from pydantic_settings import BaseSettings
from loguru import logger


class Settings(BaseSettings):
    APP_KEY: str = "YOUR_APP_KEY_HERE"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "your_password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "gis_db"

    # 默认共享单车 API/表，可被 profile 覆盖
    TABLE_NAME: str = "shenzhen_rides"
    API_URL: str = "https://opendata.sz.gov.cn/api/29200_00403627/1/service.xhtml"

    ROWS_PER_PAGE: int = 4000
    MAX_CONCURRENCY: int = 30
    MAX_RETRIES: int = 5
    RETRY_DELAY_SECONDS: int = 5

    DATA_START_DATE: str = (
        "20210101"  # ！结合官方和实际数据，只有20210101到20210830这一段时间的数据有意义。
    )
    DATA_END_DATE: str = "20210830"

    DATASET_PROFILE: str = "bike"  # bike | weather_grid

    LOG_LEVEL: str = "INFO"
    CONNECT_TIMEOUT: int = 10
    DAYS_CONCURRENCY: int = 100

    # ---- 坐标/导出设置 ----
    SOURCE_COORD: str = "bd09ll"  # 源坐标系：bd09ll | gcj02 | wgs84
    EXPORT_DIR: str = "viz/mapvgl-baidu/data"
    COORD_CONVERT_MODE: str = "local"  # local | api
    BAIDU_AK: str | None = None  # 若使用百度API转换需要设置
    BAIDU_GEOCONV_URL: str = "https://api.map.baidu.com/geoconv/v1/"
    GEOCONV_BATCH_SIZE: int = 100  # geoconv 单次最多100点
    GEOCONV_QPS: int = 30  # geoconv QPS 上限约 30

    # TimescaleDB配置
    TS_TUNE_MEMORY: str = "2GB"
    TS_TUNE_NUM_CPUS: str = "2"
    ENABLE_TIMESCALE: str = "true"
    PARTITION_INTERVAL: str = "1 day"

    # 导出配置
    EXPORT_BASE_DIR: str = "data/share"
    EXPORT_MAX_WORKERS: str = "4"
    EXPORT_BATCH_SIZE: str = "50000"

    # 性能配置
    DB_BATCH_SIZE: str = "10000"
    BUFFER_SIZE_MB: str = "100"
    PROGRESS_REPORT_INTERVAL: str = "10"
    ENABLE_PERFORMANCE_STATS: str = "true"

    model_config = {
        "env_file": ".env",  # 相对于项目目录的路径
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # 忽略额外的环境变量
    }

    def get_conn_str(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()

logger.debug(f"Settings loaded: {settings}")
