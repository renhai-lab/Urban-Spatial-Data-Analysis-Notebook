from __future__ import annotations

"""
按天导出共享单车数据到 data/share：
- CSV（zip 压缩）
- GeoJSON（zip 压缩；几何列按坐标集选择 raw/wgs84）
- Parquet（高压缩） 不导出
- GeoParquet（标准 GeoParquet，geometry=WKB；wgs84 集使用 OGC:CRS84，raw 集不声明 CRS） 不导出

时间：统一导出为北京时间字符串（YYYY-MM-DDTHH:MM:SS），列名 *_cn。
坐标：
- 可选择导出两套坐标之一（不混合）：
    - wgs84：start/end_lng_wgs84, start/end_lat_wgs84（来自 *_wgs84 或兼容旧列 *_geom）
    - raw：start/end_lng_raw, start/end_lat_raw（来自 *_geom_raw）

使用：
    uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 --sets raw,wgs84 --formats csv,geojson --batch 50000
"""

import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Iterable, List, Tuple
import json
import zipfile
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import settings


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def daterange(d1: date, d2: date) -> Iterable[date]:
    cur = d1
    one = timedelta(days=1)
    while cur <= d2:
        yield cur
        cur = cur + one


def _ensure_dirs(base: Path, coord_set: str) -> dict[str, Path]:
    root = base / coord_set
    geojson_zip = root / "geojson_zip"
    csv_zip = root / "csv_zip"
    for p in [geojson_zip, csv_zip]:
        p.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "geojson_zip": geojson_zip,
        "csv_zip": csv_zip,
    }


def _build_day_query(conn, table: str, coord_set: str, day: date):
    # 检查可用列，兼容旧列
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table,),
        )
        cols = {r[0] for r in cur.fetchall()}

    has_start_w = "start_geom_wgs84" in cols
    has_end_w = "end_geom_wgs84" in cols
    has_start = "start_geom" in cols
    has_end = "end_geom" in cols
    has_start_raw = "start_geom_raw" in cols
    has_end_raw = "end_geom_raw" in cols

    if coord_set == "wgs84":
        geom_start_expr = (
            "start_geom_wgs84" if has_start_w else ("start_geom" if has_start else None)
        )
        geom_end_expr = (
            "end_geom_wgs84" if has_end_w else ("end_geom" if has_end else None)
        )
        if not geom_start_expr:
            raise RuntimeError(
                "缺少 WGS84 或旧列起点坐标（start_geom_wgs84/start_geom）"
            )
        end_sel = (
            sql.SQL(
                "ST_X({end}::geometry) AS end_lng_wgs84, ST_Y({end}::geometry) AS end_lat_wgs84"
            ).format(end=sql.SQL(geom_end_expr))
            if geom_end_expr
            else sql.SQL(
                "NULL::double precision AS end_lng_wgs84, NULL::double precision AS end_lat_wgs84"
            )
        )
        lng_sel = sql.SQL(
            "ST_X({start}::geometry) AS start_lng_wgs84, ST_Y({start}::geometry) AS start_lat_wgs84,"
        ).format(start=sql.SQL(geom_start_expr))
        headers = [
            "user_id",
            "company_id",
            "start_time_cn",
            "end_time_cn",
            "start_lng_wgs84",
            "start_lat_wgs84",
            "end_lng_wgs84",
            "end_lat_wgs84",
        ]
    elif coord_set == "raw":
        if not has_start_raw:
            raise RuntimeError("缺少原始起点列 start_geom_raw")
        geom_start_expr = "start_geom_raw"
        geom_end_expr = "end_geom_raw" if has_end_raw else None
        end_sel = (
            sql.SQL(
                """
            CASE WHEN end_geom_raw   IS NOT NULL THEN ST_X(end_geom_raw)   END AS end_lng_raw,
            CASE WHEN end_geom_raw   IS NOT NULL THEN ST_Y(end_geom_raw)   END AS end_lat_raw,
            """
            )
            if geom_end_expr
            else sql.SQL(
                "NULL::double precision AS end_lng_raw, NULL::double precision AS end_lat_raw,"
            )
        )
        lng_sel = sql.SQL(
            """
            CASE WHEN start_geom_raw IS NOT NULL THEN ST_X(start_geom_raw) END AS start_lng_raw,
            CASE WHEN start_geom_raw IS NOT NULL THEN ST_Y(start_geom_raw) END AS start_lat_raw,
        """
        )
        headers = [
            "user_id",
            "company_id",
            "start_time_cn",
            "end_time_cn",
            "start_lng_raw",
            "start_lat_raw",
            "end_lng_raw",
            "end_lat_raw",
        ]
    else:
        raise ValueError("coord_set 仅支持 raw 或 wgs84")

    q = sql.SQL(
        """
        SELECT
            user_id,
            company_id,
            to_char(start_time AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD"T"HH24:MI:SS') AS start_time_cn,
            to_char(end_time   AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD"T"HH24:MI:SS')   AS end_time_cn,
            {lng_sel}
            {end_sel}
        FROM {table}
        WHERE DATE(start_time AT TIME ZONE 'Asia/Shanghai') = {day}
        """
    ).format(
        table=sql.Identifier(table),
        lng_sel=lng_sel,
        end_sel=end_sel,
        day=sql.Literal(day),
    )

    return q, headers


