"""
数据获取系统配置模块

该模块定义了深圳共享单车数据获取系统的所有配置参数，包括：
- 数据库连接配置
- API 接口配置  
- 数据获取策略配置
- 日志和性能配置

使用 pydantic_settings 实现配置管理，支持环境变量覆盖。
"""

from pydantic_settings import BaseSettings
from loguru import logger


class Settings(BaseSettings):
    """
    系统配置类
    
    使用 pydantic_settings 管理所有配置参数，支持通过环境变量或 .env 文件覆盖默认值。
    所有配置项都有合理的默认值，确保系统在基本环境下可以正常运行。
    """
    # ===== API 访问配置 =====
    APP_KEY: str = "YOUR_APP_KEY_HERE"  # 深圳开放数据平台 API 密钥
    
    # ===== 数据库连接配置 =====
    POSTGRES_USER: str = "postgres"          # PostgreSQL 用户名
    POSTGRES_PASSWORD: str = "your_password" # PostgreSQL 密码
    POSTGRES_HOST: str = "localhost"         # PostgreSQL 主机地址
    POSTGRES_PORT: int = 5432               # PostgreSQL 端口
    POSTGRES_DB: str = "gis_db"            # 数据库名称

    # ===== 数据获取配置 =====
    # 默认共享单车 API 和表名，可被数据集配置文件覆盖
    TABLE_NAME: str = "shenzhen_rides"
    API_URL: str = "https://opendata.sz.gov.cn/api/29200_00403627/1/service.xhtml"

    # ===== 性能和并发配置 =====
    ROWS_PER_PAGE: int = 4000              # 每页获取的记录数
    MAX_CONCURRENCY: int = 30              # 最大并发连接数
    MAX_RETRIES: int = 5                   # 最大重试次数
    RETRY_DELAY_SECONDS: int = 5           # 重试延迟时间（秒）

    # ===== 数据时间范围配置 =====
    DATA_START_DATE: str = (
        "20210101"  # 注意：结合官方说明和实际数据测试，只有 2021年1月1日 到 2021年8月30日 的数据有效
    )
    DATA_END_DATE: str = "20210830"        # 数据结束日期

    # ===== 数据集配置 =====
    DATASET_PROFILE: str = "bike"          # 数据集类型：bike（共享单车）| weather_grid（气象格点）

    # ===== 日志和监控配置 =====
    LOG_LEVEL: str = "INFO"                # 日志级别
    CONNECT_TIMEOUT: int = 10              # 数据库连接超时时间（秒）
    DAYS_CONCURRENCY: int = 3              # 按天并发处理数量（平衡原子性和内存使用）

    # ===== TimescaleDB 时序数据库配置 =====
    TS_TUNE_MEMORY: str = "2GB"            # TimescaleDB 内存调优参数
    TS_TUNE_NUM_CPUS: str = "2"           # TimescaleDB CPU 调优参数
    ENABLE_TIMESCALE: str = "true"         # 是否启用 TimescaleDB 分区
    PARTITION_INTERVAL: str = "1 day"      # 时序分区间隔

    # ===== 数据导出配置 =====
    EXPORT_BASE_DIR: str = "data/share"    # 导出数据基础目录
    EXPORT_MAX_WORKERS: int = 4            # 导出最大工作进程数
    EXPORT_BATCH_SIZE: int = 50000         # 导出批次大小

    # ===== 高级性能配置 =====
    DB_BATCH_SIZE: int = 10000             # 数据库批量插入大小
    BUFFER_SIZE_MB: int = 100              # 缓冲区大小（MB）
    PROGRESS_REPORT_INTERVAL: int = 10     # 进度报告间隔（秒）
    ENABLE_PERFORMANCE_STATS: bool = True  # 是否启用性能统计

    # ===== pydantic 模型配置 =====
    model_config = {
        "env_file": ".env",                # 环境变量文件路径（相对于项目根目录）
        "env_file_encoding": "utf-8",      # 环境变量文件编码
        "extra": "ignore",                 # 忽略未定义的额外环境变量
    }

    def get_conn_str(self) -> str:
        """
        构建 PostgreSQL 连接字符串
        
        Returns:
            str: PostgreSQL 异步连接字符串，格式为 postgresql://user:pass@host:port/db
        """
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ===== 已禁用的可视化导出配置（保留用于参考） =====
    # 以下配置项用于特定的可视化导出场景，目前已禁用
    # SOURCE_COORD: str = "bd09ll"              # 源坐标系：bd09ll | gcj02 | wgs84
    # EXPORT_DIR: str = "viz/mapvgl-baidu/data" # 可视化导出目录
    # COORD_CONVERT_MODE: str = "local"         # 坐标转换模式：local | api
    # BAIDU_AK: str | None = None              # 百度地图 API 密钥（API 转换时需要）
    # BAIDU_GEOCONV_URL: str = "https://api.map.baidu.com/geoconv/v1/"  # 百度坐标转换接口
    # GEOCONV_BATCH_SIZE: int = 100            # 坐标转换批次大小（百度 API 限制最多100点）
    # GEOCONV_QPS: int = 30                    # 坐标转换接口 QPS 限制（约30次/秒）


# ===== 全局配置实例 =====
settings = Settings()

# ===== 配置日志系统 =====  
logger.debug(f"配置加载完成: {settings}")
