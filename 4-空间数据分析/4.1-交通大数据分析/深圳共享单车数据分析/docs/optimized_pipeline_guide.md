# 优化版数据管道使用指南

## 概述

这是一个全新的优化版数据管道，相比原版本有以下改进：

### 主要改进

1. **实时坐标转换**：在数据获取阶段就完成GCJ-02到WGS84的转换
2. **Times```bash
# 获取2021年1-8月的数据，自动转换坐标并导出raw+wgs84两套坐标
uv run python -m scr.data_pipline.fetcher_v2 \
  --start 20210101 \
  --end 20210830 \
  --auto-export \
  --export-coord-sets raw,wgs84 \
  --export-formats csv,geojson
```**：支持按时间自动分区，提升大数据量查询性能
3. **简化表结构**：去掉原始坐标列，直接保存WGS84坐标
4. **集成导出功能**：数据获取完成后自动按天导出CSV和GeoJSON
5. **更好的错误处理**：坐标转换失败时的容错机制

### 新的表结构

```sql
CREATE TABLE shenzhen_rides_v2 (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    company_id TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    start_geom_raw GEOMETRY(Point, 4326),       -- 原始坐标（直接保存API返回值）
    end_geom_raw GEOMETRY(Point, 4326),
    start_geom_wgs84 GEOMETRY(Point, 4326),     -- 转换后的WGS84坐标
    end_geom_wgs84 GEOMETRY(Point, 4326),
    source_crs TEXT DEFAULT 'GCJ-02'            -- 标记原始坐标系
);

-- TimescaleDB分区（按天）
SELECT create_hypertable('shenzhen_rides_v2', 'start_time', 
                         chunk_time_interval => INTERVAL '1 day');
```

## 环境准备

### 1. 安装TimescaleDB

**Docker Compose方式（最简单）：**

```bash
# 1. 修改docker-compose.yml中的密码
# 2. 启动服务
docker-compose up -d

# 3. 检查服务状态
docker-compose logs timescaledb

# 4. 连接数据库测试
psql -h localhost -U postgres -d shenzhen_bike
# 检查扩展：SELECT extname FROM pg_extension;
```

**本地安装方式：**

1. 先安装PostgreSQL 14+
2. 下载并安装TimescaleDB：https://docs.timescale.com/install/
3. 在数据库中启用扩展

### 2. 配置环境变量

更新 `.env` 文件：

```env
# 数据库配置
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=shenzhen_bike

# 表配置
TABLE_NAME=shenzhen_rides_v2

# API配置
APP_KEY=your_app_key

# 其他配置...
```

## 使用方法

### 1. 全量数据获取（推荐）

从头开始获取所有数据，实时转换坐标并自动导出：

```bash
# 获取2021年1-8月的数据，自动转换坐标和导出
uv run python -m scr.data_pipline.fetcher_v2 \
  --start 20210101 \
  --end 20210830 \
  --auto-export \
  --export-formats csv,geojson
```

### 2. 增量更新

从数据库最新日期继续获取：

```bash
# 自动从数据库最新日期+1天开始
uv run python -m scr.data_pipline.fetcher_v2 \
  --auto-export
```

### 3. 测试运行

先运行少量天数测试：

```bash
# 只处理前5天数据进行测试
uv run python -m scr.data_pipline.fetcher_v2 \
  --start 20210101 \
  --days-limit 5 \
  --auto-export
```

### 4. 仅导出数据

如果数据已在数据库中，单独运行导出：

```bash
# 导出指定日期范围的数据，同时导出raw和wgs84坐标
uv run python -m scr.data_pipline.export_dual \
  --start 20210101 \
  --end 20210105 \
  --table shenzhen_rides_v2 \
  --coord-sets raw,wgs84 \
  --formats csv,geojson \
  --output data/share
```

## 参数说明

### fetcher_v2.py 参数

