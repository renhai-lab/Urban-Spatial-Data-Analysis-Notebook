"""
最终版数据获取程序，集成：
1. TimescaleDB分区
2. 实时坐标转换（GCJ-02 -> WGS84）
3. 按天导出功能
4. 内存优化管理
5. 原子性数据处理
6. 智能缺失日期检测和补全
7. 数据完整性验证
"""

import asyncio
import argparse
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone, date
import gc
import psutil
import os
from typing import List, Set, Dict, Optional

import aiohttp
import json
import pandas as pd
import psycopg
from psycopg import sql
from loguru import logger
from tqdm.asyncio import tqdm

from .config import settings
from .profiles import get_profile, DatasetProfile
from .db import setup_database, get_latest_date_from_db
from .export_memory import export_records_to_files
from .utils import tz_beijing

"""在 Windows 上将事件循环策略切换为 WindowsSelectorEventLoopPolicy，
以避免 psycopg 异步模式与 ProactorEventLoop 的不兼容问题。"""
if sys.platform.startswith("win") and hasattr(
    asyncio, "WindowsSelectorEventLoopPolicy"
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def get_memory_usage():
    """获取当前进程的内存使用情况（MB）"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


async def get_missing_dates(
    conn_str: str, profile: DatasetProfile, start_date: date, end_date: date
) -> List[date]:
    """
    检测指定日期范围内数据库中缺失的日期
    返回没有数据的日期列表
    """
    missing_dates = []

    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            async with aconn.cursor() as acur:
                # 生成日期序列并检查每天的数据量
                query = sql.SQL(
                    """
                    WITH days AS (
                        SELECT generate_series(%(start)s::date, %(end)s::date, interval '1 day')::date AS day
                    ), counts AS (
                        SELECT (({day_col} AT TIME ZONE 'Asia/Shanghai')::date) AS day,
                               COUNT(*)::bigint AS cnt
                        FROM {table}
                        WHERE ({day_col} AT TIME ZONE 'Asia/Shanghai')::date BETWEEN %(start)s::date AND %(end)s::date
                        GROUP BY 1
                    )
                    SELECT d.day, COALESCE(c.cnt, 0) AS cnt
                    FROM days d
                    LEFT JOIN counts c ON c.day = d.day
                    ORDER BY d.day;
                """
                ).format(
                    day_col=sql.Identifier(profile.latest_date_column),
                    table=sql.Identifier(profile.table_name),
                )

                await acur.execute(query, {"start": start_date, "end": end_date})

                rows = await acur.fetchall()

                for day, cnt in rows:
                    if cnt == 0:  # 没有数据的日期
                        missing_dates.append(day)

                if missing_dates:
                    logger.info(
                        f"检测到 {len(missing_dates)} 个缺失日期: {[d.strftime('%Y-%m-%d') for d in missing_dates[:5]]}{'...' if len(missing_dates) > 5 else ''}"
                    )
                else:
                    logger.info("未检测到缺失日期")
                return missing_dates

    except Exception as e:
        logger.error(f"检测缺失日期时发生错误: {e}")
        # 如果检测失败，返回完整的日期范围
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates


async def verify_day_completeness(
    conn_str: str,
    profile: DatasetProfile,
    target_date: date,
    expected_count: Optional[int] = None,
) -> bool:
    """
    验证指定日期的数据是否完整
    如果提供了期望数量，则检查实际数量是否匹配
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            async with aconn.cursor() as acur:
                query = sql.SQL(
                    """
                    SELECT COUNT(*) 
                    FROM {table} 
                    WHERE ({day_col} AT TIME ZONE 'Asia/Shanghai')::date = %(target_date)s
                """
                ).format(
                    table=sql.Identifier(profile.table_name),
                    day_col=sql.Identifier(profile.latest_date_column),
                )

                await acur.execute(query, {"target_date": target_date})
                result = await acur.fetchone()
                actual_count = result[0] if result else 0

                if expected_count is not None:
                    is_complete = actual_count == expected_count
                    if not is_complete:
                        logger.warning(
                            f"{target_date} 数据不完整: 期望 {expected_count}，实际 {actual_count}"
                        )
                    return is_complete
                else:
                    # 如果没有期望数量，只要有数据就认为是完整的
                    return actual_count > 0

    except Exception as e:
        logger.error(f"验证 {target_date} 数据完整性时发生错误: {e}")
        return False


async def delete_incomplete_day_data(
    conn_str: str, profile: DatasetProfile, target_date: date
) -> bool:
    """
    删除指定日期的不完整数据，为重新获取做准备
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            async with aconn.cursor() as acur:
                delete_query = sql.SQL(
                    """
                    DELETE FROM {table} 
                    WHERE ({day_col} AT TIME ZONE 'Asia/Shanghai')::date = %(target_date)s
                """
                ).format(
                    table=sql.Identifier(profile.table_name),
                    day_col=sql.Identifier(profile.latest_date_column),
                )

                await acur.execute(delete_query, {"target_date": target_date})
                deleted_count = acur.rowcount
                await aconn.commit()

                if deleted_count > 0:
                    logger.info(f"已删除 {target_date} 的 {deleted_count} 条不完整数据")

                return True

    except Exception as e:
        logger.error(f"删除 {target_date} 不完整数据时发生错误: {e}")
        return False


def is_empty_data(obj) -> bool:
    """统一判断 API 返回是否无数据。"""
    if not isinstance(obj, dict):
        return True
    data = obj.get("data", None)
    if data is None:
        return True
    if isinstance(data, list):
        return len(data) == 0
    if isinstance(data, str):
        s = data.strip()
        return s == "" or s == "[]"
    return True


async def fetch_page(
    session, page_num, target_date, semaphore, profile: DatasetProfile
):
    """
    异步获取单页数据，包含坐标转换功能
    """
    params = {
        "appKey": settings.APP_KEY,
        "page": page_num,
        "rows": settings.ROWS_PER_PAGE,
        "startDate": target_date.strftime("%Y%m%d"),
        "endDate": target_date.strftime("%Y%m%d"),
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    for attempt in range(settings.MAX_RETRIES):
        try:
            async with semaphore:  # 控制并发量
                async with session.get(
                    profile.api_url, params=params, timeout=30, headers=headers
                ) as response:
                    # 对明确的 404/400 不重试
                    if response.status == 404:
                        logger.debug(
                            f"{target_date} 第 {page_num} 页返回 404，视为无数据，跳过。"
                        )
                        return [], {
                            "raw_count": 0,
                            "expected_total": 0 if page_num == 1 else None,
                        }
                    if response.status == 400:
                        logger.warning(
                            f"{target_date} 第 {page_num} 页返回 400 参数错误，跳过。"
                        )
                        return [], {"raw_count": 0, "expected_total": None}

                    response.raise_for_status()

                    # 解析JSON
                    try:
                        json_data = await response.json(content_type=None)
                    except Exception as e:
                        text = await response.text()
                        snippet = text[:1000].replace("\n", " ") if text else ""
                        logger.warning(
                            f"响应 JSON 解析失败。status={response.status}, 错误={e}. 文本片段: {snippet}"
                        )
                        lower = (text or "").lower()
                        if (
                            "<html" in lower
                            or "<!doctype" in lower
                            or 'xmlns="http://www.w3.org/1999/xhtml"' in lower
                        ):
                            logger.debug("检测到 HTML 响应，将其视为无数据。")
                            return []
                        try:
                            json_data = json.loads(text)
                        except Exception as e2:
                            logger.error(f"无法解析响应为 JSON。错误1={e}, 错误2={e2}")
                            return None

                    # 检查是否有数据
                    expected_total = None
                    try:
                        if page_num == 1:
                            expected_total = int(json_data.get("total") or 0)
                            if expected_total == 0:
                                logger.debug(f"{target_date} total==0，整日无数据。")
                                return [], {"raw_count": 0, "expected_total": 0}
                    except Exception:
                        expected_total = None

                    if not json_data or is_empty_data(json_data):
                        logger.debug(f"{target_date} 第 {page_num} 页无数据。")
                        return [], {
                            "raw_count": 0,
                            "expected_total": expected_total if page_num == 1 else None,
                        }

                    # 处理数据（包含坐标转换）
                    raw_list = json_data.get("data", [])
                    prepared_data = []
                    conversion_errors = 0

                    for rec in raw_list:
                        try:
                            prepared = profile.prepare_record(rec)
                            if prepared is not None:
                                prepared_data.append(prepared)
                        except Exception as e:
                            conversion_errors += 1
                            logger.debug(f"记录处理失败: {e}")

                    if conversion_errors > 0:
                        logger.warning(f"坐标转换失败 {conversion_errors} 条记录")

                    logger.debug(
                        f"{target_date} 第 {page_num} 页获取到 {len(prepared_data)} 条有效记录"
                    )
                    return prepared_data, {
                        "raw_count": len(raw_list),
                        "expected_total": expected_total if page_num == 1 else None,
                        "conversion_errors": conversion_errors,
                    }

        except asyncio.TimeoutError:
            delay = 2**attempt
            logger.warning(
                f"{target_date} 第 {page_num} 页超时（第 {attempt + 1} 次尝试），{delay}s 后重试"
            )
            await asyncio.sleep(delay)
        except Exception as e:
            delay = 2**attempt
            logger.error(
                f"{target_date} 第 {page_num} 页请求失败（第 {attempt + 1} 次尝试）：{e}，{delay}s 后重试"
            )
            await asyncio.sleep(delay)

    logger.error(f"{target_date} 第 {page_num} 页重试次数用尽，跳过")
    return None


async def fetch_day_optimized(
    session, target_date, profile: DatasetProfile, max_concurrency: int = 5
):
    """
    优化版获取单天数据
    - 内存优化：分批处理页面
    - 数据完整性：验证获取数量
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    expected_total = None
    total_conversion_errors = 0

    # 首先获取第一页以确定总数
    first_page_result = await fetch_page(session, 1, target_date, semaphore, profile)
    if first_page_result is None:
        logger.error(f"{target_date} 第一页获取失败")
        return None, {"error": "第一页获取失败"}

    first_page_data, first_page_meta = first_page_result
    expected_total = first_page_meta.get("expected_total")
    total_conversion_errors += first_page_meta.get("conversion_errors", 0)

    if expected_total == 0:
        logger.info(f"{target_date} API 返回无数据")
        return [], {"expected_total": 0, "actual_total": 0}

    # 收集所有数据
    all_records = []
    all_records.extend(first_page_data)

    if expected_total and expected_total > settings.ROWS_PER_PAGE:
        # 计算需要获取的额外页数
        total_pages = (
            expected_total + settings.ROWS_PER_PAGE - 1
        ) // settings.ROWS_PER_PAGE
        logger.info(f"{target_date} 预计 {expected_total} 条记录，{total_pages} 页")

        # 分批获取剩余页面，控制内存使用
        batch_size = 10  # 每批处理10页

        for batch_start in range(2, total_pages + 1, batch_size):
            batch_end = min(batch_start + batch_size, total_pages + 1)

            # 并发获取当前批次的页面
            tasks = []
            for page_num in range(batch_start, batch_end):
                task = fetch_page(session, page_num, target_date, semaphore, profile)
                tasks.append(task)

            if tasks:
                progress_desc = f"获取 {target_date} 第{batch_start}-{batch_end-1}页"
                results = await tqdm.gather(*tasks, desc=progress_desc)

                for result in results:
                    if result is not None:
                        page_data, page_meta = result
                        all_records.extend(page_data)
                        total_conversion_errors += page_meta.get("conversion_errors", 0)

                # 清理当前批次的内存
                del tasks, results
                gc.collect()

    # 验证数据完整性
    actual_total = len(all_records)
    if expected_total and actual_total != expected_total:
        logger.warning(
            f"{target_date} 数据可能不完整: API显示 {expected_total}，实际获取 {actual_total}"
        )

    stats = {
        "expected_total": expected_total,
        "actual_total": actual_total,
        "conversion_errors": total_conversion_errors,
    }

    logger.info(
        f"{target_date} 获取完成：{len(all_records)} 条记录"
        + (
            f"，坐标转换错误 {total_conversion_errors} 条"
            if total_conversion_errors > 0
            else ""
        )
    )

    return all_records, stats


async def bulk_insert(conn_str: str, profile: DatasetProfile, records: list):
    """批量插入数据到数据库（分批 COPY，带进度日志）。"""
    if not records:
        return 0

    batch_size = getattr(settings, "DB_BATCH_SIZE", 10000) or 10000
    total = len(records)
    inserted_total = 0

    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            table_ident = sql.Identifier(profile.table_name)
            columns_idents = [sql.Identifier(col) for col in profile.copy_columns]

            async with aconn.cursor() as acur:
                copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
                    table_ident, sql.SQL(", ").join(columns_idents)
                )

                for i in range(0, total, batch_size):
                    batch = records[i : i + batch_size]
                    async with acur.copy(copy_sql) as copy:
                        for record in batch:
                            await copy.write_row(record)
                    await aconn.commit()
                    inserted_total += len(batch)
                    pct = inserted_total * 100 / total

                    # 记录内存使用情况
                    memory_mb = get_memory_usage()
                    logger.info(
                        f"COPY 进度: {inserted_total:,}/{total:,} ({pct:.1f}%) "
                        f"已提交 -> {profile.table_name}, 内存: {memory_mb:.1f}MB"
                    )

    except Exception as e:
        logger.error(f"批量插入失败: {e}（已提交 {inserted_total:,}/{total:,}）")
        return inserted_total

    logger.success(
        f"成功提交 {inserted_total:,}/{total:,} 条记录到 {profile.table_name}"
    )
    return inserted_total


