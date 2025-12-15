"""
数据集配置文件模块

该模块定义了不同数据集的配置和处理逻辑，支持：
1. TimescaleDB 时序数据库分区配置
2. 实时坐标转换（GCJ-02 转 WGS84）
3. 数据表结构简化和优化
4. 按天导出功能集成
5. 多数据源支持（共享单车、气象格点等）

主要包含的数据集：
- 深圳共享单车数据（bike）
- 深圳气象格点数据（weather_grid）

每个数据集都通过 DatasetProfile 类定义其特定的处理逻辑和数据库配置。
"""

from dataclasses import dataclass
from typing import List, Optional, Dict

from .config import settings
from .utils import to_float, to_int, parse_dt_beijing
from .coords import gcj02_to_wgs84


@dataclass
class IndexSpec:
    """
    数据库索引规格定义

    Attributes:
        name: 索引名称
        columns_sql: 索引列的 SQL 定义
        using: 索引类型（如 'btree', 'gist' 等），可选
    """

    name: str
    columns_sql: str
    using: Optional[str] = None


@dataclass
class DatasetProfile:
    """
    数据集配置基类

    定义了每个数据集的基本配置信息，包括 API 接口、数据库表结构、
    索引配置、时序分区设置等。子类需要实现 prepare_record 方法
    来处理具体的数据记录。

    Attributes:
        name: 数据集名称（用于日志显示）
        api_url: 数据获取 API 地址
        table_name: 数据库表名
        copy_columns: COPY 操作使用的列名列表
        table_columns_sql: 创建表时的列定义 SQL
        indexes: 索引配置列表
        latest_date_column: 用于查询最新日期的时间列名
        enable_timescale: 是否启用 TimescaleDB 分区
        partition_column: 时序分区的时间列名
        partition_interval: 分区时间间隔
    """

    name: str
    api_url: str
    table_name: str
    copy_columns: List[str]
    table_columns_sql: str
    indexes: List[IndexSpec]
    latest_date_column: str
    # 时序数据库配置
    enable_timescale: bool = True
    partition_column: str = "start_time"
    partition_interval: str = "1 day"
    # 是否需要坐标转换（用于异步抓取时决定是否使用线程池转换）
    needs_coord_transform: bool = False
    # 导出配置：导出时的日期时间列（用于按日期筛选数据）
    export_datetime_column: str = "start_time"
    # 导出配置：导出时的主要时间戳格式（用于时区转换）
    export_tz: str = "Asia/Shanghai"
    # 导出配置：是否支持多坐标系导出（False 表示只支持单坐标系）
    export_support_coord_sets: bool = True
    # 导出配置：地理坐标列的映射 {"coord_set": {"start_lon": "...", "start_lat": "...", "end_lon": "...", "end_lat": "..."}}
    export_geom_columns: Optional[Dict[str, Dict[str, str]]] = None

    def prepare_record(self, record: dict):  # pragma: no cover - 子类实现
        """
        处理单条记录的抽象方法

        子类必须实现此方法来处理从 API 获取的原始数据记录，
        包括数据清洗、格式转换、坐标转换等操作。

        Args:
            record: 从 API 获取的原始数据记录

        Returns:
            处理后的数据记录，格式需要与 copy_columns 对应
        """
        raise NotImplementedError

    def field_labels(self) -> Dict[str, str]:
        """
        返回字段名到中文描述的映射

        用于数据导出时的字段标签显示。

        Returns:
            Dict[str, str]: 字段名到中文描述的映射字典
        """
        return {}

    def get_timescale_setup_sql(self) -> str:
        """
        生成 TimescaleDB 分区设置的 SQL 语句

        Returns:
            str: TimescaleDB 分区设置的 SQL 语句，如果未启用则返回空字符串
        """
        if not self.enable_timescale:
            return ""

        return f"""
        -- 创建 TimescaleDB 超表（如果尚未创建）
        SELECT create_hypertable('{self.table_name}', '{self.partition_column}', 
                                 chunk_time_interval => INTERVAL '{self.partition_interval}',
                                 if_not_exists => TRUE);
        """


