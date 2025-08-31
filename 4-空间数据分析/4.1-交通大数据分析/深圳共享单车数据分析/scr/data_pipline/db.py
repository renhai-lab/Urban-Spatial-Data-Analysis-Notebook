"""
优化版本的数据库设置，支持TimescaleDB分区
"""

from datetime import date, timedelta, timezone
from loguru import logger
import psycopg
from psycopg import sql

from .config import settings
from .profiles import DatasetProfile, IndexSpec
from .utils import tz_beijing


async def setup_database(conn_str: str, profile: DatasetProfile):
    """设置数据库表，支持TimescaleDB分区"""
    async with await psycopg.AsyncConnection.connect(
        conn_str, connect_timeout=settings.CONNECT_TIMEOUT
    ) as aconn:
        async with aconn.cursor() as acur:
            logger.info(
                f"正在配置数据库表 '{profile.table_name}'（主机：{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}）..."
            )
            
            # 1. 创建扩展
            try:
                await acur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS postgis;"))
                logger.debug("PostGIS 扩展已启用")
            except Exception as e:
                logger.debug(f"PostGIS 扩展创建跳过/失败：{e}")

            if profile.enable_timescale:
                try:
                    await acur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
                    logger.debug("TimescaleDB 扩展已启用")
                except Exception as e:
                    logger.warning(f"TimescaleDB 扩展创建失败，将使用普通表：{e}")
                    profile.enable_timescale = False

            # 2. 创建表
            table_ident_str = sql.Identifier(profile.table_name).as_string(aconn)
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_ident_str} ({profile.table_columns_sql})"
            await acur.execute(create_sql.encode("utf-8"))
            logger.debug(f"表 {profile.table_name} 创建完成")

            # 3. 设置TimescaleDB分区（如果启用）
            if profile.enable_timescale:
                try:
                    timescale_sql = profile.get_timescale_setup_sql()
                    if timescale_sql.strip():
                        await acur.execute(timescale_sql.encode("utf-8"))
                        logger.info(f"TimescaleDB分区已设置：{profile.partition_interval}")
                except Exception as e:
                    logger.warning(f"TimescaleDB分区设置失败：{e}")

            # 4. 创建索引
            logger.info("正在创建索引（如果不存在）...")
            for idx in profile.indexes:
                assert isinstance(idx, IndexSpec)
                idx_ident_str = sql.Identifier(idx.name).as_string(aconn)
                table_ident_str = sql.Identifier(profile.table_name).as_string(aconn)
                using_clause = f" USING {idx.using}" if idx.using else ""
                idx_sql = f"CREATE INDEX IF NOT EXISTS {idx_ident_str} ON {table_ident_str}{using_clause} ({idx.columns_sql});"
                await acur.execute(idx_sql.encode("utf-8"))
                logger.debug(f"索引 {idx.name} 检查/创建完毕。")
            
            logger.success("数据库配置完成！")


async def get_latest_date_from_db(
    conn_str: str, profile: DatasetProfile
) -> date | None:
    """获取数据库中最新日期"""
    try:
        async with await psycopg.AsyncConnection.connect(
            conn_str, connect_timeout=settings.CONNECT_TIMEOUT
        ) as aconn:
            async with aconn.cursor() as acur:
                await acur.execute(
                    sql.SQL("SELECT MAX({col}) FROM {table};").format(
                        col=sql.Identifier(profile.latest_date_column),
                        table=sql.Identifier(profile.table_name),
                    )
                )
                result = await acur.fetchone()
                if result and result[0]:
                    max_dt = result[0]
                    # 转换为北京时间的日期
                    beijing_dt = max_dt.astimezone(tz_beijing)
                    latest_date = beijing_dt.date()
                    logger.debug(f"数据库最新日期：{latest_date}")
                    return latest_date
                else:
                    logger.debug("数据库为空，将从配置的开始日期开始")
                    return None
    except Exception as e:
        logger.warning(f"查询数据库最新日期失败：{e}，将从配置的开始日期开始")
        return None
