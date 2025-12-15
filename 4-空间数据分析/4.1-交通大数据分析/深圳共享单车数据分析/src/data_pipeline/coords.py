"""
坐标系转换工具模块

该模块提供中国常用坐标系之间的转换功能，主要包括：
- GCJ-02（国家测绘局坐标系，火星坐标系）
- WGS84（世界标准坐标系，GPS坐标系）
- BD-09（百度坐标系）

转换策略：
- GCJ-02 -> WGS84：使用 eviltransform 库进行本地转换（推荐）
- 其他转换：使用百度地图 geoconv API（需要配置 BAIDU_AK）
- 如果请求的转换对不支持，将抛出 NotImplementedError

注意：
- 本地转换速度快且无需网络，推荐用于 GCJ-02 -> WGS84
- API 转换需要网络连接和有效的百度地图密钥
- 百度 API 有 QPS 限制和批量大小限制
"""

from __future__ import annotations

import time
from typing import List, Sequence, Tuple

import requests

from eviltransform import gcj2wgs

from .config import settings

# ===== 类型定义 =====
Coord = Tuple[float, float]  # 坐标元组：(经度, 纬度)


# ===== GCJ-02 -> WGS84 本地转换 =====
def gcj02_to_wgs84(lng: float, lat: float) -> Coord:
    """
    将 GCJ-02 坐标转换为 WGS84 坐标
    
    使用 eviltransform 库进行本地转换，无需网络连接，
    转换精度满足大多数应用场景需求。
    
    Args:
        lng: GCJ-02 经度
        lat: GCJ-02 纬度
        
    Returns:
        Coord: WGS84 坐标元组 (经度, 纬度)
        
    Example:
        >>> gcj02_to_wgs84(114.057868, 22.543099)
        (114.052, 22.537)
    """
    wlat, wlng = gcj2wgs(lat, lng)  # eviltransform 返回 (lat, lng)
    return wlng, wlat  # 统一返回 (lng, lat)


def gcj02_to_wgs84_batch(coords: Sequence[Coord]) -> List[Coord]:
    """
    批量转换 GCJ-02 坐标到 WGS84
    
    Args:
        coords: GCJ-02 坐标序列，格式为 [(lng, lat), ...]
        
    Returns:
        List[Coord]: WGS84 坐标列表
    """
    return [gcj02_to_wgs84(lng, lat) for lng, lat in coords]


# ===== 百度地图 geoconv API 转换（需要网络） =====
def baidu_geoconv_batch(
    coords: Sequence[Coord], from_type: int, to_type: int
) -> List[Coord]:
    """
    使用百度地图 geoconv API 进行批量坐标转换
    
    坐标系类型码：
    - 1: WGS84（GPS 标准坐标系）
    - 3: BD-09（百度坐标系）
    - 5: GCJ-02（国家测绘局坐标系，火星坐标系）
    
    Args:
        coords: 源坐标序列，格式为 [(lng, lat), ...]
        from_type: 源坐标系类型码
        to_type: 目标坐标系类型码
        
    Returns:
        List[Coord]: 转换后的坐标列表
        
    Raises:
        NotImplementedError: 如果未配置 BAIDU_AK
        RuntimeError: 如果 API 调用失败
        
    Note:
        - 需要配置有效的百度地图 API 密钥（BAIDU_AK）
        - 遵守 API QPS 限制，自动添加延迟
        - 每次最多转换 100 个坐标点
        
    参考文档：https://lbsyun.baidu.com/index.php?title=webapi/guide/changeposition
    """
    if not settings.BAIDU_AK:
        raise NotImplementedError("未配置 BAIDU_AK，无法使用百度地图坐标转换 API")

    url = settings.BAIDU_GEOCONV_URL
    out: List[Coord] = []
    batch = settings.GEOCONV_BATCH_SIZE
    
    # 分批处理，每批最多处理指定数量的坐标点
    for i in range(0, len(coords), batch):
        chunk = coords[i : i + batch]
        # 格式化坐标为 API 要求的字符串格式: 'lng1,lat1;lng2,lat2;...'
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
            raise RuntimeError(f"百度坐标转换 API 调用失败: {j}")
            
        res = j.get("result", [])
        out.extend([(it["x"], it["y"]) for it in res])

        # 遵守 QPS 限制，添加适当延迟
        time.sleep(1.0 / max(1, settings.GEOCONV_QPS))

    return out


def batch_convert(coords: Sequence[Coord], src: str, dst: str) -> List[Coord]:
    """
    通用批量坐标转换函数
    
    根据源坐标系和目标坐标系自动选择最优的转换方法：
    - 相同坐标系：直接返回
    - GCJ-02 -> WGS84：使用本地转换（推荐）
    - 其他转换：使用百度地图 API
    
    Args:
        coords: 源坐标序列，格式为 [(lng, lat), ...]
        src: 源坐标系名称，支持 'wgs84', 'gcj02', 'bd09ll'
        dst: 目标坐标系名称，支持 'wgs84', 'gcj02', 'bd09ll'
        
    Returns:
        List[Coord]: 转换后的坐标列表
        
    Raises:
        NotImplementedError: 如果不支持指定的坐标系转换对
        
    Example:
        >>> coords = [(114.057868, 22.543099)]
        >>> batch_convert(coords, 'gcj02', 'wgs84')
        [(114.052, 22.537)]
    """
    src = src.lower()
    dst = dst.lower()
    
    # 相同坐标系，直接返回
    if src == dst:
        return list(coords)

    # GCJ-02 -> WGS84 使用本地转换
    if src == "gcj02" and dst == "wgs84":
        return gcj02_to_wgs84_batch(coords)

    # 其他转换使用百度地图 API
    type_map = {"wgs84": 1, "bd09ll": 3, "gcj02": 5}
    if src not in type_map or dst not in type_map:
        raise NotImplementedError(f"不支持的坐标系转换: {src} -> {dst}")
        
    return baidu_geoconv_batch(coords, type_map[src], type_map[dst])
