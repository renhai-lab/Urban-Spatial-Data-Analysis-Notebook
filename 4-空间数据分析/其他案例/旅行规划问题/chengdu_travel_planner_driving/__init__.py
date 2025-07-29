"""
成都旅行规划器 - 基于高德地图API的智能旅行路线规划系统

主要功能:
- 智能旅行路线规划（TSP算法优化）
- 支持GCJ02和WGS84坐标系统
- 生成GeoJSON格式的路线数据
- 交互式地图可视化
- 路径时间和距离计算

使用示例:
    from travel_planner_driving import TravelPlanner
    
    planner = TravelPlanner()
    route = planner.plan_route(locations)
    geojson = planner.generate_geojson(route, locations)

作者: 基于高德地图API开发
版本: 2.0.0 (已从百度地图API迁移至高德地图API)
"""

from .travel_planner_driving import TravelPlanner

__version__ = "2.0.0"
__author__ = "Travel Planner Team"
__all__ = ["TravelPlanner"]
