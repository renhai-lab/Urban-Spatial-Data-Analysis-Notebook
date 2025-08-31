#!/usr/bin/env python3
"""
简化测试脚本：测试优化版数据管道的核心功能
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from scr.data_pipline.config import settings
from scr.data_pipline.profiles import get_profile
from scr.data_pipline.db import setup_database
from scr.data_pipline.fetcher import fetch_day
from scr.data_pipline.export_share import export_day

import aiohttp
from loguru import logger

async def test_pipeline():
    """测试完整的数据管道流程"""
    logger.info("开始测试优化版数据管道...")
    
    # 1. 获取配置
    profile = get_profile('bike')
    conn_str = settings.get_conn_str()
    target_date = date(2021, 1, 1)
    
    logger.info(f"目标日期: {target_date}")
    logger.info(f"数据库: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
    logger.info(f"表名: {profile.table_name}")
    
    try:
        # 2. 设置数据库（如果需要）
        logger.info("检查数据库设置...")
        await setup_database(conn_str, profile)
        logger.success("数据库设置完成")
        
        # 3. 测试获取数据
        logger.info("开始获取数据...")
        async with aiohttp.ClientSession() as session:
            records, stats = await fetch_day(session, target_date, profile, 5)
            
            if records is None:
                logger.error("数据获取失败")
                return False
                
            logger.info(f"获取到 {len(records)} 条记录")
            logger.info(f"统计信息: {stats}")
            
            if len(records) == 0:
                logger.warning("当天无数据，跳过后续测试")
                return True
            
            # 4. 测试数据入库（插入少量数据）
            logger.info("测试数据入库...")
            test_records = records[:10]  # 只测试前10条
            
            from scr.data_pipline.fetcher import bulk_insert
            inserted = await bulk_insert(conn_str, profile, test_records)
            logger.info(f"插入了 {inserted} 条测试记录")
            
            # 5. 测试导出功能
            logger.info("测试导出功能...")
            export_base = Path("data/test_export")
            export_stats = export_day(
                conn_str,
                profile.table_name,
                target_date,
                export_base,
                coord_sets=["raw", "wgs84"],
                formats=["csv"],
                batch_size=1000
            )
            logger.info(f"导出统计: {export_stats}")
            
            logger.success("数据管道测试完成！")
            return True
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # 运行测试
    success = asyncio.run(test_pipeline())
    
    if success:
        print("\n🎉 测试成功！优化版数据管道工作正常。")
        print("你现在可以运行完整的数据获取命令：")
        print("uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210105")
    else:
        print("\n❌ 测试失败，请检查配置和错误信息。")
        sys.exit(1)