- `--profile`: 数据集类型（bike/weather_grid），默认bike
- `--start`: 开始日期 YYYYMMDD，默认从数据库最新日期+1开始
- `--end`: 结束日期 YYYYMMDD，默认使用配置文件中的结束日期
- `--auto-export`: 自动导出数据，默认True
- `--export-coord-sets`: 导出坐标系，默认raw,wgs84
- `--export-formats`: 导出格式，默认csv,geojson
- `--days-limit`: 限制处理天数（用于测试）

### export_dual.py 参数

- `--start`: 开始日期 YYYYMMDD
- `--end`: 结束日期 YYYYMMDD  
- `--table`: 表名，默认shenzhen_rides_v2
- `--coord-sets`: 坐标系，默认raw,wgs84
- `--formats`: 导出格式，默认csv,geojson
- `--output`: 输出目录，默认data/share
- `--batch`: 批处理大小，默认50000
- `--workers`: 并发数，默认4

## 输出结构

### 数据库表

所有数据存储在TimescaleDB中，按天自动分区：

```sql
-- 查看分区信息
SELECT * FROM timescaledb_information.chunks 
WHERE hypertable_name = 'shenzhen_rides_v2' 
ORDER BY chunk_name;

-- 查询某天数据
SELECT count(*) FROM shenzhen_rides_v2 
WHERE start_time::date = '2021-01-01';

-- 查询某个区域的数据（利用空间索引）
SELECT * FROM shenzhen_rides_v2 
WHERE ST_DWithin(start_geom_wgs84, ST_Point(114.1, 22.5), 0.01)
  AND start_time BETWEEN '2021-01-01' AND '2021-01-02';
```

### 导出文件

```
data/share/
├── raw/                          # 原始坐标系文件
│   ├── csv_zip/
│   │   ├── bike_data_20210101.zip
│   │   └── bike_data_20210102.zip
│   └── geojson_zip/
│       ├── bike_data_20210101.zip
│       └── bike_data_20210102.zip
└── wgs84/                        # WGS84坐标系文件
    ├── csv_zip/
    │   ├── bike_data_20210101.zip
    │   └── bike_data_20210102.zip
    └── geojson_zip/
        ├── bike_data_20210101.zip
        └── bike_data_20210102.zip
```

### CSV文件字段

**Raw坐标系版本：**
```csv
id,user_id,company_id,start_time_cn,end_time_cn,start_lng_raw,start_lat_raw,end_lng_raw,end_lat_raw
1,user001,company1,2021-01-01T08:30:00,2021-01-01T08:45:00,114.123456,22.123456,114.134567,22.134567
```

**WGS84坐标系版本：**
```csv
id,user_id,company_id,start_time_cn,end_time_cn,start_lng_wgs84,start_lat_wgs84,end_lng_wgs84,end_lat_wgs84
1,user001,company1,2021-01-01T08:30:00,2021-01-01T08:45:00,114.120123,22.120123,114.131234,22.131234
```

### GeoJSON文件结构

**WGS84坐标系版本（包含CRS声明）：**
```json
{
  "type": "FeatureCollection",
  "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [114.120123, 22.120123]},
      "properties": {
        "id": 1,
        "user_id": "user001",
        "company_id": "company1", 
        "start_time_cn": "2021-01-01T08:30:00",
        "end_time_cn": "2021-01-01T08:45:00",
        "point_type": "start"
      }
    }
  ]
}
```

**Raw坐标系版本（不声明CRS，因为可能是GCJ-02等）：**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [114.123456, 22.123456]},
      "properties": {
        "id": 1,
        "user_id": "user001",
        "company_id": "company1", 
        "start_time_cn": "2021-01-01T08:30:00",
        "end_time_cn": "2021-01-01T08:45:00",
        "point_type": "start"
      }
    }
  ]
}
```

## 性能优化

### 1. TimescaleDB分区优势

- **查询性能**：按时间查询时只扫描相关分区
- **维护性能**：可以按分区进行维护操作
- **存储优化**：旧数据可以压缩存储

### 2. 空间索引

```sql
-- 自动创建的GIST索引用于空间查询
CREATE INDEX idx_start_geom_wgs84_v2 ON shenzhen_rides_v2 USING GIST (start_geom_wgs84);
CREATE INDEX idx_end_geom_wgs84_v2 ON shenzhen_rides_v2 USING GIST (end_geom_wgs84);
```

### 3. 批量操作配置

在 `config.py` 中调整参数：

```python
# 提高并发数（根据服务器性能调整）
MAX_CONCURRENCY = 10
DAYS_CONCURRENCY = 3

