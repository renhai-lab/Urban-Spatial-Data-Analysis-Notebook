-- 数据库初始化脚本
-- 自动创建扩展

-- 创建PostGIS扩展
CREATE EXTENSION IF NOT EXISTS postgis;

-- 创建TimescaleDB扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 设置时区
SET timezone = 'Asia/Shanghai';

-- 显示安装的扩展
SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'timescaledb');

-- 显示PostGIS版本
SELECT PostGIS_Version();

-- 显示TimescaleDB版本
SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';
