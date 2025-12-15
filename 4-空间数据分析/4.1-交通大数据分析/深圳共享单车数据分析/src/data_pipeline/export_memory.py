"""
基于内存数据的高效导出模块
直接从获取的records导出CSV和GeoJSON，避免重复查询数据库
使用pandas/geopandas等高效库
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import zipfile
from datetime import date
import gc

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from loguru import logger

from .config import settings


def _ensure_export_dirs(
    base_path: Path, coord_sets: List[str]
) -> Dict[str, Dict[str, Path]]:
    """确保导出目录存在"""
    dirs = {}
    for coord_set in coord_sets:
        coord_dir = base_path / coord_set
        csv_dir = coord_dir / "csv_zip"
        geojson_dir = coord_dir / "geojson_zip"

        csv_dir.mkdir(parents=True, exist_ok=True)
        geojson_dir.mkdir(parents=True, exist_ok=True)

        dirs[coord_set] = {"csv": csv_dir, "geojson": geojson_dir}

    return dirs


def _records_to_dataframe(records: List[List[Any]], profile) -> pd.DataFrame:
    """将记录列表转换为DataFrame"""
    if not records:
        return pd.DataFrame()

    # 使用profile的copy_columns作为列名
    columns = profile.copy_columns
    df = pd.DataFrame(records, columns=columns)

    # 转换时间列为字符串格式（用于CSV导出）
    if "start_time" in df.columns:
        # 处理时区信息
        df["start_time"] = pd.to_datetime(df["start_time"])
        if df["start_time"].iloc[0].tz is None:
            df["start_time"] = df["start_time"].dt.tz_localize("UTC")
        df["start_time_cn"] = (
            df["start_time"]
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    if "end_time" in df.columns:
        # 处理时区信息
        df["end_time"] = pd.to_datetime(df["end_time"])
        if df["end_time"].iloc[0].tz is None:
            df["end_time"] = df["end_time"].dt.tz_localize("UTC")
        df["end_time_cn"] = (
            df["end_time"]
            .dt.tz_convert("Asia/Shanghai")
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    # 从几何对象中提取坐标
    if "start_geom_raw" in df.columns and df["start_geom_raw"].notna().any():
        df[["start_lng_raw", "start_lat_raw"]] = (
            df["start_geom_raw"].apply(_extract_coords_from_wkt).apply(pd.Series)
        )

    if "end_geom_raw" in df.columns and df["end_geom_raw"].notna().any():
        df[["end_lng_raw", "end_lat_raw"]] = (
            df["end_geom_raw"].apply(_extract_coords_from_wkt).apply(pd.Series)
        )

    if "start_geom_wgs84" in df.columns and df["start_geom_wgs84"].notna().any():
        df[["start_lng_wgs84", "start_lat_wgs84"]] = (
            df["start_geom_wgs84"].apply(_extract_coords_from_wkt).apply(pd.Series)
        )

    if "end_geom_wgs84" in df.columns and df["end_geom_wgs84"].notna().any():
        df[["end_lng_wgs84", "end_lat_wgs84"]] = (
            df["end_geom_wgs84"].apply(_extract_coords_from_wkt).apply(pd.Series)
        )

    return df


def _extract_coords_from_wkt(wkt_str):
    """从WKT字符串中提取坐标"""
    if pd.isna(wkt_str) or not wkt_str:
        return [None, None]

    try:
        # 解析WKT字符串，格式如：SRID=4326;POINT(114.1 22.5)
        if "POINT(" in wkt_str:
            # 提取POINT(lng lat)中的坐标
            point_part = wkt_str.split("POINT(")[1].split(")")[0]
            lng, lat = point_part.split(" ")
            return [float(lng), float(lat)]
    except Exception as e:
        logger.debug(f"解析WKT失败: {wkt_str}, 错误: {e}")

    return [None, None]


def _create_gdf_for_coord_set(df: pd.DataFrame, coord_set: str) -> gpd.GeoDataFrame:
    """为指定坐标系创建GeoDataFrame"""
    if df.empty:
        return gpd.GeoDataFrame()

    # 根据坐标系选择对应的坐标列
    if coord_set == "raw":
        lng_col = "start_lng_raw"
        lat_col = "start_lat_raw"
        end_lng_col = "end_lng_raw"
        end_lat_col = "end_lat_raw"
    elif coord_set == "wgs84":
        lng_col = "start_lng_wgs84"
        lat_col = "start_lat_wgs84"
        end_lng_col = "end_lng_wgs84"
        end_lat_col = "end_lat_wgs84"
    else:
        raise ValueError(f"不支持的坐标系: {coord_set}")

    # 检查必要的列是否存在
    if lng_col not in df.columns or lat_col not in df.columns:
        logger.warning(f"缺少{coord_set}坐标系的必要列: {lng_col}, {lat_col}")
        return gpd.GeoDataFrame()

    # 过滤掉坐标为空的记录
    valid_mask = df[lng_col].notna() & df[lat_col].notna()
    valid_df = df[valid_mask].copy()

    if valid_df.empty:
        logger.warning(f"{coord_set}坐标系无有效坐标数据")
        return gpd.GeoDataFrame()

    # 创建起点几何
    start_geometry = [
        Point(lng, lat) for lng, lat in zip(valid_df[lng_col], valid_df[lat_col])
    ]

    # 创建起点GeoDataFrame - 排除id字段
    start_props = valid_df[
        ["user_id", "company_id", "start_time_cn", "end_time_cn"]
    ].copy()
    start_props["point_type"] = "start"
    start_gdf = gpd.GeoDataFrame(start_props, geometry=start_geometry)

    # 如果有终点坐标，也创建终点数据
    end_features = []
    if end_lng_col in valid_df.columns and end_lat_col in valid_df.columns:
        end_valid_mask = valid_df[end_lng_col].notna() & valid_df[end_lat_col].notna()
        end_valid_df = valid_df[end_valid_mask]

        if not end_valid_df.empty:
            end_geometry = [
                Point(lng, lat)
                for lng, lat in zip(
                    end_valid_df[end_lng_col], end_valid_df[end_lat_col]
                )
            ]
            end_props = end_valid_df[
                ["user_id", "company_id", "start_time_cn", "end_time_cn"]
            ].copy()
            end_props["point_type"] = "end"
            end_gdf = gpd.GeoDataFrame(end_props, geometry=end_geometry)
            end_features.append(end_gdf)

    # 合并起点和终点
    if end_features:
        combined_gdf = gpd.GeoDataFrame(
            pd.concat([start_gdf] + end_features, ignore_index=True)
        )
    else:
        combined_gdf = start_gdf

    # 设置CRS
    if coord_set == "wgs84":
        combined_gdf.crs = "EPSG:4326"

    return combined_gdf


async def export_records_to_files(
    records: List[List[Any]],
    profile,
    target_date: date,
    export_base: Path,
    coord_sets: List[str] = ["raw", "wgs84"],
    formats: List[str] = ["csv", "geojson"],
) -> Dict[str, Any]:
    """
    直接从内存records导出文件
    """
    if not records:
        logger.info(f"{target_date} 无数据可导出")
        return {"total": 0, "coord_sets": {}}

    logger.info(
        f"开始导出 {target_date} 的 {len(records)} 条记录，坐标系: {coord_sets}，格式: {formats}"
    )

    # 确保输出目录存在
    dirs = _ensure_export_dirs(export_base, coord_sets)
    day_str = target_date.strftime("%Y%m%d")

    # 转换为DataFrame
    try:
        df = _records_to_dataframe(records, profile)
        logger.debug(f"转换为DataFrame成功，列: {list(df.columns)}")
    except Exception as e:
        logger.error(f"转换为DataFrame失败: {e}")
        return {"total": 0, "coord_sets": {}}

    stats = {"total": len(records), "coord_sets": {}}

    # 为每个坐标系并发导出
    export_tasks = []
    for coord_set in coord_sets:
        task = _export_coord_set(df, coord_set, day_str, dirs[coord_set], formats)
        export_tasks.append((coord_set, task))

    # 执行所有导出任务
    for coord_set, task in export_tasks:
        try:
            coord_stats = await task
            stats["coord_sets"][coord_set] = coord_stats
            if coord_stats["exported"] > 0:
                logger.info(
                    f"{target_date} {coord_set} 导出完成，共 {coord_stats['exported']} 条记录"
                )
        except Exception as e:
            logger.error(f"{target_date} {coord_set} 导出失败: {e}")
            stats["coord_sets"][coord_set] = {"exported": 0, "formats": []}

    # 清理内存
    del df
    gc.collect()

    return stats


async def _export_coord_set(
    df: pd.DataFrame,
    coord_set: str,
    day_str: str,
    coord_dirs: Dict[str, Path],
    formats: List[str],
) -> Dict[str, Any]:
    """导出单个坐标系的数据"""

    coord_stats = {"exported": 0, "formats": []}

    # 导出CSV
    if "csv" in formats:
        try:
            await _export_csv(df, coord_set, day_str, coord_dirs["csv"])
            coord_stats["formats"].append(
                f"CSV: {coord_dirs['csv']}/bike_data_{day_str}_{coord_set}.zip"
            )
            coord_stats["exported"] = len(df)
        except Exception as e:
            logger.error(f"CSV导出失败: {e}")

    # 导出GeoJSON
    if "geojson" in formats:
        try:
            exported_count = await _export_geojson(
                df, coord_set, day_str, coord_dirs["geojson"]
            )
            coord_stats["formats"].append(
                f"GeoJSON: {coord_dirs['geojson']}/bike_data_{day_str}_{coord_set}.zip"
            )
            if coord_stats["exported"] == 0:  # 如果CSV没有导出，使用GeoJSON的计数
                coord_stats["exported"] = exported_count
        except Exception as e:
            logger.error(f"GeoJSON导出失败: {e}")

    return coord_stats


async def _export_csv(df: pd.DataFrame, coord_set: str, day_str: str, output_dir: Path):
    """导出CSV格式"""
    csv_file = output_dir / f"bike_data_{day_str}_{coord_set}.csv"
    zip_file = output_dir / f"bike_data_{day_str}_{coord_set}.zip"

    # 根据坐标系选择相关列
    if coord_set == "raw":
        coord_cols = ["start_lng_raw", "start_lat_raw", "end_lng_raw", "end_lat_raw"]
    else:  # wgs84
        coord_cols = [
            "start_lng_wgs84",
            "start_lat_wgs84",
            "end_lng_wgs84",
            "end_lat_wgs84",
        ]

    # 选择要导出的列 - 只选择存在的列，排除id字段
    base_cols = ["user_id", "company_id", "start_time_cn", "end_time_cn"]
    available_cols = [col for col in base_cols if col in df.columns]
    available_coord_cols = [col for col in coord_cols if col in df.columns]

    export_cols = available_cols + available_coord_cols

    if not export_cols:
        logger.warning(f"没有可导出的列用于 {coord_set} 坐标系")
        return

    export_df = df[export_cols].copy()

    # 导出CSV
    export_df.to_csv(csv_file, index=False, encoding="utf-8")

    # 压缩
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(csv_file, csv_file.name)

    # 删除原始文件
    csv_file.unlink()

    logger.debug(f"CSV导出完成: {zip_file}")


async def _export_geojson(
    df: pd.DataFrame, coord_set: str, day_str: str, output_dir: Path
) -> int:
    """导出GeoJSON格式"""
    geojson_file = output_dir / f"bike_data_{day_str}_{coord_set}.geojson"
    zip_file = output_dir / f"bike_data_{day_str}_{coord_set}.zip"

    # 创建GeoDataFrame
    gdf = _create_gdf_for_coord_set(df, coord_set)

    if gdf.empty:
        logger.warning(f"{coord_set} 坐标系无有效几何数据")
        return 0

    # 导出GeoJSON
    gdf.to_file(geojson_file, driver="GeoJSON", encoding="utf-8")

    # 压缩
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(geojson_file, geojson_file.name)

    # 删除原始文件
    geojson_file.unlink()

    logger.debug(f"GeoJSON导出完成: {zip_file}")
    return len(gdf)