def _stream_query_geojson_to_zip(
    conn: psycopg.Connection,
    select_sql: sql.Composed,
    out_zip: Path,
    day_str: str,
    coord_set: str,
    batch: int,
    compress_level: int,
) -> int:
    # 直接写入 zip 成员，避免临时文件
    json_name = f"{day_str}.geojson"
    n = 0
    with zipfile.ZipFile(
        out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compress_level
    ) as zf:
        with zf.open(json_name, "w") as zfw_bin:
            zfw = io.TextIOWrapper(zfw_bin, encoding="utf-8")
            zfw.write(
                '{"type":"FeatureCollection","name":"bike_' + day_str + '","features":['
            )
            first = True
            with conn.cursor(name=f"geojson_{day_str}", row_factory=dict_row) as cur:
                cur.itersize = batch
                cur.execute(select_sql)
                while True:
                    rows = cur.fetchmany(batch)
                    if not rows:
                        break
                    for r in rows:
                        if coord_set == "wgs84":
                            lng = r.get("start_lng_wgs84")
                            lat = r.get("start_lat_wgs84")
                        else:
                            lng = r.get("start_lng_raw")
                            lat = r.get("start_lat_raw")
                        if lng is None or lat is None:
                            continue
                        feat = {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [float(lng), float(lat)],
                            },
                            "properties": {
                                "user_id": r.get("user_id"),
                                "company_id": r.get("company_id"),
                                "start_time": r.get("start_time_cn"),
                                "end_time": r.get("end_time_cn"),
                                **(
                                    {
                                        "start_lng_wgs84": r.get("start_lng_wgs84"),
                                        "start_lat_wgs84": r.get("start_lat_wgs84"),
                                        "end_lng_wgs84": r.get("end_lng_wgs84"),
                                        "end_lat_wgs84": r.get("end_lat_wgs84"),
                                    }
                                    if coord_set == "wgs84"
                                    else {
                                        "start_lng_raw": r.get("start_lng_raw"),
                                        "start_lat_raw": r.get("start_lat_raw"),
                                        "end_lng_raw": r.get("end_lng_raw"),
                                        "end_lat_raw": r.get("end_lat_raw"),
                                    }
                                ),
                            },
                        }
                        if not first:
                            zfw.write(",")
                        zfw.write(json.dumps(feat, ensure_ascii=False))
                        first = False
                        n += 1
            zfw.write("]}")
            zfw.flush()
    return n


def _copy_csv_to_zip(
    conn: psycopg.Connection,
    select_sql: sql.Composed,
    out_zip: Path,
    day_str: str,
    compress_level: int,
) -> int:
    # 使用 COPY 提升 CSV 导出速度，直接写入 zip 成员；返回导出数据行数
    csv_name = f"{day_str}.csv"
    row_count = 0
    with zipfile.ZipFile(
        out_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compress_level
    ) as zf:
        with zf.open(csv_name, "w") as zfw:
            with conn.cursor() as cur:
                copy_sql = sql.SQL("COPY ({sel}) TO STDOUT WITH CSV HEADER").format(
                    sel=select_sql
                )
                with cur.copy(copy_sql) as cp:
                    # COPY 输出是按行的 CSV 文本（\n 结尾），统计换行数减去表头行
                    first_chunk = True
                    while True:
                        chunk = cp.read()
                        if not chunk:
                            break
                        data = bytes(chunk)
                        zfw.write(data)
                        # 统计行数（LF）
                        row_count += data.count(b"\n")
                        if first_chunk:
                            # 第一行是 Header，占 1 行
                            if row_count > 0:
                                row_count -= 1
                            first_chunk = False
    return row_count