async def process_single_day_pipeline(
    session,
    target_date: date,
    profile: DatasetProfile,
    conn_str: str,
    auto_export: bool,
    export_coord_sets: list,
    export_formats: list,
    fetch_semaphore: asyncio.Semaphore,
    export_semaphore: asyncio.Semaphore,
    atomic_mode: bool = False,
):
    """
    处理单天数据的完整流水线
    atomic_mode: 是否启用原子性模式（确保数据完整性）
    """
    result = {
        "success": False,
        "records_count": 0,
        "conversion_errors": 0,
        "exported": False,
        "date": target_date,
    }

    try:
        # 控制并发获取数据
        async with fetch_semaphore:
            memory_before = get_memory_usage()
            logger.info(f"开始处理 {target_date} 数据，内存: {memory_before:.1f}MB")

            # 原子性模式：检查并清理已有数据
            if atomic_mode:
                has_data = await verify_day_completeness(conn_str, profile, target_date)
                if has_data:
                    logger.info(f"{target_date} 发现已有数据，为确保完整性将重新获取")
                    await delete_incomplete_day_data(conn_str, profile, target_date)

            # 获取数据
            records, stats = await fetch_day_optimized(
                session, target_date, profile, settings.MAX_CONCURRENCY
            )

            if records is None:
                logger.error(f"{target_date} 数据获取失败")
                return result

            if not records:
                logger.info(f"{target_date} 无数据")
                result["success"] = True
                return result

            memory_after_fetch = get_memory_usage()
            logger.success(
                f"{target_date} 获取完成：{len(records)} 条记录，"
                f"内存: {memory_after_fetch:.1f}MB (+{memory_after_fetch - memory_before:.1f}MB)"
            )
            result["records_count"] = len(records)
            result["conversion_errors"] = stats.get("conversion_errors", 0)

        # 入库操作
        logger.info(f"开始入库 {target_date} 数据")
        inserted = await bulk_insert(conn_str, profile, records)

        if inserted > 0:
            # 原子性模式：验证入库完整性
            if atomic_mode:
                expected_count = stats.get("expected_total")
                if expected_count is None:
                    expected_count = len(records)
                elif isinstance(expected_count, str):
                    try:
                        expected_count = int(expected_count)
                    except ValueError:
                        expected_count = len(records)

                is_complete = await verify_day_completeness(
                    conn_str, profile, target_date, expected_count
                )
                if not is_complete:
                    logger.error(f"{target_date} 入库验证失败，删除不完整数据")
                    await delete_incomplete_day_data(conn_str, profile, target_date)
                    return result

            logger.success(f"{target_date} 入库完成：{inserted} 条记录")
            result["success"] = True

            # 导出操作
            if auto_export:
                async with export_semaphore:
                    logger.info(f"开始导出 {target_date} 数据")
                    try:
                        export_base = Path("data/share")
                        export_stats = await export_records_to_files(
                            records=records,
                            profile=profile,
                            target_date=target_date,
                            export_base=export_base,
                            coord_sets=export_coord_sets,
                            formats=export_formats,
                        )

                        if export_stats.get("total", 0) > 0:
                            result["exported"] = True
                            logger.success(f"{target_date} 导出完成")
                        else:
                            logger.warning(f"{target_date} 导出无数据")

                    except Exception as e:
                        logger.error(f"{target_date} 导出失败: {e}")
        else:
            logger.warning(f"{target_date} 入库失败")

        # 及时释放内存
        del records, stats
        gc.collect()

        final_memory = get_memory_usage()
        logger.debug(f"{target_date} 处理完成，最终内存: {final_memory:.1f}MB")

    except Exception as e:
        logger.error(f"处理 {target_date} 时发生错误: {e}")
        # 原子性模式下清理可能的不完整数据
        if atomic_mode:
            try:
                await delete_incomplete_day_data(conn_str, profile, target_date)
            except:
                pass

    return result