# 增加每页行数（减少API调用次数）
ROWS_PER_PAGE = 10000

# 调整批量插入大小
BATCH_SIZE = 50000
```

## 监控和日志

### 程序日志

```bash
# 查看实时日志
tail -f logs/fetch_v2_*.log

# 搜索错误
grep -i error logs/fetch_v2_*.log

# 统计坐标转换错误
grep "坐标转换失败" logs/fetch_v2_*.log | wc -l
```

### 数据库监控

```sql
-- 查看表大小
SELECT 
  schemaname,
  tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE tablename LIKE '%rides_v2%';

-- 查看每日数据量
SELECT 
  start_time::date as day,
  count(*) as records,
  count(start_geom_wgs84) as with_start_coord,
  count(end_geom_wgs84) as with_end_coord
FROM shenzhen_rides_v2 
GROUP BY start_time::date 
ORDER BY day;

-- 查看坐标系分布
SELECT source_crs, count(*) 
FROM shenzhen_rides_v2 
GROUP BY source_crs;
```

## 故障排除

### 1. 坐标转换错误

如果日志中出现大量坐标转换错误：

```python
# 检查原始坐标范围
SELECT 
  min(ST_X(start_geom_raw)), max(ST_X(start_geom_raw)),
  min(ST_Y(start_geom_raw)), max(ST_Y(start_geom_raw))
FROM old_table;

# 深圳正常经纬度范围：
# 经度：113.7-114.7
# 纬度：22.4-22.9
```

### 2. TimescaleDB相关问题

```sql
-- 检查TimescaleDB扩展
SELECT * FROM pg_extension WHERE extname = 'timescaledb';

-- 查看超表信息
SELECT * FROM timescaledb_information.hypertables;

-- 如果分区创建失败，手动创建
SELECT create_hypertable('shenzhen_rides_v2', 'start_time', 
                         chunk_time_interval => INTERVAL '1 day',
                         if_not_exists => TRUE);
```

### 3. 导出问题

```python
# 检查导出目录权限
import os
os.makedirs("data/share/wgs84", exist_ok=True)

# 检查磁盘空间
df -h
```

## 迁移指南

### 从旧版本迁移

如果你已经有旧版本的数据：

1. **备份旧数据**：
```sql
CREATE TABLE shenzhen_rides_backup AS SELECT * FROM shenzhen_rides;
```

2. **运行新版本获取程序**：
```bash
uv run python -m scr.data_pipline.fetcher_v2 --start 20210101 --end 20210830
```

3. **对比数据量**：
```sql
SELECT 'old' as version, count(*) FROM shenzhen_rides
UNION ALL
SELECT 'new' as version, count(*) FROM shenzhen_rides_v2;
```

### 性能对比

新版本相比旧版本的优势：

- **存储空间**：减少约30%（去掉重复坐标列）
- **查询性能**：时间范围查询提升10-50倍（TimescaleDB分区）
- **空间查询**：性能基本一致（都有GIST索引）
- **数据获取**：速度基本一致，但减少了后期回填成本

## 最佳实践

1. **分阶段运行**：先运行少量数据测试，确认无误后再全量运行
2. **监控资源**：注意数据库连接数、磁盘空间、网络流量
3. **定期备份**：重要数据及时备份
4. **日志管理**：定期清理旧日志文件
5. **配置调优**：根据服务器性能调整并发参数
