"""
Coordinate conversion utilities constrained per requirements:
- Only use coordTransform_py for GCJ-02 -> WGS84.
- Use Baidu geoconv API for all other pairs (BD-09 <-> GCJ-02, BD-09 <-> WGS84, WGS84 <-> GCJ-02 if not the exact GCJ-02 -> WGS84 direction).
- If a requested conversion pair is not covered, raise NotImplementedError.
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

import requests

from eviltransform import gcj2wgs

from .config import settings


Coord = Tuple[float, float]


# ---- GCJ-02 -> WGS84 using coordTransform_py ----
def gcj02_to_wgs84(lng: float, lat: float) -> Coord:
    """Convert GCJ-02 coordinates to WGS84. 输出符合 lng lat的z坐标"""
    wlat, wlng = gcj2wgs(lat, lng)
    return wlng, wlat


def gcj02_to_wgs84_batch(coords: Sequence[Coord]) -> List[Coord]:
    return [gcj02_to_wgs84(lng, lat) for lng, lat in coords]


# ---- Baidu geoconv API (optional) ----
def baidu_geoconv_batch(
    coords: Sequence[Coord], from_type: int, to_type: int
) -> List[Coord]:
    """
    Call Baidu geoconv API to convert coordinates.
    from_type/to_type refer to:
      1: WGS84
      3: BD-09
      5: GCJ-02
    API docs: https://lbsyun.baidu.com/index.php?title=webapi/guide/changeposition
    """
    if not settings.BAIDU_AK:
        raise NotImplementedError("BAIDU_AK not configured for Baidu geoconv API")

    url = settings.BAIDU_GEOCONV_URL
    out: List[Coord] = []
    batch = settings.GEOCONV_BATCH_SIZE
    for i in range(0, len(coords), batch):
        chunk = coords[i : i + batch]
        # format: 'lng1,lat1;lng2,lat2;...'
        coords_str = ";".join(f"{x},{y}" for x, y in chunk)
        params = {
            "ak": settings.BAIDU_AK,
            "coords": coords_str,
            "from": str(from_type),
            "to": str(to_type),
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        j = r.json()
        if j.get("status") != 0:
            raise RuntimeError(f"geoconv failed: {j}")
        res = j.get("result", [])
        out.extend([(it["x"], it["y"]) for it in res])

        # respect QPS: simple sleep to keep <= QPS
        time.sleep(1.0 / max(1, settings.GEOCONV_QPS))

    return out


def batch_convert(coords: Sequence[Coord], src: str, dst: str) -> List[Coord]:
    """
    Convert coords from src to dst.
    Rules:
    - If src == dst: return as-is.
    - If src=='gcj02' and dst=='wgs84': use coordTransform_py.
    - Else: use Baidu geoconv API (requires BAIDU_AK).
    - If any pair not covered, raise NotImplementedError.
    """
    src = src.lower()
    dst = dst.lower()
    if src == dst:
        return list(coords)

    if src == "gcj02" and dst == "wgs84":
        return gcj02_to_wgs84_batch(coords)

    # Use Baidu geoconv API for all other pairs
    type_map = {"wgs84": 1, "bd09ll": 3, "gcj02": 5}
    if src not in type_map or dst not in type_map:
        raise NotImplementedError(f"Unsupported conversion {src}->{dst}")
    return baidu_geoconv_batch(coords, type_map[src], type_map[dst])