async def process_date_range(
    profile: DatasetProfile,
    start_date: date,
    end_date: date,
    auto_export: bool = True,
    export_coord_sets: list = ["raw", "wgs84"],
    export_formats: list = ["csv", "geojson"],
    missing_only: bool = False,
    atomic_mode: bool = False,
    max_concurrent_days: Optional[int] = None,
):
    """
    处理日期范围内的数据
    missing_only: 只处理缺失的日期
    atomic_mode: 原子性模式，确保数据完整性
    max_concurrent_days: 最大并发天数
    """
    conn_str = settings.get_conn_str()

    # 设置数据库
    await setup_database(conn_str, profile)

    # 使用配置的并发天数，如果没有提供的话
    if max_concurrent_days is None:
        max_concurrent_days = settings.DAYS_CONCURRENCY

    # 根据模式确定要处理的日期
    if missing_only:
        # 只处理缺失的日期
        dates = await get_missing_dates(conn_str, profile, start_date, end_date)
        if not dates:
            logger.info("没有缺失的日期需要处理")
            return {
                "total_days": 0,
                "successful_days": 0,
                "total_records": 0,
                "total_conversion_errors": 0,
                "exported_days": 0,
            }
        logger.info(f"将处理 {len(dates)} 个缺失日期")
    else:
        # 生成完整日期列表
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)
        logger.info(f"将处理完整日期范围：{len(dates)} 天")

    total_stats = {
        "total_days": len(dates),
        "successful_days": 0,
        "total_records": 0,
        "total_conversion_errors": 0,
        "exported_days": 0,
        "failed_days": [],
    }

    mode_desc = "原子性" if atomic_mode else "标准"
    logger.info(
        f"开始{mode_desc}处理 {len(dates)} 天数据，最大并发天数: {max_concurrent_days}"
    )

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:

        # 分批处理日期，避免内存爆炸
        for batch_start in range(0, len(dates), max_concurrent_days):
            batch_end = min(batch_start + max_concurrent_days, len(dates))
            batch_dates = dates[batch_start:batch_end]

            memory_before = get_memory_usage()
            logger.info(
                f"处理批次: {batch_dates[0]} 到 {batch_dates[-1]}，"
                f"处理前内存: {memory_before:.1f}MB"
            )

            # 创建信号量来控制并发数
            fetch_semaphore = asyncio.Semaphore(settings.DAYS_CONCURRENCY)
            export_semaphore = asyncio.Semaphore(settings.EXPORT_MAX_WORKERS)

            # 创建当前批次的处理任务
            tasks = []
            for target_date in batch_dates:
                task = process_single_day_pipeline(
                    session=session,
                    target_date=target_date,
                    profile=profile,
                    conn_str=conn_str,
                    auto_export=auto_export,
                    export_coord_sets=export_coord_sets,
                    export_formats=export_formats,
                    fetch_semaphore=fetch_semaphore,
                    export_semaphore=export_semaphore,
                    atomic_mode=atomic_mode,
                )
                tasks.append(task)

            # 并发执行当前批次的任务
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 统计当前批次结果
            for target_date, result in zip(batch_dates, results):
                try:
                    if isinstance(result, Exception):
                        logger.error(f"{target_date} 处理失败: {result}")
                        total_stats["failed_days"].append(
                            target_date.strftime("%Y-%m-%d")
                        )
                        continue

                    if not isinstance(result, dict):
                        logger.error(f"{target_date} 返回结果格式错误: {result}")
                        total_stats["failed_days"].append(
                            target_date.strftime("%Y-%m-%d")
                        )
                        continue

                    if result.get("success", False):
                        total_stats["successful_days"] += 1
                        total_stats["total_records"] += result.get("records_count", 0)
                        total_stats["total_conversion_errors"] += result.get(
                            "conversion_errors", 0
                        )
                        if result.get("exported", False):
                            total_stats["exported_days"] += 1
                    else:
                        total_stats["failed_days"].append(
                            target_date.strftime("%Y-%m-%d")
                        )

                except Exception as e:
                    logger.error(f"处理 {target_date} 结果时发生错误: {e}")
                    total_stats["failed_days"].append(target_date.strftime("%Y-%m-%d"))

            # 强制垃圾回收，释放当前批次的内存
            del tasks, results
            gc.collect()

            memory_after = get_memory_usage()
            logger.info(
                f"批次处理完成，处理后内存: {memory_after:.1f}MB，"
                f"内存变化: {memory_after - memory_before:+.1f}MB"
            )

    logger.success(
        f"{mode_desc}处理完成！成功: {total_stats['successful_days']}/{total_stats['total_days']} 天，"
        f"总记录: {total_stats['total_records']:,}，"
        f"坐标转换错误: {total_stats['total_conversion_errors']:,}，"
        f"导出: {total_stats['exported_days']} 天"
    )

    if total_stats["failed_days"]:
        logger.warning(f"失败的日期: {', '.join(total_stats['failed_days'])}")

    return total_stats