class BikeProfile(DatasetProfile):
    """
    深圳共享单车数据集配置类

    针对深圳市政府开放数据平台的共享单车数据进行优化配置：
    - 实时坐标转换（GCJ-02 转 WGS84）
    - 简化的表结构设计
    - TimescaleDB 时序分区支持
    - 完整的字段中文标签

    数据来源：深圳市政府数据开放平台 - 互联网租赁自行车停放点位数据
    """

    def __init__(self):
        super().__init__(
            name="bike",
            api_url=settings.API_URL,
            table_name=settings.TABLE_NAME,  # 直接使用配置中的表名
            copy_columns=[
                "user_id",
                "company_id",
                "start_time",
                "end_time",
                "start_geom_raw",  # 保留原始坐标
                "end_geom_raw",
                "start_geom_wgs84",  # 转换后的WGS84坐标
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
                IndexSpec(name="idx_start_time", columns_sql="start_time"),
                IndexSpec(name="idx_company_id", columns_sql="company_id"),
                # 原始坐标空间索引
                IndexSpec(
                    name="idx_start_geom_raw",
                    columns_sql="start_geom_raw",
                    using="GIST",
                ),
                IndexSpec(
                    name="idx_end_geom_raw", columns_sql="end_geom_raw", using="GIST"
                ),
                # WGS84坐标空间索引
                IndexSpec(
                    name="idx_start_geom_wgs84",
                    columns_sql="start_geom_wgs84",
                    using="GIST",
                ),
                IndexSpec(
                    name="idx_end_geom_wgs84",
                    columns_sql="end_geom_wgs84",
                    using="GIST",
                ),
                # 原始坐标系标识索引
                IndexSpec(name="idx_source_crs", columns_sql="source_crs"),
            ],
            latest_date_column="start_time",
            enable_timescale=True,
            partition_column="start_time",
            partition_interval="1 day",
            needs_coord_transform=True,
            export_datetime_column="start_time",
            export_tz="Asia/Shanghai",
            export_support_coord_sets=True,
            export_geom_columns={
                "raw": {
                    "start_lon": "start_lng_raw",
                    "start_lat": "start_lat_raw",
                    "end_lon": "end_lng_raw",
                    "end_lat": "end_lat_raw",
                },
                "wgs84": {
                    "start_lon": "start_lng_wgs84",
                    "start_lat": "start_lat_wgs84",
                    "end_lon": "end_lng_wgs84",
                    "end_lat": "end_lat_wgs84",
                },
            },
        )

    def prepare_record(self, record: dict):
        """
        处理单条共享单车记录

        执行以下操作：
        1. 解析起止时间（北京时间转UTC）
        2. 提取原始坐标信息
        3. 执行坐标转换（GCJ-02 -> WGS84）
        4. 生成 PostGIS 兼容的 WKT 格式坐标

        Args:
            record: 从 API 获取的原始数据记录

        Returns:
            tuple: 处理后的数据元组，对应 copy_columns 的顺序
        """
        # 解析时间字段（北京时间转换为 UTC）
        start_time_utc = parse_dt_beijing(record.get("START_TIME"))
        end_time_utc = parse_dt_beijing(record.get("END_TIME"))

        # 提取原始坐标（假设为 GCJ-02 坐标系）
        slon, slat = to_float(record.get("START_LNG")), to_float(
            record.get("START_LAT")
        )
        elon, elat = to_float(record.get("END_LNG")), to_float(record.get("END_LAT"))

        # 生成原始坐标的 WKT 格式（PostGIS 兼容）
        start_geom_raw_wkt = None
        if slon is not None and slat is not None:
            start_geom_raw_wkt = f"SRID=4326;POINT({slon} {slat})"

        end_geom_raw_wkt = None
        if elon is not None and elat is not None:
            end_geom_raw_wkt = f"SRID=4326;POINT({elon} {elat})"

        # 执行坐标转换：GCJ-02 -> WGS84
        start_geom_wgs84_wkt = None
        if slon is not None and slat is not None:
            try:
                wgs_lon, wgs_lat = gcj02_to_wgs84(slon, slat)
                start_geom_wgs84_wkt = f"SRID=4326;POINT({wgs_lon} {wgs_lat})"
            except Exception as e:
                # 转换失败则使用原始坐标（可能本身就是 WGS84）
                start_geom_wgs84_wkt = start_geom_raw_wkt

        end_geom_wgs84_wkt = None
        if elon is not None and elat is not None:
            try:
                wgs_lon, wgs_lat = gcj02_to_wgs84(elon, elat)
                end_geom_wgs84_wkt = f"SRID=4326;POINT({wgs_lon} {wgs_lat})"
            except Exception as e:
                # 转换失败则使用原始坐标
                end_geom_wgs84_wkt = end_geom_raw_wkt

        # 返回处理后的数据元组
        return (
            record.get("USER_ID"),  # 用户标识
            record.get("COM_ID"),  # 运营商标识
            start_time_utc,  # 开始时间（UTC）
            end_time_utc,  # 结束时间（UTC）
            start_geom_raw_wkt,  # 起点原始坐标
            end_geom_raw_wkt,  # 终点原始坐标
            start_geom_wgs84_wkt,  # 起点 WGS84 坐标
            end_geom_wgs84_wkt,  # 终点 WGS84 坐标
            "GCJ-02",  # 原始坐标系标识
        )

    def field_labels(self) -> Dict[str, str]:
        """
        返回字段的中文标签映射

        用于数据导出和可视化时显示友好的中文字段名。

        Returns:
            Dict[str, str]: 字段名到中文描述的映射
        """
        return {
            "id": "自增主键",
            "user_id": "匿名用户标识",
            "company_id": "运营商标识",
            "start_time": "骑行开始时间",
            "end_time": "骑行结束时间",
            "start_geom_raw": "起点原始坐标（GCJ-02）",
            "end_geom_raw": "终点原始坐标（GCJ-02）",
            "start_geom_wgs84": "起点标准坐标（WGS84）",
            "end_geom_wgs84": "终点标准坐标（WGS84）",
            "source_crs": "原始坐标系标识",
        }


