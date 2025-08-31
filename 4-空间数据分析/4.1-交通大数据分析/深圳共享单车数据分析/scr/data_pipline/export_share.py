"""
优化版本的按天导出功能，支持raw和wgs84两套坐标系
参考原始export_share.py的逻辑
"""

from __future__ import annotations

import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Tuple, Optional
import json
import zipfile
import io
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from loguru import logger

from .config import settings


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _ensure_dirs(
    base: Path, coord_sets: List[str] = ["raw", "wgs84"]
) -> dict[str, dict[str, Path]]:
    """确保导出目录存在，支持多套坐标系"""
    dirs = {}
    for coord_set in coord_sets:
        coord_dir = base / coord_set
        geojson_dir = coord_dir / "geojson_zip"
        csv_dir = coord_dir / "csv_zip"
        for p in [geojson_dir, csv_dir]:
            p.mkdir(parents=True, exist_ok=True)
        dirs[coord_set] = {
            "geojson": geojson_dir,
            "csv": csv_dir,
        }
    return dirs


def _build_day_query(conn, table: str, coord_set: str, day: date):
    """构建查询某天数据的SQL，支持raw和wgs84两套坐标"""
    # 检查表结构
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            """,
            (table,),
        )
        cols = {r[0] for r in cur.fetchall()}

    # 检查可用的坐标列
    has_start_raw = "start_geom_raw" in cols
    has_end_raw = "end_geom_raw" in cols
    has_start_wgs84 = "start_geom_wgs84" in cols
    has_end_wgs84 = "end_geom_wgs84" in cols

    # 兼容旧列名
    has_start = "start_geom" in cols
    has_end = "end_geom" in cols

    if coord_set == "raw":
        # 导出原始坐标
        if not has_start_raw and not has_start:
            raise RuntimeError(
                f"表 {table} 缺少原始坐标列（start_geom_raw/start_geom）"
            )

        start_geom_expr = "start_geom_raw" if has_start_raw else "start_geom"
        end_geom_expr = (
            "end_geom_raw" if has_end_raw else ("end_geom" if has_end else None)
        )

        start_coords = sql.SQL(
            "ST_X({start}::geometry) AS start_lng_raw, ST_Y({start}::geometry) AS start_lat_raw"
        ).format(start=sql.Identifier(start_geom_expr))

        if end_geom_expr:
            end_coords = sql.SQL(
                "ST_X({end}::geometry) AS end_lng_raw, ST_Y({end}::geometry) AS end_lat_raw"
            ).format(end=sql.Identifier(end_geom_expr))
        else:
            end_coords = sql.SQL(
                "NULL::double precision AS end_lng_raw, NULL::double precision AS end_lat_raw"
            )

    elif coord_set == "wgs84":
        # 导出WGS84坐标
        if not has_start_wgs84 and not has_start:
            raise RuntimeError(
                f"表 {table} 缺少WGS84坐标列（start_geom_wgs84/start_geom）"
            )

        start_geom_expr = "start_geom_wgs84" if has_start_wgs84 else "start_geom"
        end_geom_expr = (
            "end_geom_wgs84" if has_end_wgs84 else ("end_geom" if has_end else None)
        )

        start_coords = sql.SQL(
            "ST_X({start}::geometry) AS start_lng_wgs84, ST_Y({start}::geometry) AS start_lat_wgs84"
        ).format(start=sql.Identifier(start_geom_expr))

        if end_geom_expr:
            end_coords = sql.SQL(
                "ST_X({end}::geometry) AS end_lng_wgs84, ST_Y({end}::geometry) AS end_lat_wgs84"
            ).format(end=sql.Identifier(end_geom_expr))
        else:
            end_coords = sql.SQL(
                "NULL::double precision AS end_lng_wgs84, NULL::double precision AS end_lat_wgs84"
            )
    else:
        raise ValueError(f"不支持的坐标系: {coord_set}")

    # 构建完整查询
    query = sql.SQL(
        """
        SELECT 
            id,
            user_id,
            company_id,
            (start_time AT TIME ZONE 'Asia/Shanghai')::text AS start_time_cn,
            (end_time AT TIME ZONE 'Asia/Shanghai')::text AS end_time_cn,
            {start_coords},
            {end_coords}
        FROM {table}
        WHERE (start_time AT TIME ZONE 'Asia/Shanghai')::date = %s
        ORDER BY start_time
    """
    ).format(
        table=sql.Identifier(table), start_coords=start_coords, end_coords=end_coords
    )

    return query


def export_day(
    conn_str: str,
    table: str,
    day: date,
    output_base: Path,
    coord_sets: List[str] = ["raw", "wgs84"],
    formats: List[str] = ["csv", "geojson"],
    batch_size: int = 50000,
) -> dict:
    """导出某天的数据为CSV和GeoJSON格式，支持多套坐标系"""

    dirs = _ensure_dirs(output_base, coord_sets)
    day_str = day.strftime("%Y%m%d")
    stats = {"total": 0, "coord_sets": {}}

    logger.info(f"开始导出 {day_str} 的数据，坐标系: {coord_sets}，格式: {formats}")

    with psycopg.connect(conn_str) as conn:
        for coord_set in coord_sets:
            stats["coord_sets"][coord_set] = {"exported": 0, "formats": []}

            try:
                query = _build_day_query(conn, table, coord_set, day)

                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, (day,))

                    # 分批处理数据
                    all_rows = []
                    while True:
                        rows = cur.fetchmany(batch_size)
                        if not rows:
                            break
                        all_rows.extend(rows)

                    if coord_set == coord_sets[0]:  # 只在第一个坐标系时设置总数
                        stats["total"] = len(all_rows)

                    if not all_rows:
                        logger.info(f"{day_str} {coord_set} 坐标系无数据")
                        continue

                    # 导出CSV
                    if "csv" in formats:
                        try:
                            csv_file = (
                                dirs[coord_set]["csv"] / f"bike_data_{day_str}.csv"
                            )
                            csv_zip_file = (
                                dirs[coord_set]["csv"] / f"bike_data_{day_str}.zip"
                            )

                            # 写入CSV
                            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                                if all_rows:
                                    fieldnames = list(all_rows[0].keys())
                                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                                    writer.writeheader()
                                    for row in all_rows:
                                        writer.writerow(row)

                            # 压缩CSV
                            with zipfile.ZipFile(
                                csv_zip_file, "w", zipfile.ZIP_DEFLATED
                            ) as zf:
                                zf.write(csv_file, csv_file.name)

                            # 删除原始CSV文件
                            csv_file.unlink()

                            stats["coord_sets"][coord_set]["formats"].append(
                                f"CSV: {csv_zip_file}"
                            )
                            logger.debug(f"{coord_set} CSV导出完成: {csv_zip_file}")

                        except Exception as e:
                            logger.error(f"{coord_set} CSV导出失败: {e}")

                    # 导出GeoJSON
                    if "geojson" in formats:
                        try:
                            geojson_file = (
                                dirs[coord_set]["geojson"]
                                / f"bike_data_{day_str}.geojson"
                            )
                            geojson_zip_file = (
                                dirs[coord_set]["geojson"] / f"bike_data_{day_str}.zip"
                            )

                            features = []

                            # 根据坐标系确定字段名
                            if coord_set == "raw":
                                start_lng_field = "start_lng_raw"
                                start_lat_field = "start_lat_raw"
                                end_lng_field = "end_lng_raw"
                                end_lat_field = "end_lat_raw"
                            else:  # wgs84
                                start_lng_field = "start_lng_wgs84"
                                start_lat_field = "start_lat_wgs84"
                                end_lng_field = "end_lng_wgs84"
                                end_lat_field = "end_lat_wgs84"

                            for row in all_rows:
                                # 跳过没有坐标的记录
                                if (
                                    row.get(start_lng_field) is None
                                    or row.get(start_lat_field) is None
                                ):
                                    continue

                                # 创建起点feature
                                start_feature = {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Point",
                                        "coordinates": [
                                            row[start_lng_field],
                                            row[start_lat_field],
                                        ],
                                    },
                                    "properties": {
                                        "id": row["id"],
                                        "user_id": row["user_id"],
                                        "company_id": row["company_id"],
                                        "start_time_cn": row["start_time_cn"],
                                        "end_time_cn": row["end_time_cn"],
                                        "point_type": "start",
                                    },
                                }
                                features.append(start_feature)

                                # 如果有终点坐标，也创建终点feature
                                if (
                                    row.get(end_lng_field) is not None
                                    and row.get(end_lat_field) is not None
                                ):
                                    end_feature = {
                                        "type": "Feature",
                                        "geometry": {
                                            "type": "Point",
                                            "coordinates": [
                                                row[end_lng_field],
                                                row[end_lat_field],
                                            ],
                                        },
                                        "properties": {
                                            "id": row["id"],
                                            "user_id": row["user_id"],
                                            "company_id": row["company_id"],
                                            "start_time_cn": row["start_time_cn"],
                                            "end_time_cn": row["end_time_cn"],
                                            "point_type": "end",
                                        },
                                    }
                                    features.append(end_feature)

                            # 根据坐标系设置CRS
                            if coord_set == "wgs84":
                                crs = {
                                    "type": "name",
                                    "properties": {"name": "EPSG:4326"},
                                }
                            else:
                                # raw坐标系不指定CRS（因为可能是GCJ-02等）
                                crs = None

                            geojson = {
                                "type": "FeatureCollection",
                                "features": features,
                            }

                            if crs:
                                geojson["crs"] = crs

                            # 写入GeoJSON
                            with open(geojson_file, "w", encoding="utf-8") as f:
                                json.dump(
                                    geojson,
                                    f,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )

                            # 压缩GeoJSON
                            with zipfile.ZipFile(
                                geojson_zip_file, "w", zipfile.ZIP_DEFLATED
                            ) as zf:
                                zf.write(geojson_file, geojson_file.name)

                            # 删除原始GeoJSON文件
                            geojson_file.unlink()

                            stats["coord_sets"][coord_set]["formats"].append(
                                f"GeoJSON: {geojson_zip_file}"
                            )
                            logger.debug(
                                f"{coord_set} GeoJSON导出完成: {geojson_zip_file}"
                            )

                        except Exception as e:
                            logger.error(f"{coord_set} GeoJSON导出失败: {e}")

                    stats["coord_sets"][coord_set]["exported"] = len(all_rows)
                    logger.info(
                        f"{day_str} {coord_set} 导出完成，共 {len(all_rows)} 条记录"
                    )

            except Exception as e:
                logger.error(f"{day_str} {coord_set} 坐标系导出失败: {e}")

    return stats


def export_date_range(
    conn_str: str,
    table: str,
    start_date: date,
    end_date: date,
    output_base: Optional[Path] = None,
    coord_sets: List[str] = ["raw", "wgs84"],
    formats: List[str] = ["csv", "geojson"],
    batch_size: int = 50000,
    max_workers: int = 4,
) -> dict:
    """导出日期范围内的数据"""

    if output_base is None:
        output_base = Path("data/share")

    output_base.mkdir(parents=True, exist_ok=True)

    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    logger.info(
        f"开始导出 {len(dates)} 天的数据，坐标系: {coord_sets}，格式: {formats}"
    )

    total_stats = {
        "total_days": len(dates),
        "successful_days": 0,
        "total_records": 0,
        "failed_days": [],
        "coord_sets": {coord_set: {"total_records": 0} for coord_set in coord_sets},
    }

    # 并发导出
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_date = {
            executor.submit(
                export_day,
                conn_str,
                table,
                day,
                output_base,
                coord_sets,
                formats,
                batch_size,
            ): day
            for day in dates
        }

        for future in as_completed(future_to_date):
            day = future_to_date[future]
            try:
                stats = future.result()
                total_stats["successful_days"] += 1
                total_stats["total_records"] += stats["total"]

                for coord_set in coord_sets:
                    if coord_set in stats["coord_sets"]:
                        total_stats["coord_sets"][coord_set]["total_records"] += stats[
                            "coord_sets"
                        ][coord_set]["exported"]

            except Exception as e:
                logger.error(f"导出 {day} 失败: {e}")
                total_stats["failed_days"].append(str(day))

    logger.success(
        f"导出完成！成功: {total_stats['successful_days']}/{total_stats['total_days']} 天"
    )
    for coord_set in coord_sets:
        count = total_stats["coord_sets"][coord_set]["total_records"]
        logger.info(f"{coord_set} 坐标系总记录: {count:,}")

    if total_stats["failed_days"]:
        logger.warning(f"失败的日期: {total_stats['failed_days']}")

    return total_stats


if __name__ == "__main__":
    """命令行测试"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    ap.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    ap.add_argument("--table", default="shenzhen_rides", help="表名")
    ap.add_argument("--coord-sets", default="raw,wgs84", help="坐标系")
    ap.add_argument("--formats", default="csv,geojson", help="导出格式")
    ap.add_argument("--output", default="data/share", help="输出目录")
    ap.add_argument("--batch", type=int, default=50000, help="批处理大小")
    ap.add_argument("--workers", type=int, default=4, help="并发数")

    args = ap.parse_args()

    start_date = parse_day(args.start)
    end_date = parse_day(args.end)
    coord_sets = [f.strip() for f in args.coord_sets.split(",")]
    formats = [f.strip() for f in args.formats.split(",")]

    conn_str = settings.get_conn_str()

    export_date_range(
        conn_str=conn_str,
        table=args.table,
        start_date=start_date,
        end_date=end_date,
        output_base=Path(args.output),
        coord_sets=coord_sets,
        formats=formats,
        batch_size=args.batch,
        max_workers=args.workers,
    )
