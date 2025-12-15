"""
本数据集为“2021深圳开放数据应用创新大赛”的静态样例数据，不再更新，也无法提供其他数据项。
本脚本已模块化：配置见 src/config.py，数据集定义见 src/profiles.py，数据库见 src/db.py。
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
from .utils import tz_beijing

"""在 Windows 上将事件循环策略切换为 WindowsSelectorEventLoopPolicy，
以避免 psycopg 异步模式与 ProactorEventLoop 的不兼容问题。"""
if sys.platform.startswith("win") and hasattr(
    asyncio, "WindowsSelectorEventLoopPolicy"
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def is_empty_data(obj) -> bool:
    """统一判断 API 返回是否无数据。
    兼容 data 缺失/None、空列表、空字符串、"[]" 等情况。
    """
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
    异步获取单页数据，并包含强大的重试逻辑。
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

    logger.debug(f"请求参数: {params}")

    for attempt in range(settings.MAX_RETRIES):
        try:
            async with semaphore:  # 控制并发量
                async with session.get(
                    profile.api_url, params=params, timeout=30, headers=headers
                ) as response:
                    # 对明确的 404/400 不重试，直接视为当天无数据或参数不支持
                    if response.status == 404:
                        logger.debug(
                            f"{target_date.date()} 第 {page_num} 页返回 404，视为无数据/接口无该日，跳过。"
                        )
                        # 明确无数据：期望总数置 0
                        return [], {
                            "raw_count": 0,
                            "expected_total": 0 if page_num == 1 else None,
                        }
                    if response.status == 400:
                        logger.warning(
                            f"{target_date.date()} 第 {page_num} 页返回 400 参数错误，跳过（不重试）。"
                        )
                        # 参数错误：保守起见不确认 expected_total
                        return [], {"raw_count": 0, "expected_total": None}

                    response.raise_for_status()  # 对 >= 400 的状态码抛出异常
                    # 尝试解析 JSON，某些响应会返回 application/xhtml+xml 或其他 content-type
                    try:
                        json_data = await response.json(content_type=None)
                    except Exception as e:
                        # 解析失败：读取文本并做出降级判断
                        text = await response.text()
                        snippet = text[:1000].replace("\n", " ") if text else ""
                        logger.warning(
                            f"响应 JSON 解析失败，尝试降级处理。status={response.status}, 错误={e}. 文本片段: {snippet}"
                        )
                        # 如果返回的是 HTML（页面或错误页），把它视为当天无数据并记录调试片段
                        lower = (text or "").lower()
                        if (
                            "<html" in lower
                            or "<!doctype" in lower
                            or 'xmlns="http://www.w3.org/1999/xhtml"' in lower
                        ):
                            logger.debug(
                                f"检测到 HTML 响应（{response.content_type}），将其视为无数据。"
                            )
                            return []
                        # 否则尝试用 json.loads 作为最后手段
                        try:
                            json_data = json.loads(text)
                        except Exception as e2:
                            logger.error(
                                f"无法解析响应为 JSON（包括二次尝试）。错误1={e}, 错误2={e2}，URL={response.url}"
                            )
                            return None

                    # 第 1 页时，total==0 可直接判定整日无数据
                    expected_total = None
                    try:
                        if page_num == 1:
                            expected_total = int(json_data.get("total") or 0)
                            if expected_total == 0:
                                logger.debug(
                                    f"{target_date.date()} total==0，整日无数据。"
                                )
                                return [], {"raw_count": 0, "expected_total": 0}
                    except Exception:
                        expected_total = None

                    if not json_data or is_empty_data(json_data):
                        logger.debug(f"{target_date.date()} 第 {page_num} 页无数据。")
                        return [], {
                            "raw_count": 0,
                            "expected_total": expected_total if page_num == 1 else None,
                        }

                    # 在这里处理数据为元组
                    raw_list = json_data.get("data", [])
                    prepared_data = [profile.prepare_record(rec) for rec in raw_list]
                    # 过滤掉处理失败的 None 值
                    cleaned = [d for d in prepared_data if d is not None]
                    logger.debug(
                        f"{target_date.date()} 第 {page_num} 页拉取 {len(raw_list)} 条，净得 {len(cleaned)} 条。"
                    )
                    return cleaned, {
                        "raw_count": len(raw_list),
                        "expected_total": expected_total if page_num == 1 else None,
                    }

        except (
            aiohttp.ClientResponseError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ValueError,
        ) as e:
            logger.warning(
                f"获取 {target_date.date()} 第 {page_num} 页失败 (尝试 {attempt + 1}/{settings.MAX_RETRIES}): {e}"
            )
            if attempt < settings.MAX_RETRIES - 1:
                delay = settings.RETRY_DELAY_SECONDS * (2**attempt)  # 指数退避
                await asyncio.sleep(delay)
            else:
                logger.error(f"获取 {target_date.date()} 第 {page_num} 页彻底失败。")
                return None  # 返回 None 表示彻底失败


async def fetch_day(session, date, conn_str, semaphore, profile: DatasetProfile):
    """按天原子化拉取：
    - 在一个事务内，先删除该天旧数据（按北京时间归档），再分页抓取 + COPY 写入；
    - 任一环节失败则整天回滚；成功则整天提交；
    - 幂等：重复执行不会产生重复数据。
    """
    page_num = 1
    total_records_for_day = 0  # 实际写入（清洗后）的记录数
    raw_total_received = 0  # API 原始返回的记录计数（按 total/rows 维度）
    expected_total = None  # API total（来自第 1 页）
    day_str = str(date.date())

    async with await psycopg.AsyncConnection.connect(
        conn_str, connect_timeout=settings.CONNECT_TIMEOUT
    ) as aconn:
        # 单日事务：失败则回滚，成功自动提交
        async with aconn.transaction():
            # 1) 先删除该天旧数据（北京时间）
            async with aconn.cursor() as acur:
                del_sql = sql.SQL(
                    "DELETE FROM {table} WHERE (({col} AT TIME ZONE 'Asia/Shanghai')::date) = %s;"
                ).format(
                    table=sql.Identifier(profile.table_name),
                    col=sql.Identifier(profile.latest_date_column),
                )
                await acur.execute(del_sql, (date.date(),))
                logger.debug(f"{day_str} 先删旧数据：{acur.rowcount or 0} 条。")

            # 2) 分页抓取 + COPY（全部在同一事务内）
            while True:
                res = await fetch_page(session, page_num, date, semaphore, profile)

                if res is None:
                    # 触发回滚：让异常向外抛出
                    raise RuntimeError(
                        f"{day_str} 第 {page_num} 页网络/解析失败，整日回滚。"
                    )

                page_data, meta = res
                raw_count = (
                    int(meta.get("raw_count", len(page_data)))
                    if isinstance(meta, dict)
                    else len(page_data)
                )
                if expected_total is None and isinstance(meta, dict):
                    et = meta.get("expected_total")
                    if et is not None:
                        expected_total = int(et)

                if raw_count == 0:
                    logger.debug(f"{day_str} 第 {page_num} 页无数据，分页结束。")
                    break

                # 使用 COPY 写入当页（page_data 是清洗后记录）
                try:
                    if page_data:
                        async with aconn.cursor() as acur:
                            cols = sql.SQL(", ").join(
                                map(sql.Identifier, profile.copy_columns)
                            )
                            copy_command = sql.SQL(
                                "COPY {table} ({cols}) FROM STDIN;"
                            ).format(
                                table=sql.Identifier(profile.table_name), cols=cols
                            )
                            async with acur.copy(copy_command) as copy:
                                for record_tuple in page_data:
                                    await copy.write_row(record_tuple)

                        total_records_for_day += len(page_data)
                        logger.debug(
                            f"{day_str} 第 {page_num} 页写入 {len(page_data)} 条，累计 {total_records_for_day} 条。"
                        )
                    else:
                        logger.debug(
                            f"{day_str} 第 {page_num} 页清洗后为空（原始 {raw_count} 条）。"
                        )
                except Exception as e:
                    # 触发回滚
                    raise RuntimeError(
                        f"{day_str} 写入失败（第 {page_num} 页）：{e}"
                    ) from e

                raw_total_received += raw_count

                # 使用原始条数判断是否最后一页
                if raw_count < settings.ROWS_PER_PAGE:
                    logger.debug(
                        f"{day_str} 第 {page_num} 页原始记录数 {raw_count} < 每页 {settings.ROWS_PER_PAGE}，到达最后一页。"
                    )
                    break

                page_num += 1

            # 3) 完整性校验：若 expected_total 可用，要求与 raw_total_received 一致
            if expected_total is not None:
                if raw_total_received == 0:
                    # 平台偶有 total>0 但 data 为空的异常：按“无数据日”处理，不视为不完整
                    logger.info(
                        f"{day_str} API total={expected_total} 但无任何记录返回，按无数据日处理（不视为不完整）。"
                    )
                elif raw_total_received != expected_total:
                    raise RuntimeError(
                        f"{day_str} 完整性校验失败：API total={expected_total}，实际收到={raw_total_received}，已回滚。"
                    )

    logger.info(
        f"完成日期：{day_str}，写入 {total_records_for_day} 条（清洗后），API原始计数={raw_total_received}，已原子提交。"
    )
    return total_records_for_day


async def main():
    parser = argparse.ArgumentParser(description="深圳开放数据抓取：共享单车/天气等")
    parser.add_argument(
        "--start", help="覆盖起始日期 YYYYMMDD（提供时将不从数据库续爬）", default=None
    )
    parser.add_argument("--end", help="覆盖结束日期 YYYYMMDD", default=None)
    args = parser.parse_args()

    # 重新配置 logger：控制台（stderr） + 文件，级别来自配置
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL)
    logger.add(
        f"{log_dir}/fetch_log_{{time}}.log", level=settings.LOG_LEVEL, rotation="10 MB"
    )
    logger.info("启动数据获取程序 (目标: PostGIS)...")

    if settings.APP_KEY == "YOUR_APP_KEY_HERE":
        logger.warning("APP_KEY 仍为占位值，请在 .env 中设置真实 APP_KEY。")

    profile = get_profile(settings.DATASET_PROFILE)
    logger.info(
        f"当前数据集：{profile.name} | 表：{profile.table_name} | 接口：{profile.api_url}"
    )
    # 数据库连接字符串
    conn_str = settings.get_conn_str()
    # 初始化数据库
    await setup_database(conn_str, profile)

    # 计算实际的起止日期：命令行 > 配置 > 数据库续爬
    end_date_str = args.end or settings.DATA_END_DATE
    start_date_str = args.start or settings.DATA_START_DATE

    if args.start is None:
        # 未显式指定 --start 时，才启用数据库续爬
        latest_date_in_db = await get_latest_date_from_db(conn_str, profile)
        if latest_date_in_db:
            start_date = latest_date_in_db + timedelta(days=1)
            start_date_str = start_date.strftime("%Y%m%d")
            logger.info(
                f"数据库中最新数据日期为 {latest_date_in_db}（列：{profile.latest_date_column}），将从 {start_date_str} 开始获取。"
            )
    else:
        logger.info(
            f"使用命令行覆盖日期范围：start={start_date_str}, end={end_date_str}（忽略续爬）"
        )

    date_range = pd.date_range(start=start_date_str, end=end_date_str, freq="D")

    if len(date_range) == 0:
        logger.info("数据已是最新，无需获取。")
        return

    logger.info(
        f"任务日期范围：{start_date_str} ~ {end_date_str}，共 {len(date_range)} 天；页内并发={settings.MAX_CONCURRENCY}，按天并发={settings.DAYS_CONCURRENCY}，每页={settings.ROWS_PER_PAGE}"
    )
    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
    async with aiohttp.ClientSession() as session:
        pbar = tqdm(total=len(date_range), desc="按天获取数据")

        total_records = 0
        # 分批创建任务，限制按天并发数量
        for i in range(0, len(date_range), settings.DAYS_CONCURRENCY):
            batch = list(date_range[i : i + settings.DAYS_CONCURRENCY])
            tasks = [
                asyncio.create_task(
                    fetch_day(session, d, conn_str, semaphore, profile),
                    name=f"fetch_day:{profile.name}:{d.date()}",
                )
                for d in batch
            ]
            try:
                # 小睡一会儿以让 create_task/事件循环稳定
                await asyncio.sleep(0)
                for t in asyncio.as_completed(tasks):
                    try:
                        day_total = await t
                        if day_total and day_total > 0:
                            total_records += day_total
                    except asyncio.CancelledError:
                        logger.debug("按天任务被取消（CancelledError），已忽略。")
                        # 轻微等待以让取消传播，不阻塞太久
                        await asyncio.sleep(0)
                        continue
                    except Exception as e:
                        logger.error(f"按天任务出现未捕获异常：{e}")
                    finally:
                        pbar.update(1)
                        pbar.set_postfix_str(f"共获取 {total_records:,} 条记录")
            finally:
                # 确保没有悬挂任务
                pending = [t for t in tasks if not t.done()]
                if pending:
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

        pbar.close()

    logger.success("所有日期处理完毕！")


if __name__ == "__main__":
    asyncio.run(main())
