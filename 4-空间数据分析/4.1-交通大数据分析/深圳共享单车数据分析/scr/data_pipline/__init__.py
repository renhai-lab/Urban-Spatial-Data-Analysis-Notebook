"""
深圳共享单车数据获取流水线包

该包提供了完整的深圳市政府开放数据平台数据获取解决方案，包括：

核心模块：
- config: 系统配置管理
- profiles: 数据集配置和处理逻辑
- db: 数据库操作和 TimescaleDB 优化
- fetcher: 高性能异步数据获取器（生产版）
- fetcher-legacy: 简化教学版数据获取器
- coords: 中国坐标系转换工具
- utils: 通用工具函数

导出模块：
- export_share: 数据导出和格式转换
- export_memory: 内存优化的数据导出
- export_bike_json: JSON 格式专用导出

数据处理模块：
- audit_days: 数据完整性审计
- backfill_wgs84_from_raw: 坐标系回填工具

使用示例：
    from scr.data_pipline import get_profile
    from scr.data_pipline.fetcher import main as run_fetcher
    
    # 获取数据集配置
    profile = get_profile('bike')
    
    # 启动数据获取
    asyncio.run(run_fetcher())

支持的数据集：
- bike: 深圳共享单车轨迹数据
- weather_grid: 深圳气象格点数据

作者：renhai-lab
许可：CC BY-SA 4.0
"""

# 导出核心功能
from .profiles import get_profile, DatasetProfile, BikeProfile, WeatherGridProfile
from .config import settings

__version__ = "1.0.0"
__author__ = "renhai-lab"
__all__ = [
    "get_profile", 
    "DatasetProfile", 
    "BikeProfile", 
    "WeatherGridProfile", 
    "settings"
]
