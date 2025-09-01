# 深圳共享单车数据快速上手指南

本指南帮你快速开始使用深圳共享单车数据管道，从环境搭建到数据获取，10分钟内完成第一次数据采集。

## 🚀 一键启动（推荐新手）

### 环境准备

1. **安装 Docker**（如果还没有）
   - Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Mac: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Linux: `curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh`

2. **安装 Python 包管理器 uv**
   ```bash
   # Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # Mac/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

### 数据库启动

```bash
# 启动 TimescaleDB + PostGIS（一体化方案）
docker run -d \
  --name shenzhen-bike-db \
  -e POSTGRES_PASSWORD=your_password_here \
  -e POSTGRES_DB=shenzhen_bike \
  -p 5432:5432 \
  timescale/timescaledb-ha:pg17

# 等待30秒让数据库完全启动
sleep 30

# 创建必要的扩展
docker exec shenzhen-bike-db psql -U postgres -d shenzhen_bike -c \
  "CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS postgis;"
```

### 配置项目

```bash
# 克隆项目（如果还没有）
git clone <项目地址>
cd 深圳共享单车数据分析

# 复制配置文件
cp .env.example .env

# 编辑 .env 文件，修改密码
# POSTGRES_PASSWORD=your_password_here （改成你上面设置的密码）
```

### 第一次数据获取

```bash
# 安装依赖
uv sync

# 获取一天的数据进行测试
uv run python -m scr.data_pipline.fetcher --start 20210118 --end 20210118

# 如果成功，获取更多数据
uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210105
```

## 📊 获取和导出数据

### 批量获取数据

```bash
# 获取指定日期范围的数据
uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210130

# 同时获取数据并导出
uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210105 \
  --auto-export --export-coord-sets raw,wgs84 --export-formats csv,geojson
```

### 导出已有数据

```bash
# 导出 WGS84 坐标数据（推荐）
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210105 \
  --coord-sets wgs84 --formats csv,geojson --out data/share

# 导出双坐标系数据
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210105 \
  --coord-sets raw,wgs84 --formats csv,geojson --out data/share
```

## 🔍 数据查看和分析

### 在数据库中查询

```sql
-- 连接数据库
psql -h localhost -U postgres -d shenzhen_bike

-- 查看基础统计
SELECT 
  DATE(start_time AT TIME ZONE 'Asia/Shanghai') as date,
  COUNT(*) as trips,
  COUNT(DISTINCT company_id) as companies,
  COUNT(DISTINCT user_id) as users
FROM shenzhen_rides 
WHERE start_time >= '2021-01-01' AND start_time < '2021-01-02'
GROUP BY DATE(start_time AT TIME ZONE 'Asia/Shanghai')
ORDER BY date;

-- 查看空间分布（需要有 WGS84 坐标）
SELECT 
  company_id,
  COUNT(*) as trips,
  ST_AsText(ST_Centroid(ST_Union(start_geom_wgs84))) as center
FROM shenzhen_rides 
WHERE start_time >= '2021-01-01' AND start_time < '2021-01-02'
  AND start_geom_wgs84 IS NOT NULL
GROUP BY company_id;
```

### 用 Python 分析

```python
import pandas as pd
import matplotlib.pyplot as plt

# 读取导出的数据
df = pd.read_csv('data/share/wgs84/csv_zip/bike_data_20210101_wgs84.zip')

# 基础统计
print(f"总行程数: {len(df)}")
print(f"运营公司: {df['company_id'].nunique()}")
print(f"活跃用户: {df['user_id'].nunique()}")

# 时间分布
df['hour'] = pd.to_datetime(df['start_time_cn']).dt.hour
hourly_trips = df['hour'].value_counts().sort_index()

plt.figure(figsize=(12, 6))
hourly_trips.plot(kind='bar')
plt.title('每小时行程分布')
plt.xlabel('小时')
plt.ylabel('行程数')
plt.show()
```

## 🗺️ 地图可视化

### 使用 kepler.gl（最简单）

1. 打开 [https://kepler.gl/demo](https://kepler.gl/demo)
2. 拖拽 `data/share/wgs84/geojson_zip/2021-01-01.geojson.zip` 到页面
3. 解压后选择 .geojson 文件
4. 在图层设置中选择 Point 类型
5. 可以按 `start_time_cn` 添加时间过滤器

### 使用 QGIS（专业版）

1. 下载安装 [QGIS](https://qgis.org/download/)
2. 添加图层 → 矢量图层 → 选择解压后的 .geojson 文件
3. 右键图层 → 属性 → 符号系统，设置点样式
4. 可以按属性进行分类渲染（如按 company_id 着色）

## 📈 数据审计

```bash
# 检查数据完整性
uv run python -m scr.data_pipline.audit_days

# 查看审计报告
cat data/audit/daily_counts_with_api.csv
```

## 🔧 常用配置调优

编辑 `.env` 文件进行性能调优：

```env
# 提高并发（谨慎调整，避免被限流）
MAX_CONCURRENCY=10
DAYS_CONCURRENCY=3
ROWS_PER_PAGE=15000

# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL=INFO

# TimescaleDB 优化
TS_TUNE_MEMORY=4GB
TS_TUNE_NUM_CPUS=4
```

## 🚨 常见问题解决

### 数据库连接失败
```bash
# 检查容器状态
docker ps
docker logs shenzhen-bike-db

# 重启数据库
docker restart shenzhen-bike-db
```

### API 请求频率过高
```env
# 降低并发设置
MAX_CONCURRENCY=5
DAYS_CONCURRENCY=1
RETRY_DELAY_SECONDS=10
```

### 内存不足
```env
# 减小批次大小
DB_BATCH_SIZE=5000
EXPORT_BATCH_SIZE=20000
BUFFER_SIZE_MB=50
```

## 📚 下一步学习

- **空间分析**: 学习 PostGIS 空间查询和分析
- **数据可视化**: 掌握 kepler.gl、QGIS 或 Python 地图库
- **大数据处理**: 了解 TimescaleDB 的高级特性
- **机器学习**: 基于行程数据进行预测和聚类分析

## 💡 提示

- 首次运行建议先测试小范围日期（1-3天）
- WGS84 坐标系适合与其他地理数据叠加分析
- 原始坐标保留了数据的原始特征，适合特定研究场景
- 大规模数据处理时要注意磁盘空间和网络带宽

祝你数据分析愉快！🎉
