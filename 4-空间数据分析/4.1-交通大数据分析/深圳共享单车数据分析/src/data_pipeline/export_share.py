"""
优化版本的按天导出功能，支持多数据集和多坐标系
参考原始export_share.py的逻辑，并增加内存优化、并发处理和多profile支持

支持特性：
- 多坐标系导出（raw/wgs84）
- 多数据集导出（共享单车、气象数据等）
- CSV 和 GeoJSON 格式导出
- 内存优化和流式处理
- 按 profile 动态适配导出逻辑
"""

from __future__ import annotations

import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import json
import zipfile
import io
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
import os
import gc
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from loguru import logger

from .config import settings
from .profiles import get_profile, DatasetProfile


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _ensure_dirs(
    base: Path, coord_sets: Optional[List[str]] = None
) -> dict[str, dict[str, Path]]:
    """
    确保导出目录存在，支持多套坐标系或无坐标系

    Args:
        base: 基础导出目录
        coord_sets: 坐标系列表，如果为 None 则创建无坐标系的目录结构

    Returns:
        目录结构映射
    """
    if coord_sets is None:
        # 无坐标系（如天气数据），直接在基础目录下创建格式目录
        dirs = {}
        for fmt in ["csv", "geojson"]:
            fmt_dir = base / f"{fmt}_zip"
            fmt_dir.mkdir(parents=True, exist_ok=True)
            dirs[fmt] = fmt_dir
        return {"no_coord": dirs}

    # 多坐标系支持（如共享单车数据）
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


@contextmanager
def get_db_cursor(conn_str: str):
    """获取数据库游标的上下文管理器"""
    conn = None
    try:
        conn = psycopg.connect(conn_str)
        yield conn
    finally:
        if conn:
            conn.close()


