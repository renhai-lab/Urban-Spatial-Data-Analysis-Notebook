"""
优化版本的数据集配置文件，支持：
1. TimescaleDB分区
2. 实时坐标转换（GCJ-02 -> WGS84）
3. 简化表结构
4. 集成按天导出
"""

from dataclasses import dataclass
from typing import List, Optional, Dict

from .config import settings
from .utils import to_float, to_int, parse_dt_beijing
from .coords import gcj02_to_wgs84


@dataclass
class IndexSpec:
    name: str
    columns_sql: str
    using: Optional[str] = None


@dataclass
class DatasetProfile:
    name: str
    api_url: str
    table_name: str
    copy_columns: List[str]
    table_columns_sql: str
    indexes: List[IndexSpec]
    latest_date_column: str
    # 新增：是否启用TimescaleDB分区
    enable_timescale: bool = True
    # 新增：分区时间列
    partition_column: str = "start_time"
    # 新增：分区间隔（如 '1 day', '1 week'）
    partition_interval: str = "1 day"

    def prepare_record(self, record: dict):  # pragma: no cover - overridden
        raise NotImplementedError

    def field_labels(self) -> Dict[str, str]:
        """Return a mapping of raw API field names to Chinese descriptions."""
        return {}

    def get_timescale_setup_sql(self) -> str:
        """返回TimescaleDB设置SQL"""
        if not self.enable_timescale:
            return ""
        
        return f"""
        -- 创建hypertable（如果尚未创建）
        SELECT create_hypertable('{self.table_name}', '{self.partition_column}', 
                                 chunk_time_interval => INTERVAL '{self.partition_interval}',
                                 if_not_exists => TRUE);
        """


class BikeProfileV2(DatasetProfile):
    """优化版本的共享单车配置：实时转换坐标，简化表结构"""
    
    def __init__(self):
        super().__init__(
            name="bike_v2",
            api_url=settings.API_URL,
            table_name=settings.TABLE_NAME,  # 直接使用配置中的表名
            copy_columns=[
                "user_id",
                "company_id", 
                "start_time",
                "end_time",
                "start_geom_raw",     # 保留原始坐标
                "end_geom_raw",
                "start_geom_wgs84",   # 转换后的WGS84坐标
                "end_geom_wgs84",
                "source_crs",
            ],
            table_columns_sql="""
            id BIGSERIAL,
            user_id TEXT,
            company_id TEXT,
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ,
            -- 原始坐标（直接按接口给出的经纬度写入）
            start_geom_raw GEOMETRY(Point, 4326),
            end_geom_raw GEOMETRY(Point, 4326),
            -- 转换后的 WGS84 坐标（实时转换）
            start_geom_wgs84 GEOMETRY(Point, 4326),
            end_geom_wgs84 GEOMETRY(Point, 4326),
            -- 原始坐标系标识（默认 'GCJ-02'）
            source_crs TEXT DEFAULT 'GCJ-02',
            PRIMARY KEY (id, start_time)
            """,
            indexes=[
                IndexSpec(name="idx_start_time_v2", columns_sql="start_time"),
                IndexSpec(name="idx_company_id_v2", columns_sql="company_id"),
                # 原始坐标空间索引
                IndexSpec(
                    name="idx_start_geom_raw_v2",
                    columns_sql="start_geom_raw",
                    using="GIST",
                ),
                IndexSpec(
                    name="idx_end_geom_raw_v2", 
                    columns_sql="end_geom_raw", 
                    using="GIST"
                ),
                # WGS84坐标空间索引
                IndexSpec(
                    name="idx_start_geom_wgs84_v2",
                    columns_sql="start_geom_wgs84",
                    using="GIST",
                ),
                IndexSpec(
                    name="idx_end_geom_wgs84_v2", 
                    columns_sql="end_geom_wgs84", 
                    using="GIST"
                ),
                # 原始坐标系标识索引
                IndexSpec(name="idx_source_crs_v2", columns_sql="source_crs"),
            ],
            latest_date_column="start_time",
            enable_timescale=True,
            partition_column="start_time",
            partition_interval="1 day",
        )

    def prepare_record(self, record: dict):
        """准备记录，同时保存原始坐标和转换后的WGS84坐标"""
        start_time_utc = parse_dt_beijing(record.get("START_TIME"))
        end_time_utc = parse_dt_beijing(record.get("END_TIME"))

        # 获取原始坐标
        slon, slat = to_float(record.get("START_LNG")), to_float(record.get("START_LAT"))
        elon, elat = to_float(record.get("END_LNG")), to_float(record.get("END_LAT"))

        # 原始坐标WKT
        start_geom_raw_wkt = None
        if slon is not None and slat is not None:
            start_geom_raw_wkt = f"SRID=4326;POINT({slon} {slat})"

        end_geom_raw_wkt = None
        if elon is not None and elat is not None:
            end_geom_raw_wkt = f"SRID=4326;POINT({elon} {elat})"

        # 转换为WGS84坐标
        start_geom_wgs84_wkt = None
        if slon is not None and slat is not None:
            try:
                wgs_lon, wgs_lat = gcj02_to_wgs84(slon, slat)
                start_geom_wgs84_wkt = f"SRID=4326;POINT({wgs_lon} {wgs_lat})"
            except Exception as e:
                # 转换失败则使用原始坐标（可能本身就是WGS84）
                start_geom_wgs84_wkt = start_geom_raw_wkt

        end_geom_wgs84_wkt = None
        if elon is not None and elat is not None:
            try:
                wgs_lon, wgs_lat = gcj02_to_wgs84(elon, elat)
                end_geom_wgs84_wkt = f"SRID=4326;POINT({wgs_lon} {wgs_lat})"
            except Exception as e:
                # 转换失败则使用原始坐标
                end_geom_wgs84_wkt = end_geom_raw_wkt

        return (
            record.get("USER_ID"),
            record.get("COM_ID"),
            start_time_utc,
            end_time_utc,
            start_geom_raw_wkt,    # start_geom_raw
            end_geom_raw_wkt,      # end_geom_raw
            start_geom_wgs84_wkt,  # start_geom_wgs84
            end_geom_wgs84_wkt,    # end_geom_wgs84
            "GCJ-02",              # source_crs，默认假设原始数据为GCJ-02
        )

    def field_labels(self) -> Dict[str, str]:
        return {
            "id": "自增主键",
            "user_id": "用户ID", 
            "company_id": "企业ID",
            "start_time": "开始时间",
            "end_time": "结束时间",
            "start_geom_raw": "起点原始坐标（未转换，Point）",
            "end_geom_raw": "终点原始坐标（未转换，Point）",
            "start_geom_wgs84": "起点坐标（WGS84，已转换）",
            "end_geom_wgs84": "终点坐标（WGS84，已转换）",
            "source_crs": "原始坐标系标识（默认GCJ-02）",
        }