def export_day(
    day: date,
    formats: set[str],
    batch: int,
    share_dir: Path,
    coord_set: str,
    compress_level: int,
) -> dict[str, int]:
    dirs = _ensure_dirs(share_dir, coord_set)
    day_str = day.isoformat()
    table = settings.TABLE_NAME
    conn_str = settings.get_conn_str()

    results: dict[str, int] = {}
    # 先构造 SELECT 语句（使用短连接检查列存在并生成 SQL）
    with psycopg.connect(conn_str) as conn_build:
        select_sql, headers = _build_day_query(conn_build, table, coord_set, day)

    if "geojson" in formats:
        out_zip = dirs["geojson_zip"] / f"{day_str}.geojson.zip"
        with psycopg.connect(conn_str) as conn_gj:
            results["geojson"] = _stream_query_geojson_to_zip(
                conn_gj, select_sql, out_zip, day_str, coord_set, batch, compress_level
            )
    if "csv" in formats:
        out_zip = dirs["csv_zip"] / f"{day_str}.csv.zip"
        with psycopg.connect(conn_str) as conn_csv:
            results["csv"] = _copy_csv_to_zip(
                conn_csv, select_sql, out_zip, day_str, compress_level
            )

    return results


def main():
    ap = argparse.ArgumentParser(
        description="按天导出 CSV(zip)/GeoJSON(zip)（默认）；支持 raw/wgs84 两套坐标分开导出"
    )
    ap.add_argument("--start", required=True, help="起始日期 YYYYMMDD（北京时）")
    ap.add_argument("--end", required=True, help="结束日期 YYYYMMDD（北京时）")
    ap.add_argument(
        "--sets",
        default="wgs84",
        help="导出坐标集，逗号分隔：raw,wgs84（默认仅 wgs84）；会写入 data/share/<set>/...",
    )
    ap.add_argument(
        "--formats",
        default="csv,geojson",
        help="导出格式，逗号分隔：csv,geojson；默认仅 csv,geojson",
    )
    ap.add_argument("--batch", type=int, default=50000, help="单批行数（流式读取）")
    ap.add_argument("--out", default="data/share", help="输出根目录")
    ap.add_argument(
        "--workers",
        type=int,
        default=max(2, (os.cpu_count() or 4) // 2),
        help="并发导出线程数（默认 CPU/2，至少 2）",
    )
    ap.add_argument(
        "--zip-compress-level",
        type=int,
        default=6,
        help="zip 压缩等级 0-9（0=不压缩最快；9=最小体积最慢；默认 6）",
    )
    args = ap.parse_args()

    d1 = parse_day(args.start)
    d2 = parse_day(args.end)
    fmts = {s.strip().lower() for s in args.formats.split(",") if s.strip()}
    sets = [s.strip().lower() for s in args.sets.split(",") if s.strip()]
    for s in sets:
        if s not in {"raw", "wgs84"}:
            raise SystemExit("--sets 仅支持 raw,wgs84")
    share_dir = Path(args.out)
    share_dir.mkdir(parents=True, exist_ok=True)

    # 构造任务列表（按天 × 坐标集）
    tasks: List[Tuple[date, str]] = []
    cur = d1
    while cur <= d2:
        for s in sets:
            tasks.append((cur, s))
        cur = cur + timedelta(days=1)

    totals: dict[str, dict[str, int]] = {s: {k: 0 for k in fmts} for s in sets}

    # 并发执行导出任务
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {
            ex.submit(
                export_day, day, fmts, args.batch, share_dir, s, args.zip_compress_level
            ): (day, s)
            for (day, s) in tasks
        }
        for fut in as_completed(futs):
            day, s = futs[fut]
            try:
                res = fut.result()
                for k, v in res.items():
                    # 对于 CSV，我们现在能返回准确的行数
                    if isinstance(v, int) and v >= 0:
                        totals[s][k] = totals[s].get(k, 0) + v
                print(
                    f"{day.isoformat()} [{s}] 导出完成："
                    + ", ".join([f"{k}={res.get(k,'?')}" for k in fmts])
                )
            except Exception as e:
                print(f"{day.isoformat()} [{s}] 导出失败：{e}")

    print("汇总：", totals)


if __name__ == "__main__":
    main()