class WeatherGridProfile(DatasetProfile):
    """
    深圳气象格点数据集配置类

    针对深圳市政府开放数据平台的气象格点数据进行配置：
    - 网格化气象数据存储
    - 时序数据分区优化
    - 多气象要素支持（温度、风速、湿度等）

    数据来源：深圳市政府数据开放平台 - 气象格点数据
    """

    def __init__(self):
        super().__init__(
            name="weather_grid",
            api_url="https://opendata.sz.gov.cn/api/29200_00903509/1/service.xhtml",
            table_name="sz_weather_grid",
            copy_columns=[
                "recid",
                "ddatetime",
                "gridid",
                "ybsx",
                "forecasttime",
                "plevel",
                "t",
                "wspd",
                "wdir",
                "slp",
                "rhsfc",
                "rain01h",
                "rain03h",
                "rain06h",
                "rain24h",
                "v",
                "tracerr01h",
                "maxtofday",
                "rain02h",
                "wd3smaxdf",
                "wd3smaxdd",
                "crttime",
                "keyid",
            ],
            table_columns_sql="""
            id BIGSERIAL,
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
            crttime TIMESTAMPTZ NOT NULL,
            keyid TEXT NOT NULL,
            PRIMARY KEY (keyid, crttime)
            """,
            indexes=[
                IndexSpec(name="idx_wg_crttime", columns_sql="crttime"),
                IndexSpec(name="idx_wg_forecasttime", columns_sql="forecasttime"),
                IndexSpec(name="idx_wg_gridid", columns_sql="gridid"),
            ],
            latest_date_column="crttime",  # 用于读取最近时间的数据
            enable_timescale=True,
            partition_column="crttime",  # 分区列
            partition_interval="1 day",
            export_datetime_column="crttime",
            export_tz="Asia/Shanghai",
            export_support_coord_sets=False,  # 天气数据没有地理坐标
            export_geom_columns=None,  # 无地理坐标列
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
        return WeatherGridProfile()
    return BikeProfile()
