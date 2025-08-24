# 深圳共享单车 2.4 亿级数据获取与 PostGIS 分析流水线（适用于深圳市政府开放平台的大部分数据的获取）

本项目聚焦两部分：

- scr/data_pipline：面向“共享单车”和“气象格点”两类数据集的数据获取与入库流水线
- sql：PostGIS 下的空间表构建、天气格网几何生成、视图与索引脚本

## 项目特色

- 异步高吞吐：aiohttp + 并发限流，按天并发抓取，自动重试与指数退避
- 稳健解析：容错 JSON 解析，自动识别 HTML 降级，跳过异常页，日志可溯源
- 增量续跑：启动前查询目标表 MAX(时间列)，从次日接续，避免重复
- 高效入库：psycopg COPY 批量写入，WGS84 geography(Point) 存储坐标，GIST 空间索引
- 配置即插拔：Dataset Profile 抽象，轻松切换 bike / weather_grid 并扩展新数据集
- SQL 工程化：提供天气格点几何构建、字段规范化、索引与视图，便于后续分析

## 为什么使用 PostGIS？

- 原生空间类型与索引：geography/geometry + GIST，使距离、缓冲、相交等空间运算在亿级规模仍可查询
- 与 Python/SQL 协同：流水线直接写入空间类型列，SQL 分析即可产出特征与视图，无需反复导出/导入
- 工程可维护性：表结构、索引、视图作为基础设施明确固化，支持增量和长周期运行

## 环境要求

- Python >= 3.13（已提供 pyproject.toml，推荐使用 uv）
- PostgreSQL 14+（建议 16）
- PostGIS 扩展

## 安装依赖（Python）

```powershell
# 推荐：使用 uv（已配置清华镜像）
uv sync
```

## 安装与启用 PostGIS（Windows）

任选其一：

- 本机安装[（StackBuilder）](https://download.osgeo.org/postgis/windows/)：安装 PostgreSQL 后，打开 StackBuilder 勾选 PostGIS 插件安装；在目标数据库执行：

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

- Docker 运行（示例）：

```powershell
docker run -d --name pg-postgis -e POSTGRES_PASSWORD=your_password -p 5432:5432 postgis/postgis:16-3.4
# 首次连接后在数据库内执行：CREATE EXTENSION postgis;
```

提示：本项目的初始化程序会尝试执行 CREATE EXTENSION IF NOT EXISTS postgis；如无权限或未安装将记录提醒。

## 配置（.env）

在项目根目录复制 `.env.example` 并编辑  `.env `（可覆盖 `scr/data_pipline/config.py` 中的值）。

密钥一定要保存在  `.env `中。

更多项见 `scr/data_pipline/config.py`。

## 数据集 Profiles（scr/data_pipline）

- bike（共享单车）

  - 表：shenzhen_rides（可通过 TABLE_NAME 覆盖）
  - 列：user_id, company_id, start_time, end_time, start_geom, end_geom
  - 类型：时间列 TIMESTAMPTZ；坐标 geography(Point,4326)
  - 索引：start_time、start_geom(GIST)、end_geom(GIST)
  - 增量列：start_time
- weather_grid（深圳范围自动站实况格点）

  - 表：sz_weather_grid
  - 列：recid、ddatetime、gridid、…、crttime、keyid（详见 `profiles.py`）
  - 索引：crttime、ddatetime、gridid
  - 增量列：crttime

## 快速运行

```powershell
# 方式 A：使用 uv 运行
uv run python -m scr.data_pipline.fetcher

# 方式 B：现有虚拟环境
.venv\Scripts\python -m scr.data_pipline.fetcher
```

运行时会：

- 自动初始化目标表与索引（若不存在）
- 查询数据库中最新日期，按配置范围增量抓取
- 并发分页请求，批量 COPY 入库
- 生成日志到控制台与 logs/ 目录

常用调参：ROWS_PER_PAGE、MAX_CONCURRENCY、DAYS_CONCURRENCY、DATA_START_DATE/DATA_END_DATE、LOG_LEVEL。

## 获取“全量数据”不建议使用 fetcher-legacy.py 的原因

`scr/data_pipline/fetcher-legacy.py` 为教学/演示用简化脚本，特点是按页追加写 CSV：

- 不做断点续跑、去重与强健重试；异常页会中断或丢失
- 单线程请求，面对 2.4 亿量级极慢；CSV 体量与 I/O 成本高
- 无数据库索引与空间类型，后续分析需二次导入

因此：

- 全量与长周期采集，请使用异步版 `scr/data_pipline/fetcher.py` + PostGIS 入库
- 若仅需“某一天”的样例数据/快速 CSV，可用 legacy：

```powershell
python scr\data_pipline\fetcher-legacy.py
# 将 startDate=endDate 设置为目标日期（如 20210101），输出到 data/raw/
```

## SQL 工作流（sql）

以“天气格网几何 + 观测数据”为例，提供一套工程化脚本：

1. 创建并导入格网基础信息（create_sz_weather_grid_cells.sql）

- 建立 stage 与目标几何表结构；随后用 psql 将 CSV 导入 stage：

```sql
-- 注意使用列名导入以避免顺序问题
\copy public.sz_weather_grid_cells_stage (X1,Y2,YINDEX,XINDEX,RECID,Y1,X2,CODE)
FROM 'data/raw/深圳范围自动站实况格点信息表_2920000903510.csv' CSV HEADER ENCODING 'UTF8';
```

2. 转换为 Polygon/Point，并创建索引（load_sz_weather_grid_cells.sql）

- 将经纬度边界构成 Polygon 几何，生成质心，建立 GIST 索引

3. 规范化主表键、索引与外键（augment_sz_weather_grid_keys.sql）

- 为 `sz_weather_grid` 生成 `recid_int`，并（可选）外键关联 `sz_weather_grid_cells(recid)`

4. 视图（views_sz_weather_grid.sql）

- `v_sz_weather_grid`：几何与观测全量联接
- `v_sz_weather_grid_latest`：每格最新一条（按 ddatetime 优先，否则 crttime），便于快速绘图/统计

执行顺序建议：create → 导入 CSV → load → augment → views。

## 示例特征视图（共享单车）

入库后可直接在数据库中派生统计特征：

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bike_features AS
SELECT
  id, user_id, company_id, start_time, end_time, start_geom, end_geom,
  EXTRACT(EPOCH FROM (end_time - start_time))::bigint AS duration_seconds,
  CASE WHEN start_geom IS NOT NULL AND end_geom IS NOT NULL
	  THEN ST_Distance(start_geom, end_geom)
	  ELSE NULL END AS distance_meters,
  CASE WHEN end_time > start_time AND start_geom IS NOT NULL AND end_geom IS NOT NULL
	  THEN (ST_Distance(start_geom, end_geom) / 1000.0) / (EXTRACT(EPOCH FROM (end_time - start_time)) / 3600.0)
	  ELSE NULL END AS speed_kmh
FROM shenzhen_rides;

CREATE INDEX IF NOT EXISTS idx_mv_bike_features_time ON mv_bike_features (start_time);
```

## 常见问题

- 400/404：多为该日无数据或参数不支持，程序会跳过
- 响应非 JSON：平台偶返 HTML，程序会降级并跳过该页
- 性能优化：调大 ROWS_PER_PAGE、合理设置并发；确保时间/空间索引存在
- 续跑策略：以各 Profile 的 latest_date_column 为准，从数据库 MAX(列)+1 天开始

## 日志

输出到控制台与 `logs/fetch_log_*.log`（可通过 LOG_LEVEL 控制详细程度）。
