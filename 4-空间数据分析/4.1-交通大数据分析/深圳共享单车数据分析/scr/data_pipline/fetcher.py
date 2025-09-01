"""
优化版本的数据获取程序，集成：
1. TimescaleDB分区
2. 实时坐标转换（GCJ-02 -> WGS84）
3. 按天导出功能
4. 更高效的数据处理流程
"""

import asyncio
import argparse
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone, date

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

    # logger.debug(f"请求参数: {params}，请求url：{profile.api_url}")

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


async def fetch_day(
    session, target_date, profile: DatasetProfile, max_concurrency: int = 5
):
    """获取单天数据"""
    semaphore = asyncio.Semaphore(max_concurrency)
    all_records = []
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
        logger.info(f"{target_date} 无数据")
        return [], {"expected_total": 0, "actual_total": 0}

    all_records.extend(first_page_data)

    if expected_total and expected_total > settings.ROWS_PER_PAGE:
        # 计算需要获取的额外页数
        total_pages = (
            expected_total + settings.ROWS_PER_PAGE - 1
        ) // settings.ROWS_PER_PAGE
        logger.info(f"{target_date} 预计 {expected_total} 条记录，{total_pages} 页")

        # 并发获取剩余页面
        tasks = []
        for page_num in range(2, total_pages + 1):
            task = fetch_page(session, page_num, target_date, semaphore, profile)
            tasks.append(task)

        if tasks:
            progress_desc = f"获取 {target_date}"
            results = await tqdm.gather(*tasks, desc=progress_desc)

            for result in results:
                if result is not None:
                    page_data, page_meta = result
                    all_records.extend(page_data)
                    total_conversion_errors += page_meta.get("conversion_errors", 0)

    stats = {
        "expected_total": expected_total,
        "actual_total": len(all_records),
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
                    logger.info(
                        f"COPY 进度: {inserted_total:,}/{total:,} ({pct:.1f}%) 已提交 -> {profile.table_name}"
                    )

    except Exception as e:
        logger.error(
            f"批量插入失败: {e}（已提交 {inserted_total:,}/{total:,}）"
        )
        return inserted_total

    logger.success(
        f"成功提交 {inserted_total:,}/{total:,} 条记录到 {profile.table_name}"
    )
    return inserted_total


async def process_date_range(
    profile: DatasetProfile,
    start_date: date,
    end_date: date,
    auto_export: bool = True,
    export_coord_sets: list = ["raw", "wgs84"],
    export_formats: list = ["csv", "geojson"],
):
    """处理日期范围内的数据，实现流水线式处理：获取完即导出"""
    conn_str = settings.get_conn_str()

    # 设置数据库
    await setup_database(conn_str, profile)

    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    total_stats = {
        "total_days": len(dates),
        "successful_days": 0,
        "total_records": 0,
        "total_conversion_errors": 0,
        "exported_days": 0,
    }

    logger.info(
        f"开始流水线处理 {len(dates)} 天数据，最大并发天数: {settings.DAYS_CONCURRENCY}"
    )

    # 创建信号量来控制并发数
    fetch_semaphore = asyncio.Semaphore(settings.DAYS_CONCURRENCY)
    export_semaphore = asyncio.Semaphore(settings.EXPORT_MAX_WORKERS)

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=60)
    ) as session:

        # 创建所有日期的处理任务
        tasks = []
        for target_date in dates:
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
            )
            tasks.append(task)

        # 并发执行所有任务，每个任务内部是流水线式的
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        for target_date, result in zip(dates, results):
            try:
                if isinstance(result, Exception):
                    logger.error(f"{target_date} 处理失败: {result}")
                    continue

                if not isinstance(result, dict):
                    logger.error(f"{target_date} 返回结果格式错误: {result}")
                    continue

                if result.get("success", False):
                    total_stats["successful_days"] += 1
                    total_stats["total_records"] += result.get("records_count", 0)
                    total_stats["total_conversion_errors"] += result.get(
                        "conversion_errors", 0
                    )
                    if result.get("exported", False):
                        total_stats["exported_days"] += 1

            except Exception as e:
                logger.error(f"处理 {target_date} 结果时发生错误: {e}")

    logger.success(
        f"流水线处理完成！成功: {total_stats['successful_days']}/{total_stats['total_days']} 天，"
        f"总记录: {total_stats['total_records']:,}，"
        f"坐标转换错误: {total_stats['total_conversion_errors']:,}，"
        f"导出: {total_stats['exported_days']} 天"
    )

    return total_stats


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
):
    """处理单天数据的完整流水线：获取->入库->导出"""

    result = {
        "success": False,
        "records_count": 0,
        "conversion_errors": 0,
        "exported": False,
    }

    try:
        # 控制并发获取数据
        async with fetch_semaphore:
            logger.info(f"开始获取 {target_date} 数据")

            # 获取数据
            records, stats = await fetch_day(
                session, target_date, profile, settings.MAX_CONCURRENCY
            )

            if records is None:
                logger.error(f"{target_date} 数据获取失败")
                return result

            if not records:
                logger.info(f"{target_date} 无数据")
                result["success"] = True
                return result

            logger.success(f"{target_date} 获取完成：{len(records)} 条记录")
            result["records_count"] = len(records)
            result["conversion_errors"] = stats.get("conversion_errors", 0)

        # 入库操作（不在信号量控制内，因为数据库连接有自己的池管理）
        logger.info(f"开始入库 {target_date} 数据")
        inserted = await bulk_insert(conn_str, profile, records)

        if inserted > 0:
            logger.success(f"{target_date} 入库完成：{inserted} 条记录")
            result["success"] = True

            # 导出操作（获取完数据就立即开始，不等待其他天）
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

    except Exception as e:
        logger.error(f"处理 {target_date} 时发生错误: {e}")

    return result


def main():
    """主程序入口"""
    ap = argparse.ArgumentParser(description="优化版本的数据获取程序")
    ap.add_argument(
        "--profile", default="bike", choices=["bike", "weather_grid"], help="数据集类型"
    )
    ap.add_argument(
        "--start", type=str, help="开始日期 YYYYMMDD（默认从数据库最新日期+1开始）"
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
    log_file = log_dir / f"fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="100 MB",
    )

    # 获取数据集配置
    profile = get_profile(args.profile)
    logger.info(f"使用数据集配置: {profile.name}")

    # 确定日期范围
    conn_str = settings.get_conn_str()

    if args.start:
        start_date = datetime.strptime(args.start, "%Y%m%d").date()
    else:
        # 从数据库最新日期+1开始
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

    logger.info(f"处理日期范围: {start_date} 到 {end_date}")
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
        )
    )

    logger.info("程序执行完成！")
    return stats


if __name__ == "__main__":
    main()
