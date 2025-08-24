from datetime import datetime, timedelta, timezone

tz_beijing = timezone(timedelta(hours=8))


def to_float(value):
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "" or s.lower() == "null":
            return None
        return float(s)
    except Exception:
        return None


def to_int(value):
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "" or s.lower() == "null":
            return None
        return int(float(s))
    except Exception:
        return None


def parse_dt_beijing(value: str | None) -> datetime | None:
    """将字符串为 北京时间：`%Y-%m-%d %H:%M:%S.?` 的解析为北京时间的 datetime 对象。"""
    if not value:
        return None
    try:
        s = str(value).split(".")[0]
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz_beijing)
    except Exception:
        return None