def main():
    """主程序入口"""
    ap = argparse.ArgumentParser(
        description="高级数据获取程序 - 支持内存优化、原子性处理、缺失日期检测"
    )
    ap.add_argument(
        "--profile", default="bike", choices=["bike", "weather_grid"], help="数据集类型"
    )
    ap.add_argument(
        "--start",
        type=str,
        help="开始日期 YYYYMMDD（默认从数据库最新日期+1开始，或配置的开始日期）",
    )
    ap.add_argument(
        "--end", type=str, help="结束日期 YYYYMMDD（默认使用配置中的结束日期）"
    )
    ap.add_argument(
        "--auto-export",
        action="store_true",
        default=True,
        help="完成数据获取后自动导出",
    )
    ap.add_argument(
        "--export-coord-sets",
        default="raw,wgs84",
        help="导出坐标系，逗号分隔（如: raw,wgs84）",
    )
    ap.add_argument(
        "--export-formats",
        default="csv,geojson",
        help="导出格式，逗号分隔（如: csv,geojson）",
    )
    ap.add_argument("--days-limit", type=int, help="限制处理天数（用于测试）")
    ap.add_argument(
        "--missing-only",
        action="store_true",
        default=False,
        help="只处理缺失的日期（推荐用于修复数据）",
    )
    ap.add_argument(
        "--atomic-mode",
        action="store_true",
        default=False,
        help="启用原子性模式（确保数据完整性，适用于重要数据）",
    )
    ap.add_argument(
        "--max-concurrent-days",
        type=int,
        default=None,
        help=f"最大并发处理天数（默认从配置文件读取：{settings.DAYS_CONCURRENCY}）",
    )

    args = ap.parse_args()

    # 配置日志
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 根据模式设置日志文件名
    mode_suffix = ""
    if args.missing_only:
        mode_suffix += "_missing"
    if args.atomic_mode:
        mode_suffix += "_atomic"

    log_file = (
        log_dir / f"fetch{mode_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="100 MB",
    )

    # 记录初始内存使用
    initial_memory = get_memory_usage()
    logger.info(f"程序启动，初始内存使用: {initial_memory:.1f}MB")

    # 获取数据集配置
    profile = get_profile(args.profile)
    logger.info(f"使用数据集配置: {profile.name}")

    # 确定日期范围
    conn_str = settings.get_conn_str()

    if args.start:
        start_date = datetime.strptime(args.start, "%Y%m%d").date()
    else:
        if not args.missing_only:
            # 普通模式：从数据库最新日期+1开始
            try:
                latest = asyncio.run(get_latest_date_from_db(conn_str, profile))
                if latest:
                    start_date = latest + timedelta(days=1)
                else:
                    start_date = datetime.strptime(
                        settings.DATA_START_DATE, "%Y%m%d"
                    ).date()
            except Exception as e:
                logger.warning(f"获取数据库最新日期失败: {e}")
                start_date = datetime.strptime(
                    settings.DATA_START_DATE, "%Y%m%d"
                ).date()
        else:
            # 缺失模式：从配置的开始日期开始
            start_date = datetime.strptime(settings.DATA_START_DATE, "%Y%m%d").date()

    if args.end:
        end_date = datetime.strptime(args.end, "%Y%m%d").date()
    else:
        end_date = datetime.strptime(settings.DATA_END_DATE, "%Y%m%d").date()

    # 限制处理天数
    if args.days_limit:
        actual_days = (end_date - start_date).days + 1
        if actual_days > args.days_limit:
            end_date = start_date + timedelta(days=args.days_limit - 1)
            logger.info(f"限制处理天数为 {args.days_limit}，调整结束日期为 {end_date}")

    export_coord_sets = [f.strip() for f in args.export_coord_sets.split(",")]
    export_formats = [f.strip() for f in args.export_formats.split(",")]

    max_concurrent_days = args.max_concurrent_days or settings.DAYS_CONCURRENCY

    logger.info(f"处理日期范围: {start_date} 到 {end_date}")
    logger.info(f"最大并发天数: {max_concurrent_days}")
    logger.info(f"只处理缺失日期: {args.missing_only}")
    logger.info(f"原子性模式: {args.atomic_mode}")
    logger.info(
        f"自动导出: {args.auto_export}，坐标系: {export_coord_sets}，格式: {export_formats}"
    )

    # 运行主程序
    stats = asyncio.run(
        process_date_range(
            profile=profile,
            start_date=start_date,
            end_date=end_date,
            auto_export=args.auto_export,
            export_coord_sets=export_coord_sets,
            export_formats=export_formats,
            missing_only=args.missing_only,
            atomic_mode=args.atomic_mode,
            max_concurrent_days=max_concurrent_days,
        )
    )

    final_memory = get_memory_usage()
    logger.info(
        f"程序执行完成！最终内存使用: {final_memory:.1f}MB，"
        f"内存增长: {final_memory - initial_memory:+.1f}MB"
    )
    return stats


if __name__ == "__main__":
    main()
