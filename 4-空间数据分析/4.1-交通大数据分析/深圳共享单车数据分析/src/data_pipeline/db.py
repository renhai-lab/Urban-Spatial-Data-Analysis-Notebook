"""
数据库设置和管理模块

该模块提供数据库相关的核心功能：
1. 数据库表结构创建和配置
2. TimescaleDB 时序数据库分区设置
3. PostGIS 空间数据库扩展配置
4. 数据库索引优化
5. 增量数据获取支持（查询最新日期）

支持的数据库特性：
- PostgreSQL + PostGIS 空间数据支持
- TimescaleDB 时序数据自动分区
- 批量数据插入优化
- 空间索引自动创建
"""

from datetime import date, timedelta, timezone
from loguru import logger
import psycopg
from psycopg import sql

from .config import settings
from .profiles import DatasetProfile, IndexSpec
from .utils import tz_beijing


async def setup_database(conn_str: str, profile: DatasetProfile):
    """
    初始化数据库表和扩展

    执行以下操作：
    1. 创建必需的数据库扩展（PostGIS, TimescaleDB）
    2. 创建数据表（如果不存在）
    3. 设置 TimescaleDB 分区（如果启用）
    4. 创建所有必需的索引

    Args:
        conn_str: PostgreSQL 连接字符串
        profile: 数据集配置对象，包含表结构和索引定义

    Raises:
        psycopg.Error: 数据库操作失败时抛出异常
    """
    async with await psycopg.AsyncConnection.connect(
        conn_str, connect_timeout=settings.CONNECT_TIMEOUT
    ) as aconn:
        async with aconn.cursor() as acur:
            logger.info(
                f"正在配置数据库表 '{profile.table_name}'（主机：{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}）..."
            )

            # ===== 1. 创建数据库扩展 =====
            try:
                await acur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS postgis;"))
                logger.debug("PostGIS 空间数据库扩展已启用")
            except Exception as e:
                logger.debug(f"PostGIS 扩展创建跳过或失败：{e}")

            # 尝试启用 TimescaleDB 扩展（如果配置启用）
            if profile.enable_timescale:
                try:
                    await acur.execute(
                        sql.SQL("CREATE EXTENSION IF NOT EXISTS timescaledb;")
                    )
                    logger.debug("TimescaleDB 时序数据库扩展已启用")
                except Exception as e:
                    logger.warning(
                        f"TimescaleDB 扩展创建失败，将使用普通 PostgreSQL 表：{e}"
                    )
                    profile.enable_timescale = False

            # ===== 2. 创建数据表 =====
            table_ident_str = sql.Identifier(profile.table_name).as_string(aconn)
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_ident_str} ({profile.table_columns_sql})"
            await acur.execute(create_sql.encode("utf-8"))
            logger.debug(f"数据表 {profile.table_name} 创建完成")

            # ===== 3. 设置 TimescaleDB 分区（如果启用） =====
            if profile.enable_timescale:
                try:
                    timescale_sql = profile.get_timescale_setup_sql()
                    if timescale_sql.strip():
                        await acur.execute(timescale_sql.encode("utf-8"))
                        logger.info(
                            f"TimescaleDB 分区已设置：{profile.partition_interval} 间隔"
                        )
                except Exception as e:
                    logger.warning(f"TimescaleDB分区设置失败：{e}")
                    try:
                        await aconn.rollback()
                    except Exception:
                        pass

            # ===== 4. 创建数据库索引 =====
            logger.info("正在创建数据库索引（如果不存在）...")
            for idx in profile.indexes:
                assert isinstance(idx, IndexSpec)
                idx_ident_str = sql.Identifier(idx.name).as_string(aconn)
                table_ident_str = sql.Identifier(profile.table_name).as_string(aconn)
                using_clause = f" USING {idx.using}" if idx.using else ""
                idx_sql = f"CREATE INDEX IF NOT EXISTS {idx_ident_str} ON {table_ident_str}{using_clause} ({idx.columns_sql});"
                await acur.execute(idx_sql.encode("utf-8"))
                logger.debug(f"索引 {idx.name} 检查/创建完毕")

            logger.success("数据库配置完成！")


async def get_latest_date_from_db(
    conn_str: str, profile: DatasetProfile
) -> date | None:
    """
    查询数据库中最新的数据日期

    用于支持增量数据获取，避免重复获取已存在的数据。
    查询指定时间列的最大值，并转换为北京时间的日期格式。

    Args:
        conn_str: PostgreSQL 连接字符串
        profile: 数据集配置对象，指定要查询的表和时间列

    Returns:
        date | None: 数据库中最新的日期，如果表为空或查询失败则返回 None

    Note:
        返回的日期基于北京时区，用于与配置的日期范围进行比较
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            async with aconn.cursor() as acur:
                # 查询指定时间列的最大值
                await acur.execute(
                    sql.SQL("SELECT MAX({col}) FROM {table};").format(
                        col=sql.Identifier(profile.latest_date_column),
                        table=sql.Identifier(profile.table_name),
                    )
                )
                result = await acur.fetchone()

                if result and result[0]:
                    max_dt = result[0]
                    # 转换为北京时间的日期格式
                    beijing_dt = max_dt.astimezone(tz_beijing)
                    latest_date = beijing_dt.date()
                    logger.debug(f"数据库最新日期：{latest_date}")
                    return latest_date
                else:
                    logger.debug("数据库为空，将从配置的开始日期开始获取数据")
                    return None

    except Exception as e:
        logger.warning(f"查询数据库最新日期失败：{e}，将从配置的开始日期开始获取数据")
        return None
