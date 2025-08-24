from datetime import date, timedelta, timezone
from loguru import logger
import psycopg
from psycopg import sql

from .config import settings
from .profiles import DatasetProfile, IndexSpec
from .utils import tz_beijing


async def setup_database(conn_str: str, profile: DatasetProfile):
    async with await psycopg.AsyncConnection.connect(
        conn_str, connect_timeout=settings.CONNECT_TIMEOUT
    ) as aconn:
        async with aconn.cursor() as acur:
            logger.info(
                f"正在配置数据库表 '{profile.table_name}'（主机：{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}）..."
            )
            try:
                await acur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS postgis;"))
            except Exception as e:
                logger.debug(f"PostGIS 扩展创建跳过/失败：{e}")

            table_ident_str = sql.Identifier(profile.table_name).as_string(aconn)
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_ident_str} ({profile.table_columns_sql})"
            await acur.execute(create_sql.encode("utf-8"))

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
                latest_timestamp = await acur.fetchone()
                if latest_timestamp and latest_timestamp[0]:
                    latest_beijing_time = latest_timestamp[0].astimezone(tz_beijing)
                    return latest_beijing_time.date()
                else:
                    logger.info("数据库暂无历史数据记录。")
    except (psycopg.OperationalError, Exception) as e:
        logger.warning(f"无法连接到数据库获取最新日期: {e}。将从头开始。")
    return None
