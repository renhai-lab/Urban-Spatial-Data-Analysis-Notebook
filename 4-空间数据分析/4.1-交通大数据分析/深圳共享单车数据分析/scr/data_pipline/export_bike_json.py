import json
import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import settings
from .coords import batch_convert


SQL = sql.SQL(
    """
SELECT
    user_id,
    company_id,
    start_time AT TIME ZONE 'Asia/Shanghai' AS start_time_cn,
    -- start_geom 为 GEOGRAPHY(Point,4326)，直接取经纬度
    ST_X(start_geom::geometry) AS lng,
    ST_Y(start_geom::geometry) AS lat
FROM {table}
WHERE DATE(start_time AT TIME ZONE 'Asia/Shanghai') = %s
    AND start_geom IS NOT NULL
LIMIT %s
"""
)


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _write_geojson_features(
    out_path: str, features: List[dict], name: str | None = None
) -> None:
    _ensure_dir(out_path)
    collection = {
        "type": "FeatureCollection",
        **({"name": name} if name else {}),
        "features": features,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False)
    print(f"导出完成：{out_path}，共 {len(features)} 条要素")


def _rows_to_features(rows: Iterable[dict]) -> List[dict]:
    features: List[dict] = []
    for r in rows:
        lng = r.get("lng")
        lat = r.get("lat")
        if lng is None or lat is None:
            continue
        st = r.get("start_time_cn")
        if st is None:
            start_time_str = None
        else:
            try:
                start_time_str = st.isoformat()  # type: ignore[attr-defined]
            except Exception:
                start_time_str = str(st)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lng), float(lat)],
                },
                "properties": {
                    "user_id": r.get("user_id"),
                    "company_id": r.get("company_id"),
                    "start_time": start_time_str,
                },
            }
        )
    return features


def _convert_features(features: List[dict], src: str, dst: str) -> List[dict]:
    coords = [tuple(f["geometry"]["coordinates"]) for f in features]  # type: ignore[index]
    converted = batch_convert(coords, src, dst)
    out: List[dict] = []
    for f, (lng, lat) in zip(features, converted):
        nf = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": dict(f.get("properties", {})),
        }
        out.append(nf)
    return out


def export_bike_points(day: date, limit: int = 200000) -> None:
    conn_str = settings.get_conn_str()
    table = settings.TABLE_NAME
    query = SQL.format(table=sql.Identifier(table))

    with psycopg.connect(conn_str) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (day, limit))
            rows = cur.fetchall()

    # 转为 GeoJSON-like features (geometry/properties)
    src_features = _rows_to_features(rows)

    export_dir = Path(settings.EXPORT_DIR)
    export_dir.mkdir(parents=True, exist_ok=True)
    day_str = day.isoformat()

    # 如果默认不是bd09 是gcj02

    # 1) 源坐标（按 settings.SOURCE_COORD 声明，默认 BD-09 地理坐标）
    bd_path = export_dir / f"bike_{day_str}gcj.bd09ll.geojson"
    _write_geojson_features(str(bd_path), src_features, name=f"bike_{day_str}_bd09ll")

    # # 2) 转 GCJ-02（高德）：严格使用百度 geoconv API（由 coords.batch_convert 内部处理）
    # gcj_features = _convert_features(
    #     src_features, src=settings.SOURCE_COORD, dst="gcj02"
    # )
    # gcj_path = export_dir / f"bike_{day_str}.gcj02.geojson"
    # _write_geojson_features(str(gcj_path), gcj_features, name=f"bike_{day_str}_gcj02")

    # 3) 转 WGS84：必须走 GCJ-02 -> WGS84（coordTransform_py），先基于已得 GCJ-02 再转
    try:
        wgs_features = _convert_features(src_features, src="gcj02", dst="wgs84")
    except NotImplementedError:
        # 若 coordTransform_py 未安装或不可用，明确报错
        raise
    wgs_path = export_dir / f"bike_{day_str}.wgs84.geojson"
    _write_geojson_features(
        str(wgs_path), wgs_features, name=f"bike_{day_str}_wgs84_test"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="导出指定日期（YYMMDD）的共享单车起点 GeoJSON（WGS84）"
    )
    parser.add_argument(
        "day",
        nargs="?",
        help="日期，格式 YYYYMMDD（如 20210101 表示 2021-01-01）",
        default=None,
    )
    args = parser.parse_args()

    if args.day:
        try:
            day_dt = datetime.strptime(args.day, "%Y%m%d").date()
        except ValueError:
            raise SystemExit(
                "日期格式错误：请使用 YYYYMMDD，例如 20210101 表示 2021-01-01"
            )
    else:
        # 兼容旧行为：未传参则导出 2021-01-01
        day_dt = date(2021, 1, 1)

    export_bike_points(day_dt)
