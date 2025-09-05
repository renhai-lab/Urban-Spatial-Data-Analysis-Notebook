# 深圳共享单车 2.4 亿条数据获取与 PostGIS 分析流水线（适用于深圳市政府开放平台的大部分数据的获取）

本项目聚焦两部分：

- scr/data_pipline：面向"共享单车"和"气象格点"两类数据集的数据获取与入库流水线
- sql：PostGIS 下的空间表构建、天气格网几何生成、视图与索引脚本

## 项目特色

- *## 获取"全量数据"不建议使用 fetcher-legacy.py 的原因

`scr/data_pipline/fetcher-legacy.py` 为教学/演示用简化脚本，特点是按页追加写 CSV：

- 不做断点续跑、去重与强健重试；异常页会中断或丢失
- 单线程请求，面对 2.4 亿量级极慢；CSV 体量与 I/O 成本高
- 无数据库索引与空间类型，后续分析需二次导入
- 不支持 TimescaleDB 分区，无法应对大规模时序数据

因此：

- **全量与长周期采集**，请使用异步版 `scr/data_pipline/fetcher.py` + TimescaleDB + PostGIS 入库
- **若仅需"某一天"的样例数据/快速 CSV**，可用 legacy：

```bash
python scr\data_pipline\fetcher-legacy.py
# 将 startDate=endDate 设置为目标日期（如 20210101），输出到 data/raw/
```

**：自动分区表按天分区，支持亿级数据高效存储与查询
- **实时坐标转换**：获取过程中同步完成 GCJ-02 → WGS84 转换，无需后期回填
- **双坐标系导出**：同时保留原始坐标和 WGS84 坐标，满足不同使用场景
- **异步高吞吐**：aiohttp + 并发限流，按天并发抓取，自动重试与指数退避
- **稳健解析**：容错 JSON 解析，自动识别 HTML 降级，跳过异常页，日志可溯源
- **增量续跑**：启动前查询目标表 MAX(时间列)，从次日接续，避免重复
- **高效入库**：psycopg COPY 批量写入，geometry(Point,4326) 存储坐标，GIST 空间索引
- **配置即插拔**：Dataset Profile 抽象，轻松切换 bike / weather_grid 并扩展新数据集
- **SQL 工程化**：提供天气格点几何构建、字段规范化、索引与视图，便于后续分析数据获取与 PostGIS 分析流水线（适用于深圳市政府开放平台的大部分数据的获取）

本项目聚焦两部分：

- scr/data_pipline：面向“共享单车”和“气象格点”两类数据集的数据获取与入库流水线
- sql：PostGIS 下的空间表构建、天气格网几何生成、视图与索引脚本

## 项目特色

- 异步高吞吐：aiohttp + 并发限流，按天并发抓取，自动重试与指数退避
- 稳健解析：容错 JSON 解析，自动识别 HTML 降级，跳过异常页，日志可溯源
- 增量续跑：启动前查询目标表 MAX(时间列)，从次日接续，避免重复
- 高效入库：psycopg COPY 批量写入，WGS84 geometry(Point,4326) 存储坐标，GIST 空间索引
- 配置即插拔：Dataset Profile 抽象，轻松切换 bike / weather_grid 并扩展新数据集
- SQL 工程化：提供天气格点几何构建、字段规范化、索引与视图，便于后续分析

## 为什么使用 PostGIS 和 TimescaleDB？

- **原生空间类型与索引**：geometry + GIST，使距离、缓冲、相交等空间运算在亿级规模仍可查询
- **时序数据优化**：TimescaleDB 按天自动分区，显著提升大规模时序数据的查询性能
- **与 Python/SQL 协同**：流水线直接写入空间类型列，SQL 分析即可产出特征与视图，无需反复导出/导入
- **工程可维护性**：表结构、索引、视图作为基础设施明确固化，支持增量和长周期运行

## 环境要求

- Python >= 3.13（已提供 pyproject.toml，推荐使用 uv）
- PostgreSQL 16+（推荐 17）+ PostGIS 3.5+
- TimescaleDB 2.17+（建议使用 2.21+ 版本以获得最佳性能）

### Docker 部署（推荐）

使用官方 TimescaleDB + PostGIS 镜像：

```bash
# 启动 TimescaleDB + PostGIS 容器
docker run -d \
  --name timescaledb-postgis \
  -e POSTGRES_PASSWORD=your_password_here \
  -e POSTGRES_DB=shenzhen_bike \
  -p 5432:5432 \
  timescale/timescaledb-ha:pg17

# 等待启动后连接并创建扩展
docker exec -it timescaledb-postgis psql -U postgres -d shenzhen_bike -c \
  "CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS postgis;"

如果是自己安装的postgres+postgis，记得先创建数据库。

```

