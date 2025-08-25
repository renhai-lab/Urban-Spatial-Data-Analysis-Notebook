"""
按天核查工具：统计数据库内每日条数，找出缺失天/异常天，并导出 CSV。

用法：直接运行本脚本将读取 settings 与当前 profile，范围为 DATA_START_DATE ~ DATA_END_DATE。
输出：
- logs/daily_counts.csv  包含 day,cnt 两列
- 终端打印缺失天列表与概要统计

注意：
- 天粒度采用北京时间归档：(latest_date_column at time zone 'Asia/Shanghai')::date
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from loguru import logger
import psycopg
from psycopg import sql
import pandas as pd
import asyncio
import aiohttp
import sys

from .config import settings
from .profiles import get_profile, DatasetProfile


def _to_date_str8(s: str) -> str:
    s = s.replace("-", "").strip()
    assert len(s) == 8 and s.isdigit(), "日期应为 YYYYMMDD 或 YYYY-MM-DD"
    return s


def fetch_daily_counts_db(conn_str: str, profile: DatasetProfile) -> pd.DataFrame:
    start_d = _to_date_str8(settings.DATA_START_DATE)
    end_d = _to_date_str8(settings.DATA_END_DATE)

    # 生成日期序列并左连接每日计数
    with psycopg.connect(conn_str, connect_timeout=settings.CONNECT_TIMEOUT) as conn:
        with conn.cursor() as cur:
            day_col = sql.Identifier(profile.latest_date_column)
            tbl = sql.Identifier(profile.table_name)

            # SELECT 结果：day::date, cnt::bigint
            query = sql.SQL(
                """
                WITH days AS (
                    SELECT generate_series(%(start)s::date, %(end)s::date, interval '1 day')::date AS day
                ), counts AS (
                    SELECT (({day_col} AT TIME ZONE 'Asia/Shanghai')::date) AS day,
                           COUNT(*)::bigint AS cnt
                    FROM {tbl}
                    GROUP BY 1
                )
                SELECT d.day, COALESCE(c.cnt, 0) AS cnt
                FROM days d
                LEFT JOIN counts c ON c.day = d.day
                ORDER BY d.day;
                """
            ).format(day_col=day_col, tbl=tbl)

            cur.execute(query, {"start": start_d, "end": end_d})
            rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["day", "cnt"])
    return df


async def fetch_api_total_for_day_async(
    session: aiohttp.ClientSession, day_str8: str, profile: DatasetProfile
) -> int | None:
    """异步调用 API 获取单日 total。400/404 视为 0；HTML/空数组按 0。"""
    params = {
        "appKey": settings.APP_KEY,
        "page": 1,
        "rows": 1,
        "startDate": day_str8,
        "endDate": day_str8,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    url = profile.api_url
    for attempt in range(3):
        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (400, 404):
                    return 0
                resp.raise_for_status()
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    text = await resp.text()
                    txt = (text or "").lower()
                    if "<html" in txt or "<!doctype" in txt:
                        return 0
                    try:
                        import json as _json

                        data = _json.loads(text)
                    except Exception:
                        return None

                if isinstance(data, dict):
                    raw_total = int(data.get("total") or 0)
                    arr = data.get("data")
                    if isinstance(arr, list) and len(arr) == 0:
                        return 0
                    return raw_total
                return None
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1 + attempt)
                continue
            return None


async def fetch_api_totals_for_days(
    days_str8: list[str], profile: DatasetProfile, concurrency: int = 30
) -> list[int | None]:
    # Windows 事件循环兼容（避免 psycopg 异步问题；此处仅 aiohttp）
    if sys.platform.startswith("win") and hasattr(
        asyncio, "WindowsSelectorEventLoopPolicy"
    ):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:

        async def run_one(d: str):
            async with sem:
                return await fetch_api_total_for_day_async(session, d, profile)

        tasks = [asyncio.create_task(run_one(d)) for d in days_str8]
        return await asyncio.gather(*tasks)


def detect_missing_days(df: pd.DataFrame) -> List[str]:
    return [d.strftime("%Y-%m-%d") for d, c in zip(df["day"], df["cnt"]) if int(c) == 0]


def detect_low_days(df: pd.DataFrame, ratio: float = 0.5) -> List[str]:
    """找出明显偏低的天（低于全期中位数 * ratio），用于人工复核。
    不代表一定缺失，只是给线索。
    """
    if df.empty:
        return []
    med = float(df["cnt"].median()) if len(df) else 0.0
    threshold = med * ratio
    low = df[df["cnt"] < threshold]
    return [d.strftime("%Y-%m-%d") for d in low["day"].tolist()]


def main():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.remove()
    logger.add(lambda m: print(m, end=""), level=settings.LOG_LEVEL)
    logger.add(
        log_dir / "audit_days_{time}.log", level=settings.LOG_LEVEL, rotation="10 MB"
    )

    profile = get_profile(settings.DATASET_PROFILE)
    conn_str = settings.get_conn_str()
    logger.info(
        f"开始按天核查：表={profile.table_name}，日期范围 {settings.DATA_START_DATE}~{settings.DATA_END_DATE}\n"
    )

    df = fetch_daily_counts_db(conn_str, profile)
    out_csv = log_dir / "daily_counts.csv"
    df_out = df.copy()
    df_out["day"] = pd.to_datetime(df_out["day"]).dt.strftime("%Y-%m-%d")
    df_out.to_csv(out_csv, index=False, encoding="utf-8")
    logger.info(f"已导出 {out_csv}")

    missing = detect_missing_days(df)
    low = detect_low_days(df, ratio=0.5)

    total = int(df["cnt"].sum()) if len(df) else 0
    msg = [
        f"总计 {total:,} 条",
        f"天数 {len(df)} 天",
        f"缺失天 {len(missing)} 天",
        f"低值可疑天 {len(low)} 天 (阈值=中位数*0.5，仅作线索)",
    ]
    logger.info(" | ".join(msg))

    if missing:
        logger.warning("缺失天：" + ", ".join(missing))
    if low:
        logger.warning("低值可疑天：" + ", ".join(low))

    # 给出补爬提示（人工设定日期范围重新跑 fetcher.py 或定向一天一天补）
    logger.info(
        "\n补爬建议：\n- 缺失天可优先补；\n- 如需单日重跑，可临时将 .env 中 DATA_START_DATE=YYYYMMDD, DATA_END_DATE=YYYYMMDD，或给 fetcher.py 增加（ --start 20210506 --end 20210506）命令行覆盖参数。"
    )

    # 若有 APP_KEY，进一步调 API total 做对比
    if settings.APP_KEY and settings.APP_KEY != "YOUR_APP_KEY_HERE":
        logger.info("开始调用 API 获取每日 total 进行对比（异步并发）…")
        days_fmt = pd.to_datetime(df["day"]).dt.strftime("%Y-%m-%d").tolist()
        days_str8 = pd.to_datetime(df["day"]).dt.strftime("%Y%m%d").tolist()
        api_totals: list[int | None] = asyncio.run(
            fetch_api_totals_for_days(days_str8, profile, concurrency=30)
        )

        norm_api_totals: list[int | None] = []
        for x in api_totals:
            if x is None:
                norm_api_totals.append(None)
            else:
                try:
                    norm_api_totals.append(int(x))
                except Exception:
                    norm_api_totals.append(None)

        df_api = pd.DataFrame(
            {
                "day": days_fmt,
                "db_count": [int(v) for v in df["cnt"].tolist()],
                "api_total": norm_api_totals,
            }
        )
        df_api["delta"] = df_api["api_total"].astype("Int64") - df_api[
            "db_count"
        ].astype("Int64")
        out2 = log_dir / "daily_counts_with_api.csv"
        df_api.to_csv(out2, index=False, encoding="utf-8")
        logger.info(f"已导出 {out2}")

        # 列出明显不一致的天
        mism = df_api[df_api["api_total"].notna() & (df_api["delta"] != 0)]
        if not mism.empty:
            bad_list: list[str] = []
            for row in mism[["day", "delta"]].itertuples(index=False, name=None):
                day_val, delta_val = row
                if pd.isna(delta_val):
                    delta_str = "NA"
                else:
                    try:
                        delta_str = str(int(delta_val))
                    except Exception:
                        delta_str = str(delta_val)
                bad_list.append(f"{day_val} Δ={delta_str}")
            bad = ", ".join(bad_list)
            logger.warning(f"与 API total 不一致的天：{bad}")
        else:
            logger.info("数据库计数与 API total 一致。")
    else:
        logger.warning("未配置有效 APP_KEY，跳过 API total 对比。")


if __name__ == "__main__":
    main()
