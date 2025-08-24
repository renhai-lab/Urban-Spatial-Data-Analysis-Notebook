"""
本数据集为“2021深圳开放数据应用创新大赛”的静态样例数据，不再更新，也无法提供其他数据项。
本脚本已模块化：配置见 scr/config.py，数据集定义见 scr/profiles.py，数据库见 scr/db.py。
"""

import asyncio
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
                        return []
                    if response.status == 400:
                        logger.warning(
                            f"{target_date.date()} 第 {page_num} 页返回 400 参数错误，跳过（不重试）。"
                        )
                        return []

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
                    try:
                        if page_num == 1 and int(json_data.get("total") or 0) == 0:
                            logger.debug(f"{target_date.date()} total==0，整日无数据。")
                            return []
                    except Exception:
                        pass

                    if not json_data or is_empty_data(json_data):
                        logger.debug(f"{target_date.date()} 第 {page_num} 页无数据。")
                        return []  # 返回空列表表示此页无数据

                    # 在这里处理数据为元组
                    prepared_data = [
                        profile.prepare_record(rec) for rec in json_data.get("data", [])
                    ]
                    # 过滤掉处理失败的 None 值
                    cleaned = [d for d in prepared_data if d is not None]
                    logger.debug(
                        f"{target_date.date()} 第 {page_num} 页拉取 {len(json_data['data'])} 条，净得 {len(cleaned)} 条。"
                    )
                    return cleaned

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
    """获取一天的数据并使用 COPY 命令高效存入数据库（结构由 profile 定义）。"""
    page_num = 1
    total_records_for_day = 0

    # logger.info(f"开始处理日期：{date.date()}")
    async with await psycopg.AsyncConnection.connect(
        conn_str, connect_timeout=settings.CONNECT_TIMEOUT
    ) as aconn:
        while True:
            page_data = await fetch_page(
                session, page_num, date, semaphore, profile
            )  # page_data 是元组列表

            if page_data is None:
                logger.error(f"跳过日期 {date.date()} 的剩余部分，因为网络错误。")
                break

            if not page_data:
                logger.debug(f"{date.date()} 第 {page_num} 页为空，分页结束。")
                break

            try:
                # 使用 psycopg 最高效的 COPY 方式
                async with aconn.cursor() as acur:
                    # 动态 COPY 列
                    cols = sql.SQL(", ").join(map(sql.Identifier, profile.copy_columns))
                    copy_command = sql.SQL("COPY {table} ({cols}) FROM STDIN;").format(
                        table=sql.Identifier(profile.table_name), cols=cols
                    )
                    async with acur.copy(copy_command) as copy:
                        for record_tuple in page_data:
                            await copy.write_row(record_tuple)

                total_records_for_day += len(page_data)
                logger.debug(
                    f"{date.date()} 第 {page_num} 页写入 {len(page_data)} 条，累计 {total_records_for_day} 条。"
                )
            except Exception as e:
                logger.error(f"写入数据库时出错: {e}")

            if len(page_data) < settings.ROWS_PER_PAGE:
                logger.debug(
                    f"{date.date()} 第 {page_num} 页记录数 {len(page_data)} < 每页 {settings.ROWS_PER_PAGE}，到达最后一页。"
                )
                break

            page_num += 1

    logger.info(f"完成日期：{date.date()}，共写入 {total_records_for_day} 条。")
    return total_records_for_day


async def main():
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

    # 获取上次爬取的最新日期
    latest_date_in_db = await get_latest_date_from_db(conn_str, profile)
    start_date_str = settings.DATA_START_DATE
    if latest_date_in_db:
        start_date = latest_date_in_db + timedelta(days=1)
        start_date_str = start_date.strftime("%Y%m%d")
        logger.info(
            f"数据库中最新数据日期为 {latest_date_in_db}（列：{profile.latest_date_column}），将从 {start_date_str} 开始获取。"
        )

    date_range = pd.date_range(
        start=start_date_str, end=settings.DATA_END_DATE, freq="D"
    )

    if len(date_range) == 0:
        logger.info("数据已是最新，无需获取。")
        return

    logger.info(
        f"任务日期范围：{start_date_str} ~ {settings.DATA_END_DATE}，共 {len(date_range)} 天；页内并发={settings.MAX_CONCURRENCY}，按天并发={settings.DAYS_CONCURRENCY}，每页={settings.ROWS_PER_PAGE}"
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
