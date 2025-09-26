"""
数据处理工具函数模块

该模块提供数据清洗和格式转换的基础工具函数：
1. 数据类型转换（字符串转数字）
2. 时间解析和时区处理
3. 容错的数据清洗函数

这些工具函数被数据获取和处理流程广泛使用，确保数据的一致性和可靠性。
"""

from datetime import datetime, timedelta, timezone

# ===== 时区定义 =====
tz_beijing = timezone(timedelta(hours=8))  # 北京时间（UTC+8）


def to_float(value):
    """
    安全地将值转换为浮点数
    
    支持容错处理，自动处理以下情况：
    - None 值 -> None
    - 空字符串 -> None  
    - "null" 字符串 -> None
    - 有效数字字符串 -> float
    - 无效格式 -> None
    
    Args:
        value: 待转换的值（任意类型）
        
    Returns:
        float | None: 转换后的浮点数，失败时返回 None
    """
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
    """
    安全地将值转换为整数
    
    支持容错处理，先转换为浮点数再转为整数，
    可以处理 "123.0" 格式的字符串。
    
    Args:
        value: 待转换的值（任意类型）
        
    Returns:
        int | None: 转换后的整数，失败时返回 None
    """
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "" or s.lower() == "null":
            return None
        return int(float(s))  # 先转 float 再转 int，处理 "123.0" 格式
    except Exception:
        return None


def parse_dt_beijing(value: str | None) -> datetime | None:
    """
    解析北京时间字符串为 datetime 对象
    
    解析格式：'YYYY-MM-DD HH:MM:SS' 或 'YYYY-MM-DD HH:MM:SS.ffffff'
    自动忽略毫秒部分，统一返回北京时区的 datetime 对象。
    
    Args:
        value: 时间字符串，格式为 '%Y-%m-%d %H:%M:%S.?'
        
    Returns:
        datetime | None: 北京时区的 datetime 对象，解析失败时返回 None
        
    Example:
        >>> parse_dt_beijing("2021-01-01 12:30:45")
        datetime(2021, 1, 1, 12, 30, 45, tzinfo=timezone(timedelta(seconds=28800)))
        
        >>> parse_dt_beijing("2021-01-01 12:30:45.123456")  
        datetime(2021, 1, 1, 12, 30, 45, tzinfo=timezone(timedelta(seconds=28800)))
    """
    if not value:
        return None
    try:
        # 移除毫秒部分，只保留秒级精度
        s = str(value).split(".")[0]
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz_beijing)
    except Exception:
        return None