class WeatherGridProfileV2(DatasetProfile):
    """天气格点数据配置（已优化）"""
    
    def __init__(self):
        super().__init__(
            name="weather_grid_v2",
            api_url="https://opendata.sz.gov.cn/api/29200_00903509/1/service.xhtml",
            table_name="sz_weather_grid_v2",
            copy_columns=[
                "recid", "ddatetime", "gridid", "ybsx", "forecasttime", "plevel",
                "t", "wspd", "wdir", "slp", "rhsfc", "rain01h", "rain03h", 
                "rain06h", "rain24h", "v", "tracerr01h", "maxtofday", "rain02h",
                "wd3smaxdf", "wd3smaxdd", "crttime", "keyid",
            ],
            table_columns_sql="""
            id BIGSERIAL PRIMARY KEY,
            recid TEXT,
            ddatetime TIMESTAMPTZ NOT NULL,
            gridid TEXT,
            ybsx INTEGER,
            forecasttime TIMESTAMPTZ,
            plevel TEXT,
            t DOUBLE PRECISION,
            wspd DOUBLE PRECISION,
            wdir DOUBLE PRECISION,
            slp DOUBLE PRECISION,
            rhsfc DOUBLE PRECISION,
            rain01h DOUBLE PRECISION,
            rain03h DOUBLE PRECISION,
            rain06h DOUBLE PRECISION,
            rain24h DOUBLE PRECISION,
            v DOUBLE PRECISION,
            tracerr01h DOUBLE PRECISION,
            maxtofday DOUBLE PRECISION,
            rain02h DOUBLE PRECISION,
            wd3smaxdf DOUBLE PRECISION,
            wd3smaxdd DOUBLE PRECISION,
            crttime TIMESTAMPTZ,
            keyid TEXT
            """,
            indexes=[
                IndexSpec(name="idx_wg_v2_crttime", columns_sql="crttime"),
                IndexSpec(name="idx_wg_v2_ddatetime", columns_sql="ddatetime"),
                IndexSpec(name="idx_wg_v2_gridid", columns_sql="gridid"),
            ],
            latest_date_column="crttime",
            enable_timescale=True,
            partition_column="ddatetime",
            partition_interval="1 day",
        )

    def prepare_record(self, record: dict):
        return (
            str(record.get("RECID")) if record.get("RECID") is not None else None,
            parse_dt_beijing(record.get("DDATETIME")),
            str(record.get("GRIDID")) if record.get("GRIDID") is not None else None,
            to_int(record.get("YBSX")),
            parse_dt_beijing(record.get("FORECASTTIME")),
            str(record.get("PLEVEL")) if record.get("PLEVEL") is not None else None,
            to_float(record.get("T")),
            to_float(record.get("WSPD")),
            to_float(record.get("WDIR")),
            to_float(record.get("SLP")),
            to_float(record.get("RHSFC")),
            to_float(record.get("RAIN01H")),
            to_float(record.get("RAIN03H")),
            to_float(record.get("RAIN06H")),
            to_float(record.get("RAIN24H")),
            to_float(record.get("V")),
            to_float(record.get("TRACERR01H")),
            to_float(record.get("MAXTOFDAY")),
            to_float(record.get("RAIN02H")),
            to_float(record.get("WD3SMAXDF")),
            to_float(record.get("WD3SMAXDD")),
            parse_dt_beijing(record.get("CRTTIME")),
            str(record.get("KEYID")) if record.get("KEYID") is not None else None,
        )


def get_profile(profile_name: str) -> DatasetProfile:
    """获取数据集配置"""
    name = (profile_name or "bike").lower()
    if name == "weather_grid":
        return WeatherGridProfileV2()
    return BikeProfileV2()
