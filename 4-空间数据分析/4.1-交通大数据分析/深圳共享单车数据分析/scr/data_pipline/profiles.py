from dataclasses import dataclass
from typing import List, Optional, Dict

from .config import settings
from .utils import to_float, to_int, parse_dt_beijing


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

    def prepare_record(self, record: dict):  # pragma: no cover - overridden
        raise NotImplementedError

    def field_labels(self) -> Dict[str, str]:
        """Return a mapping of raw API field names to Chinese descriptions."""
        return {}


class BikeProfile(DatasetProfile):
    def __init__(self):
        super().__init__(
            name="bike",
            api_url=settings.API_URL,
            table_name=settings.TABLE_NAME,
            copy_columns=[
                "user_id",
                "company_id",
                "start_time",
                "end_time",
                "start_geom",
                "end_geom",
            ],
            table_columns_sql="""
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT,
            company_id TEXT,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            start_geom GEOGRAPHY(Point, 4326),
            end_geom GEOGRAPHY(Point, 4326)
            """,
            indexes=[
                IndexSpec(name="idx_start_time", columns_sql="start_time"),
                IndexSpec(
                    name="idx_start_geom", columns_sql="start_geom", using="GIST"
                ),
                IndexSpec(name="idx_end_geom", columns_sql="end_geom", using="GIST"),
            ],
            latest_date_column="start_time",
        )

    def prepare_record(self, record: dict):
        start_time_utc = parse_dt_beijing(record.get("START_TIME"))
        end_time_utc = parse_dt_beijing(record.get("END_TIME"))

        start_geom_wkt = None
        slon, slat = to_float(record.get("START_LNG")), to_float(
            record.get("START_LAT")
        )
        if slon is not None and slat is not None:
            start_geom_wkt = f"SRID=4326;POINT({slon} {slat})"

        end_geom_wkt = None
        elon, elat = to_float(record.get("END_LNG")), to_float(record.get("END_LAT"))
        if elon is not None and elat is not None:
            end_geom_wkt = f"SRID=4326;POINT({elon} {elat})"

        return (
            record.get("USER_ID"),
            record.get("COM_ID"),
            start_time_utc,
            end_time_utc,
            start_geom_wkt,
            end_geom_wkt,
        )

    def field_labels(self) -> Dict[str, str]:
        # 与 Postgres 表列名对应的中文说明
        return {
            "id": "自增主键",
            "user_id": "用户ID",
            "company_id": "企业ID",
            "start_time": "开始时间",
            "end_time": "结束时间",
            "start_geom": "起点坐标（WGS84 Point）",
            "end_geom": "终点坐标（WGS84 Point）",
        }


class WeatherGridProfile(DatasetProfile):
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
            id BIGSERIAL PRIMARY KEY,
            recid TEXT,
            ddatetime TIMESTAMPTZ,
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
                IndexSpec(name="idx_wg_crttime", columns_sql="crttime"),
                IndexSpec(name="idx_wg_ddatetime", columns_sql="ddatetime"),
                IndexSpec(name="idx_wg_gridid", columns_sql="gridid"),
            ],
            latest_date_column="crttime",
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

    def field_labels(self) -> Dict[str, str]:
        # 与 Postgres 表列名对应的中文说明
        return {
            "id": "自增主键",
            "recid": "记录编号",
            "ddatetime": "发布时间",
            "gridid": "格网ID",
            "ybsx": "预报时效（小时）",
            "forecasttime": "预报时间",
            "plevel": "预报级别",
            "t": "温度（摄氏度）",
            "wspd": "风速（米/秒）",
            "wdir": "风向（度）",
            "slp": "气压（百帕）",
            "rhsfc": "相对湿度（百分比）",
            "rain01h": "1小时累计降雨量（毫米）",
            "rain03h": "3小时累计降雨量（毫米）",
            "rain06h": "6小时累计降雨量（毫米）",
            "rain24h": "24小时累计降雨量（毫米）",
            "v": "能见度（公里）",
            "tracerr01h": "Tracer1小时累计降雨量预报",
            "maxtofday": "日最高温度（摄氏度）",
            "rain02h": "2小时累计降雨量（毫米）",
            "wd3smaxdf": "极大风速（米/秒）",
            "wd3smaxdd": "极大风向（度）",
            "crttime": "入库时间",
            "keyid": "入库序号",
            # 若已执行 augment 脚本，会存在此列：
            "recid_int": "记录编号（整数化，用于关联几何网格）",
        }


def get_profile(profile_name: str) -> DatasetProfile:
    name = (profile_name or "bike").lower()
    if name == "weather_grid":
        return WeatherGridProfile()
    return BikeProfile()
