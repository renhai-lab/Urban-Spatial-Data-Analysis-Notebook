-- TimescaleDB 气象格点表主键迁移脚本
-- 从 PRIMARY KEY (id, crttime) 迁移到 PRIMARY KEY (keyid, crttime)
-- 
-- 执行步骤：
-- 1. 停止所有数据写入操作
-- 2. 备份原表数据（可选但推荐）
-- 3. 执行此脚本
-- 4. 验证数据完整性
-- 5. 恢复数据写入

-- 备份原表（保险起见）
CREATE TABLE sz_weather_grid_backup AS 
SELECT * FROM sz_weather_grid;

-- 删除 TimescaleDB hypertable（会删除所有 chunks）
DROP TABLE IF EXISTS sz_weather_grid CASCADE;

-- 重新创建表（新主键）
CREATE TABLE sz_weather_grid (
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
    keyid TEXT UNIQUE NOT NULL,
    PRIMARY KEY (keyid, crttime)
);

-- 创建 TimescaleDB hypertable（按 crttime 分区）
SELECT create_hypertable('sz_weather_grid', 'crttime',
                         chunk_time_interval => INTERVAL '1 day',
                         if_not_exists => TRUE);

-- 创建索引
CREATE INDEX idx_wg_crttime ON sz_weather_grid (crttime);
CREATE INDEX idx_wg_forecasttime ON sz_weather_grid (forecasttime);
CREATE INDEX idx_wg_gridid ON sz_weather_grid (gridid);

-- 从备份表恢复数据
INSERT INTO sz_weather_grid 
SELECT * FROM sz_weather_grid_backup;

-- 验证数据完整性
SELECT 
    'sz_weather_grid' as table_name,
    COUNT(*) as total_records,
    COUNT(DISTINCT keyid) as unique_keyids,
    MIN(crttime) as earliest_crttime,
    MAX(crttime) as latest_crttime
FROM sz_weather_grid;

-- 数据完整性检查（应该显示 0 行，表示没有重复 keyid）
SELECT keyid, COUNT(*) as cnt
FROM sz_weather_grid
GROUP BY keyid
HAVING COUNT(*) > 1;

-- 清理备份表（可选）
-- DROP TABLE sz_weather_grid_backup;
