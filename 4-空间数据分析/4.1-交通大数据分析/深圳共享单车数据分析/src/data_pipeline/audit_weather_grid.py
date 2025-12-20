"""
气象格点数据完整性审计脚本

检查数据库中每天的气象格点数据完整性，生成审计报告。
可以识别缺失、不完整或异常的日期。
"""

import asyncio
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import psycopg
from psycopg import sql
from loguru import logger
import aiohttp

from .config import settings
from .profiles import get_profile

# Windows 平台兼容性设置
if sys.platform.startswith("win") and hasattr(
    asyncio, "WindowsSelectorEventLoopPolicy"
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def fetch_api_total_for_day_async(day_str8: str, api_url: str) -> tuple[int | None, str | None]:
    """
    调用气象格点 API 获取单日 total。

    返回 (total, flag)。flag 用于标记异常场景，例如 total=1 但 data 为空，避免被误判为缺失天。
    """

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

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.get(
                    api_url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (400, 404):
                        return 0, None
                    resp.raise_for_status()
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        text = await resp.text()
                        txt = (text or "").lower()
                        if "<html" in txt or "<!doctype" in txt:
                            return 0, "html_response"
                        try:
                            import json as _json

                            data = _json.loads(text)
                        except Exception:
                            return None, "json_parse_failed"

                    if isinstance(data, dict):
                        raw_total = int(data.get("total") or 0)
                        arr = data.get("data")
                        if isinstance(arr, list) and len(arr) == 0:
                            if raw_total == 1:
                                return raw_total, "empty_data_but_total_1"
                            return 0, "empty_data"
                        return raw_total, None
                    return None, None
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
                    continue
                return None, "exception"
    
    return None, "max_retries"


async def audit_weather_grid_completeness(
    start_date: date,
    end_date: date,
    output_file: str = "data/audit/weather_grid_audit.csv",
):
    """
    审计气象格点数据的完整性

    Args:
        start_date: 开始日期
        end_date: 结束日期
        output_file: 输出CSV文件路径
    """
    profile = get_profile("weather_grid")
    conn_str = settings.get_conn_str()

    results = []

    # 准备 API 对比（可选）
    use_api = bool(settings.APP_KEY and settings.APP_KEY != "YOUR_APP_KEY_HERE")
    api_map: dict[str, tuple[int | None, str | None]] = {}

    async with await psycopg.AsyncConnection.connect(conn_str) as aconn:
        async with aconn.cursor() as acur:
            # 生成日期序列并统计每天的数据
            query = sql.SQL(
                """
                WITH date_series AS (
                    SELECT generate_series(
                        %(start_date)s::date,
                        %(end_date)s::date,
                        '1 day'::interval
                    )::date AS check_date
                ),
                daily_stats AS (
                    SELECT 
                        (crttime AT TIME ZONE 'Asia/Shanghai')::date AS data_date,
                        COUNT(*) as record_count,
                        COUNT(DISTINCT keyid) as unique_keyids,
                        COUNT(DISTINCT gridid) as unique_grids,
                        MIN(crttime) as earliest_crttime,
                        MAX(crttime) as latest_crttime,
                        -- 检查是否有重复 keyid（理论上应该唯一）
                        COUNT(*) - COUNT(DISTINCT keyid) as duplicate_keyids
                    FROM sz_weather_grid
                    WHERE (crttime AT TIME ZONE 'Asia/Shanghai')::date 
                        BETWEEN %(start_date)s AND %(end_date)s
                    GROUP BY 1
                )
                SELECT 
                    ds.check_date,
                    COALESCE(s.record_count, 0) as record_count,
                    COALESCE(s.unique_keyids, 0) as unique_keyids,
                    COALESCE(s.unique_grids, 0) as unique_grids,
                    s.earliest_crttime,
                    s.latest_crttime,
                    COALESCE(s.duplicate_keyids, 0) as duplicate_keyids
                FROM date_series ds
                LEFT JOIN daily_stats s ON ds.check_date = s.data_date
                ORDER BY ds.check_date;
            """
            )

            await acur.execute(query, {"start_date": start_date, "end_date": end_date})

            rows = await acur.fetchall()

            # 若配置了 APP_KEY，则并发请求 API，获取每日 total/flag
            if use_api:
                day_list_str8 = [r[0].strftime("%Y%m%d") for r in rows]
                tasks = [
                    asyncio.create_task(
                        fetch_api_total_for_day_async(d, profile.api_url)
                    )
                    for d in day_list_str8
                ]
                api_results = await asyncio.gather(*tasks)
                api_map = {
                    d: res for d, res in zip(day_list_str8, api_results)
                }

            for row in rows:
                (
                    check_date,
                    record_count,
                    unique_keyids,
                    unique_grids,
                    earliest_crttime,
                    latest_crttime,
                    duplicate_keyids,
                ) = row

                day_str = check_date.strftime("%Y%m%d")
                api_total = None
                api_flag = None
                if use_api and day_str in api_map:
                    api_total, api_flag = api_map.get(day_str, (None, None))

                # 判断数据状态（考虑 API total=1 但 data 为空的特殊情况）
                if record_count == 0:
                    if api_flag == "empty_data_but_total_1":
                        status = "异常-API_total1空"
                    else:
                        status = "缺失"
                elif duplicate_keyids > 0:
                    status = "异常-重复keyid"
                elif unique_keyids != record_count:
                    status = "异常-keyid不唯一"
                elif unique_grids < 100:  # 正常应该有很多格点
                    status = "可疑-格点数过少"
                else:
                    status = "正常"

                # 计算 delta：API_total - record_count
                delta = None
                if api_total is not None:
                    delta = api_total - record_count

                results.append(
                    {
                        "日期": check_date.strftime("%Y-%m-%d"),
                        "记录数": record_count,
                        "唯一keyid数": unique_keyids,
                        "唯一格点数": unique_grids,
                        "最早时间": (
                            earliest_crttime.strftime("%Y-%m-%d %H:%M:%S")
                            if earliest_crttime
                            else None
                        ),
                        "最晚时间": (
                            latest_crttime.strftime("%Y-%m-%d %H:%M:%S")
                            if latest_crttime
                            else None
                        ),
                        "重复keyid数": duplicate_keyids,
                        "API_total": api_total,
                        "delta": delta,
                        "API_flag": api_flag,
                        "状态": status,
                    }
                )

    # 保存为CSV
    df = pd.DataFrame(results)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    # 生成统计报告
    total_days = len(results)
    missing_days = len([r for r in results if r["状态"] == "缺失"])
    abnormal_days = len([r for r in results if r["状态"].startswith("异常")])
    suspicious_days = len([r for r in results if r["状态"].startswith("可疑")])
    normal_days = len([r for r in results if r["状态"] == "正常"])
    api_flagged_days = [
        r for r in results if r.get("API_flag") == "empty_data_but_total_1"
    ]
    # DB vs API 不一致的天（delta != 0）
    inconsistent_days = [
        r for r in results if r.get("delta") is not None and r.get("delta") != 0
    ]

    logger.info(f"\n{'='*60}")
    logger.info(f"气象格点数据审计报告")
    logger.info(f"{'='*60}")
    logger.info(f"审计日期范围: {start_date} 至 {end_date}")
    logger.info(f"总天数: {total_days}")
    logger.info(f"  - 正常: {normal_days} 天")
    logger.info(f"  - 缺失: {missing_days} 天")
    logger.info(f"  - 异常: {abnormal_days} 天")
    logger.info(f"  - 可疑: {suspicious_days} 天")
    logger.info(f"{'='*60}")
    logger.info(f"详细报告已保存至: {output_path}")

    if use_api:
        logger.info(
            f"API 参与判定：total=1 但 data 为空的天数共 {len(api_flagged_days)} 天"
        )

    # 列出缺失的日期
    if missing_days > 0:
        missing_list = [r["日期"] for r in results if r["状态"] == "缺失"]
        logger.warning(f"\n缺失的日期 ({len(missing_list)} 天):")
        for i in range(0, len(missing_list), 10):
            logger.warning(f"  {', '.join(missing_list[i:i+10])}")

    # 列出异常的日期
    if abnormal_days > 0:
        abnormal_list = [
            (r["日期"], r["状态"], r["记录数"])
            for r in results
            if r["状态"].startswith("异常")
        ]
        logger.error(f"\n异常的日期 ({len(abnormal_list)} 天):")
        for date_str, status, count in abnormal_list[:20]:
            logger.error(f"  {date_str}: {status} (记录数: {count})")

    # 列出 API 标记为 total=1 且 data 为空的日期（已排除在缺失外）
    if api_flagged_days:
        flagged_list = [r["日期"] for r in api_flagged_days]
        logger.warning(
            f"\nAPI 标记 total=1 但 data 为空的日期 ({len(flagged_list)} 天，归类为异常)："
        )
        for i in range(0, len(flagged_list), 10):
            logger.warning(f"  {', '.join(flagged_list[i:i+10])}")

    # 列出 DB 与 API 不一致的日期
    if inconsistent_days:
        logger.warning(
            f"\n数据库与 API 不一致的日期 ({len(inconsistent_days)} 天，delta ≠ 0)："
        )
        inconsistent_list = [
            f"{r['日期']} (DB={r['记录数']}, API={r['API_total']}, Δ={r['delta']})"
            for r in inconsistent_days[:30]
        ]
        for i in range(0, len(inconsistent_list), 3):
            logger.warning(f"  {'; '.join(inconsistent_list[i:i+3])}")
        if len(inconsistent_days) > 30:
            logger.warning(f"  … 还有 {len(inconsistent_days) - 30} 天")
    else:
        if use_api:
            logger.info("数据库与 API 数据一致（delta = 0）。")

    return df


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="审计气象格点数据完整性")
    parser.add_argument(
        "--start", type=str, default="20210101", help="开始日期 YYYYMMDD"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.now().strftime("%Y%m%d"),
        help="结束日期 YYYYMMDD（默认今天）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/audit/weather_grid_audit.csv",
        help="输出CSV文件路径",
    )

    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y%m%d").date()
    end_date = datetime.strptime(args.end, "%Y%m%d").date()

    logger.info(f"开始审计气象格点数据: {start_date} 至 {end_date}")

    asyncio.run(
        audit_weather_grid_completeness(
            start_date=start_date, end_date=end_date, output_file=args.output
        )
    )


if __name__ == "__main__":
    main()