def _export_csv_stream(
    conn_str: str,
    query,
    day: date,
    csv_file: Path,
    csv_zip_file: Path,
    coord_set: str,
    batch_size: int = 50000,
) -> int:
    """流式导出CSV格式"""
    record_count = 0

    with get_db_cursor(conn_str) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (day,))

            # 先写入临时文件，然后压缩
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = None

                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break

                    # 初始化writer（在第一批数据时）
                    if writer is None and rows:
                        fieldnames = list(rows[0].keys())
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()

                    # 写入数据
                    if writer is not None:
                        for row in rows:
                            writer.writerow(row)
                            record_count += 1

                    # 每批处理后清理内存
                    del rows
                    gc.collect()

    # 压缩文件
    if record_count > 0:
        with zipfile.ZipFile(csv_zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(csv_file, csv_file.name)
        csv_file.unlink()  # 删除原始文件

    return record_count


def _export_geojson_stream(
    conn_str: str,
    query,
    day: date,
    geojson_file: Path,
    geojson_zip_file: Path,
    coord_set: str,
    batch_size: int = 50000,
) -> int:
    """流式导出GeoJSON格式"""
    record_count = 0

    with get_db_cursor(conn_str) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (day,))

            # 确定字段名
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

            # 分批处理并写入GeoJSON
            features = []

            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break

                # 转换为GeoJSON features
                for row in rows:
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
                            "coordinates": [row[start_lng_field], row[start_lat_field]],
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
                    record_count += 1

                    # 如果有终点坐标，也创建终点feature
                    if (
                        row.get(end_lng_field) is not None
                        and row.get(end_lat_field) is not None
                    ):
                        end_feature = {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [row[end_lng_field], row[end_lat_field]],
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
                        record_count += 1

                # 清理内存
                del rows
                gc.collect()

            # 写入GeoJSON文件
            if features:
                # 根据坐标系设置CRS
                if coord_set == "wgs84":
                    crs = {"type": "name", "properties": {"name": "EPSG:4326"}}
                else:
                    crs = None

                geojson = {"type": "FeatureCollection", "features": features}
                if crs:
                    geojson["crs"] = crs

                with open(geojson_file, "w", encoding="utf-8") as f:
                    json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))

                # 压缩文件
                with zipfile.ZipFile(geojson_zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(geojson_file, geojson_file.name)
                geojson_file.unlink()  # 删除原始文件

    return record_count


def export_day(
    conn_str: str,
    table: str,
    day: date,
    output_base: Path,
    coord_sets: List[str] = ["raw", "wgs84"],
    formats: List[str] = ["csv", "geojson"],
    batch_size: int = 50000,
) -> dict:
    """导出某天的数据为CSV和GeoJSON格式，支持多套坐标系和流式处理"""

    dirs = _ensure_dirs(output_base, coord_sets)
    day_str = day.strftime("%Y%m%d")
    stats = {"total": 0, "coord_sets": {}}

    logger.info(f"开始导出 {day_str} 的数据，坐标系: {coord_sets}，格式: {formats}")

    # 使用线程池并发处理不同坐标系和格式的组合
    max_workers = min(len(coord_sets) * len(formats), settings.EXPORT_MAX_WORKERS)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []

        for coord_set in coord_sets:
            stats["coord_sets"][coord_set] = {"exported": 0, "formats": []}

            try:
                # 构建查询
                with get_db_cursor(conn_str) as conn:
                    query = _build_day_query(conn, table, coord_set, day)

                # 为每种格式创建导出任务
                for format_type in formats:
                    if format_type == "csv":
                        csv_file = (
                            dirs[coord_set]["csv"]
                            / f"bike_data_{day_str}_{coord_set}.csv"
                        )
                        csv_zip_file = (
                            dirs[coord_set]["csv"]
                            / f"bike_data_{day_str}_{coord_set}.zip"
                        )

                        future = executor.submit(
                            _export_csv_stream,
                            conn_str,
                            query,
                            day,
                            csv_file,
                            csv_zip_file,
                            coord_set,
                            batch_size,
                        )
                        futures.append((future, coord_set, format_type, csv_zip_file))

                    elif format_type == "geojson":
                        geojson_file = (
                            dirs[coord_set]["geojson"]
                            / f"bike_data_{day_str}_{coord_set}.geojson"
                        )
                        geojson_zip_file = (
                            dirs[coord_set]["geojson"]
                            / f"bike_data_{day_str}_{coord_set}.zip"
                        )

                        future = executor.submit(
                            _export_geojson_stream,
                            conn_str,
                            query,
                            day,
                            geojson_file,
                            geojson_zip_file,
                            coord_set,
                            batch_size,
                        )
                        futures.append(
                            (future, coord_set, format_type, geojson_zip_file)
                        )

            except Exception as e:
                logger.error(f"{day_str} {coord_set} 坐标系查询构建失败: {e}")
                continue

        # 收集结果
        for future, coord_set, format_type, output_file in futures:
            try:
                record_count = future.result()
                if record_count > 0:
                    stats["coord_sets"][coord_set]["exported"] = max(
                        stats["coord_sets"][coord_set]["exported"], record_count
                    )
                    stats["coord_sets"][coord_set]["formats"].append(
                        f"{format_type.upper()}: {output_file}"
                    )
                    logger.debug(
                        f"{coord_set} {format_type.upper()}导出完成: {output_file}"
                    )
                else:
                    logger.info(f"{day_str} {coord_set} {format_type} 无数据")

            except Exception as e:
                logger.error(f"{coord_set} {format_type.upper()}导出失败: {e}")

    # 更新总计
    if coord_sets:
        stats["total"] = max(stats["coord_sets"][cs]["exported"] for cs in coord_sets)

    for coord_set in coord_sets:
        exported = stats["coord_sets"][coord_set]["exported"]
        if exported > 0:
            logger.info(f"{day_str} {coord_set} 导出完成，共 {exported} 条记录")

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
    max_workers: Optional[int] = None,
) -> dict:
    """导出日期范围内的数据"""

    if output_base is None:
        output_base = Path("data/share")

    if max_workers is None:
        max_workers = settings.EXPORT_MAX_WORKERS

    output_base.mkdir(parents=True, exist_ok=True)

    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    logger.info(
        f"开始导出 {len(dates)} 天的数据，坐标系: {coord_sets}，格式: {formats}，"
        f"最大并发数: {max_workers}"
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
    """命令行工具 - 支持多 profile 导出"""
    ap = argparse.ArgumentParser(
        description="按天导出数据为 CSV 和 GeoJSON 格式，支持多数据集和多坐标系"
    )
    ap.add_argument(
        "--profile",
        default="bike",
        choices=["bike", "weather_grid"],
        help="数据集配置（默认: bike 共享单车）",
    )
    ap.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    ap.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    ap.add_argument("--table", default="", help="表名（留空则使用 profile 中的表名）")
    ap.add_argument(
        "--coord-sets", default="", help="坐标系，逗号分隔（留空则使用 profile 配置）"
    )
    ap.add_argument("--formats", default="csv,geojson", help="导出格式，逗号分隔")
    ap.add_argument("--output", default="data/share", help="输出目录")
    ap.add_argument("--batch", type=int, default=50000, help="批处理大小")
    ap.add_argument(
        "--workers", type=int, default=settings.EXPORT_MAX_WORKERS, help="并发数"
    )

    args = ap.parse_args()

    # 加载 profile 配置
    profile = get_profile(args.profile)
    logger.info(f"使用数据集配置: {profile.name}")

    start_date = parse_day(args.start)
    end_date = parse_day(args.end)

    # 使用 profile 中的表名（如果未指定）
    table = args.table or profile.table_name

    # 确定坐标系
    if args.coord_sets:
        # 用户指定了坐标系
        coord_sets = [f.strip() for f in args.coord_sets.split(",") if f.strip()]
    elif profile.export_support_coord_sets:
        # 使用 profile 默认的坐标系（共享单车默认 raw, wgs84）
        coord_sets = ["raw", "wgs84"]
    else:
        # 无坐标系（天气数据）
        coord_sets = None

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    conn_str = settings.get_conn_str()

    logger.info(f"表名: {table}")
    logger.info(f"坐标系: {coord_sets if coord_sets else '无（仅导出属性数据）'}")
    logger.info(f"格式: {formats}")
    logger.info(f"日期范围: {start_date} 到 {end_date}")

    export_date_range(
        conn_str=conn_str,
        table=table,
        start_date=start_date,
        end_date=end_date,
        output_base=Path(args.output),
        coord_sets=coord_sets,
        formats=formats,
        batch_size=args.batch,
        max_workers=args.workers,
    )