## 安装依赖（Python）

```powershell
# 推荐：使用 uv（已配置清华镜像）
uv sync
```

## 安装与启用 PostGIS（本机安装）

任选其一：

- 本机安装[（StackBuilder）](https://download.osgeo.org/postgis/windows/)：安装 PostgreSQL 后，打开 StackBuilder 勾选 PostGIS 插件安装；在目标数据库执行：

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
```

- Docker 运行（见上方 Docker 部署）

提示：本项目的初始化程序会尝试执行 CREATE EXTENSION IF NOT EXISTS timescaledb/postgis；如无权限或未安装将记录提醒。

## 配置（.env）

在项目根目录复制 `.env.example` 并编辑 `.env`（可覆盖 `scr/data_pipline/config.py` 中的值）。

密钥一定要保存在 `.env` 中。

更多项见 `scr/data_pipline/config.py`。

## 数据集 Profiles（scr/data_pipline）

- bike（共享单车）

  - 表：shenzhen_rides（可通过 TABLE_NAME 覆盖）
  - **TimescaleDB 分区**：按 start_time 列自动按天分区，支持高效时序查询
  - 列：
    - user_id TEXT, company_id TEXT, start_time TIMESTAMPTZ, end_time TIMESTAMPTZ
    - **原始坐标**：start_geom_raw GEOMETRY(Point,4326), end_geom_raw GEOMETRY(Point,4326)
    - **WGS84坐标**：start_geom_wgs84 GEOMETRY(Point,4326), end_geom_wgs84 GEOMETRY(Point,4326)
    - source_crs TEXT（原始坐标系标识；示例：'bd09ll'/'gcj02'/'wgs84'）
  - 索引：
    - 时间：idx_start_time(start_time) - TimescaleDB 分区键
    - 空间（raw）：idx_start_geom_raw/idx_end_geom_raw（GIST）
    - 空间（wgs84）：idx_start_geom_wgs84/idx_end_geom_wgs84（GIST）
    - 过滤：idx_source_crs(source_crs)
  - 增量列：start_time
  - **实时坐标转换**：采集时自动完成 BD09LL/GCJ-02 → WGS84 转换
- weather_grid（深圳范围自动站实况格点）

  - 表：sz_weather_grid
  - 列：recid、ddatetime、gridid、…、crttime、keyid（详见 `profiles.py`）
  - 索引：crttime、ddatetime、gridid
  - 增量列：crttime

## 快速运行

### 基础数据获取

```bash
# 方式 A：使用 uv 运行（推荐）
uv run python -m scr.data_pipline.fetcher

# 方式 B：现有虚拟环境
.venv\Scripts\python -m scr.data_pipline.fetcher

# 指定日期范围 不指定日期的时候会从数据库中读取最新的日期 然后开始往后爬取
uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210105

# 同时导出双坐标系数据
uv run python -m scr.data_pipline.fetcher --start 20210101 --end 20210105 \
  --auto-export --export-coord-sets raw,wgs84 --export-formats csv,geojson
```

### 导出数据

```bash
# 导出指定日期范围的数据
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets wgs84 --formats csv,geojson --batch 50000 --out data/share

# 同时导出原始坐标和WGS84坐标
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets raw,wgs84 --formats csv,geojson --batch 50000 --out data/share
```

运行时会：

- 自动初始化 TimescaleDB 分区表与索引（若不存在）
- 查询数据库中最新日期，按配置范围增量抓取
- 实时完成坐标转换（BD09LL/GCJ-02 → WGS84）
- 并发分页请求，批量 COPY 入库
- 生成日志到控制台与 logs/ 目录

常用调参：ROWS_PER_PAGE、MAX_CONCURRENCY、DAYS_CONCURRENCY、DATA_START_DATE/DATA_END_DATE、LOG_LEVEL。

## 审计

按天核查工具：统计数据库内每日条数，找出缺失天/异常天，并导出 CSV。

`uv run python -m scr.data_pipline.audit_days`

输出：

- data/audit/daily_counts.csv  包含 day,cnt 两列，可以查看每天有多少数据。
- （主要看这个）data/audit/daily_counts_with_api.csv ：包含 day,db_count,api_total，delta（与数据库的差别）

共享单车全量共有244,622,889条数据，而20210101到20210830之间数据占绝大部分，有244,412,855条。

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

1. 转换为 Polygon/Point，并创建索引（load_sz_weather_grid_cells.sql）

- 将经纬度边界构成 Polygon 几何，生成质心，建立 GIST 索引

1. 规范化主表键、索引与外键（augment_sz_weather_grid_keys.sql）

- 为 `sz_weather_grid` 生成 `recid_int`，并（可选）外键关联 `sz_weather_grid_cells(recid)`

1. 视图（views_sz_weather_grid.sql）

- `v_sz_weather_grid`：几何与观测全量联接
- `v_sz_weather_grid_latest`：每格最新一条（按 ddatetime 优先，否则 crttime），便于快速绘图/统计

执行顺序建议：create → 导入 CSV → load → augment → views。

## 共享单车表结构说明（重要）

新版本数据管道采用以下优化设计：

### 表结构特性

1. **TimescaleDB 分区**：自动按 `start_time` 列按天分区，提升大数据查询性能
2. **双坐标系存储**：同时保存原始坐标和 WGS84 坐标
3. **实时坐标转换**：采集过程中自动完成坐标系转换，无需后期回填

### 核心字段

```sql
CREATE TABLE shenzhen_rides (
    id BIGSERIAL,
    user_id TEXT,
    company_id TEXT,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    -- 原始坐标（BD09LL/GCJ-02等）
    start_geom_raw GEOMETRY(Point,4326),
    end_geom_raw GEOMETRY(Point,4326),
    -- WGS84坐标（实时转换）
    start_geom_wgs84 GEOMETRY(Point,4326),
    end_geom_wgs84 GEOMETRY(Point,4326),
    -- 坐标系标识
    source_crs TEXT,
    PRIMARY KEY (id, start_time)  -- TimescaleDB 复合主键
);

-- 创建 TimescaleDB 超表
SELECT create_hypertable('shenzhen_rides', 'start_time', 
                        chunk_time_interval => INTERVAL '1 day');
```

### 索引策略

```sql
-- 时间索引（分区键）
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_start_time 
ON shenzhen_rides (start_time);

-- 空间索引（原始坐标）
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_start_geom_raw 
ON shenzhen_rides USING GIST (start_geom_raw);
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_end_geom_raw 
ON shenzhen_rides USING GIST (end_geom_raw);

-- 空间索引（WGS84坐标）
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_start_geom_wgs84 
ON shenzhen_rides USING GIST (start_geom_wgs84);
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_end_geom_wgs84 
ON shenzhen_rides USING GIST (end_geom_wgs84);

-- 过滤索引
CREATE INDEX IF NOT EXISTS idx_shenzhen_rides_source_crs 
ON shenzhen_rides (source_crs);
```

## 示例特征视图（共享单车）

入库后可直接在数据库中派生统计特征：

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bike_features AS
SELECT
  id, user_id, company_id, start_time, end_time,
  COALESCE(start_geom_wgs84, start_geom) AS start_geom,
  COALESCE(end_geom_wgs84, end_geom)     AS end_geom,
  EXTRACT(EPOCH FROM (end_time - start_time))::bigint AS duration_seconds,
  CASE WHEN COALESCE(start_geom_wgs84, start_geom) IS NOT NULL AND COALESCE(end_geom_wgs84, end_geom) IS NOT NULL
    THEN ST_Distance(COALESCE(start_geom_wgs84, start_geom), COALESCE(end_geom_wgs84, end_geom))
    ELSE NULL END AS distance_meters,
  CASE WHEN end_time > start_time AND COALESCE(start_geom_wgs84, start_geom) IS NOT NULL AND COALESCE(end_geom_wgs84, end_geom) IS NOT NULL
    THEN (ST_Distance(COALESCE(start_geom_wgs84, start_geom), COALESCE(end_geom_wgs84, end_geom)) / 1000.0)
      / (EXTRACT(EPOCH FROM (end_time - start_time)) / 3600.0)
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

## 延伸阅读

- 2.4 亿条深圳共享单车数据集获取完整教程【开发者版】：见 `docs/bike_240m_developer_guide.md`
- 小白使用指南：拿到 `data/share/raw` 后如何打开与可视化：见 `docs/beginner_guide_using_raw_share.md`

## 数据来源与合规说明

- 数据来源：深圳市政府数据开放平台（与其公共数据接口/下载渠道一致）。
- 仅限科研、教学与公共管理用途；请遵守平台服务条款与使用规范，严禁用于识别个人身份或进行商业化再分发。
- 隐私与去标识：采集与入库流程不包含可识别个人身份的信息；示例导出仅包含时间、空间位置及运营公司等业务字段。
- 坐标系说明：原始坐标可能为 GCJ-02/BD-09 或其他坐标系；请在分析前按文档回填/转换到 WGS84，并在对外发布前标注坐标系。
