# 2.4 亿条深圳共享单车数据集获取完整教程【开发者版】

本# 从 fetcher-legacy 到 TimescaleDB 异步高并发：工程设计与取舍

本文聚焦"为什么要放弃 `scr/data_pipline/fetcher-legacy.py`，改用现在的 TimescaleDB + 异步高并发流水线（`scr/data_pipline/fetcher` 等）"。

## 痛点复盘：legacy 的边界

- **吞吐瓶颈**：单线程顺序请求 + 逐页写 CSV，网络等待无法并行叠加；面对 2.4 亿## 与代码位置对应

- **采集**：`scr/data_pipline/fetcher.py`
- **数据库设置**：`scr/data_pipline/db.py`（包含 TimescaleDB 分区设置）
- **数据配置**：`scr/data_pipline/profiles.py`（包含双坐标系表结构）
- **坐标转换**：`scr/data_pipline/coords.py`（支持多种坐标系转换）
- **审计**：`scr/data_pipline/audit_days.py`
- **导出**：`scr/data_pipline/export_share.py`（支持双坐标系导出）

> 运行指引请见项目 README 的"快速运行/审计/导出"章节；本文侧重设计与取舍。别"。
- **易中断且不可恢复**：异常页/超时导致长跑失败；没有断点续跑与去重，追加 CSV 难以幂等。
- **I/O 与二次导入成本高**：海量 CSV 写盘 → 再导入数据库 → 再建索引，重复工作多且慢。
- **分析链路断裂**：缺少空间类型/索引；后续 SQL 分析前需要额外搬运与转换。
- **时序查询性能差**：传统表结构面对亿级时序数据查询缓慢。

## 目标与约束

- **高吞吐**：把"等待"并行化，尽可能跑满带宽与数据库写入能力。
- **可恢复**：失败重试、断点续跑、幂等写入，长周期运行不中断。
- **时序优化**：TimescaleDB 自动分区，提升大规模时序数据查询性能。
- **坐标统一**：实时转换坐标系，避免后期批量回填的复杂性。
- **可审计**：产出日粒度对账，发现缺口可定向补采。
- **易维护**：配置化的 Dataset Profile，表结构/索引/视图工程化管理。如何使用本仓库的异步采集 + TimescaleDB + PostGIS 入库流水线，以可靠、高吞吐的方式获取深圳共享单车约 2.44 亿条骑行记录，并产出可复用的数据资产与审计报表。

## 适用读者

- 需要批量/长期稳定采集市开放平台数据的研发、数据工程师
- 需要在数据库内直接进行空间分析与统计的 GIS/数据分析师
- 需要落地可维护的"数据→SQL→可视化/分析"工作流的团队

## 架构概览

- **采集**：`aiohttp` + 限流 + 指数退避 + 容错解析（JSON/HTML）
- **时序优化**：TimescaleDB 按 `start_time` 自动按天分区，支持亿级数据高效查询
- **坐标处理**：实时转换 BD09LL/GCJ-02 → WGS84，同时保留原始坐标
- **增量续跑**：按数据集 profile 的 `latest_date_column` 从库中 MAX(列)+1 天续跑
- **入库优化**：`psycopg` 的 COPY 批量写入；空间列使用 `geometry(Point,4326)` 并建 GIST 索引据集获取完整教程【开发者版】

本文面向工程/数据平台同学，详细讲解如何使用本仓库的异步采集 + PostGIS 入库流水线，以可靠、高吞吐的方式获取深圳共享单车约 2.44 亿条骑行记录，并产出可复用的数据资产与审计报表。

## 适用读者

- 需要批量/长期稳定采集市开放平台数据的研发、数据工程师
- 需要在数据库内直接进行空间分析与统计的 GIS/数据分析师
- 需要落地可维护的“数据→SQL→可视化/分析”工作流的团队

## 架构概览

- 采集：`aiohttp` + 限流 + 指数退避 + 容错解析（JSON/HTML）
- 增量：按数据集 profile 的 `latest_date_column` 从库中 MAX(列)+1 天续跑
- 入库：`psycopg` 的 COPY 批量写入；空间列使用 `geometry(Point,4326)` 并建 GIST 索引

# 从 fetcher-legacy 到异步高并发：工程设计与取舍

本文聚焦“为什么要放弃 `scr/data_pipline/fetcher-legacy.py`，改用现在的异步高并发流水线（`scr/data_pipline/fetcher` 等）”。

## 痛点复盘：legacy 的边界

- 吞吐瓶颈：单线程顺序请求 + 逐页写 CSV，网络等待无法并行叠加；面对 2.4 亿量级会拖到“月级别”。
- 易中断且不可恢复：异常页/超时导致长跑失败；没有断点续跑与去重，追加 CSV 难以幂等。
- I/O 与二次导入成本高：海量 CSV 写盘 → 再导入数据库 → 再建索引，重复工作多且慢。
- 分析链路断裂：缺少空间类型/索引；后续 SQL 分析前需要额外搬运与转换。

## 目标与约束

- 高吞吐：把“等待”并行化，尽可能跑满带宽与数据库写入能力。
- 可恢复：失败重试、断点续跑、幂等写入，长周期运行不中断。
- 可审计：产出日粒度对账，发现缺口可定向补采。
- 易维护：配置化的 Dataset Profile，表结构/索引/视图工程化管理。

## 关键设计决策

1. **TimescaleDB 时序优化**

- 按 `start_time` 列自动按天分区，显著提升时序数据查询性能
- 复合主键 `(id, start_time)` 满足 TimescaleDB 分区要求
- 利用 TimescaleDB 的压缩和保留策略管理历史数据

2. **协程优先而非线程/进程**

- 任务 IO 密集（HTTP 请求 + 等待），协程切换轻、占用低；线程上下文切换更重，进程模型合并写入更复杂。

3. **两层并发与背压**

- 外层"按天"并发控制失败边界与日志可读性；内层"按页"并发填满带宽。
- 信号量 + 队列背压，避免压垮接口与数据库。

4. **实时坐标转换策略**

- 采集时同步完成 BD09LL/GCJ-02 → WGS84 转换，避免后期批量回填
- 同时保留原始坐标和转换后坐标，满足不同分析需求
- 标记 `source_crs` 字段便于溯源

5. **失败视为常态**（重试 + 指数退避 + HTML 回退）

- 平台偶尔返回 HTML/空页，不当做致命错误；跳过坏页、保留日志，整体任务继续前进。

6. **增量续跑**

- 以目标表的 `MAX(日期列)` 为起点（+1 天），和配置窗口取交集；幂等入库避免重复。

7. **直接 COPY 入库**

- `psycopg` COPY 批量写入显著快于逐行 INSERT；空间列采用 `geometry(Point,4326)`，并建立 GIST 索引。

## 小片段（简化示意）

### 限流 + 指数退避 + 容错解析

```python
import asyncio, json, random
from contextlib import asynccontextmanager

sem_page = asyncio.Semaphore(MAX_CONCURRENCY)

@asynccontextmanager
async def page_slot():
  async with sem_page:
    yield

async def fetch_page(session, url, params, timeout=20, retries=5):
  backoff = 0.5
  for _ in range(retries):
    try:
      async with page_slot():
        async with session.get(url, params=params, timeout=timeout) as r:
          text = await r.text()
          try:
            return json.loads(text)
          except Exception:
            # 平台可能返回 HTML，视为坏页但不中断
            if text.lstrip().startswith("<"):
              return None
            raise
    except Exception:
      await asyncio.sleep(backoff + random.random() * 0.2)
      backoff = min(backoff * 2, 8)
  return None
```

### TimescaleDB 分区表创建

```python
# 创建分区表（示意）
async def setup_timescale_hypertable(conn, table_name, partition_column, interval):
    async with conn.cursor() as cur:
        # 创建基础表
        await cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id BIGSERIAL,
                user_id TEXT,
                company_id TEXT,
                start_time TIMESTAMPTZ,
                end_time TIMESTAMPTZ,
                start_geom_raw GEOMETRY(Point,4326),
                end_geom_raw GEOMETRY(Point,4326),
                start_geom_wgs84 GEOMETRY(Point,4326),
                end_geom_wgs84 GEOMETRY(Point,4326),
                source_crs TEXT,
                PRIMARY KEY (id, {partition_column})
            )
        """)
        
        # 创建 TimescaleDB 超表
        await cur.execute(f"""
            SELECT create_hypertable('{table_name}', '{partition_column}',
                                   chunk_time_interval => INTERVAL '{interval}',
                                   if_not_exists => TRUE)
        """)
```

### 实时坐标转换 + 批量 COPY 入库

```python
import io, csv
from eviltransform import gcj2wgs, bd2wgs

async def ingest_rows_with_transform(conn, rows):
    with conn.cursor() as cur:
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in rows:
            # 实时坐标转换
            start_raw = (float(r['start_lng']), float(r['start_lat']))
            end_raw = (float(r['end_lng']), float(r['end_lat']))
            
            # BD09LL -> WGS84 转换
            start_wgs84 = bd2wgs(*start_raw)
            end_wgs84 = bd2wgs(*end_raw)
            
            w.writerow([
                r['user_id'], r['company_id'], r['start_time'], r['end_time'],
                f"SRID=4326;POINT({start_raw[0]} {start_raw[1]})",  # raw
                f"SRID=4326;POINT({end_raw[0]} {end_raw[1]})",      # raw
                f"SRID=4326;POINT({start_wgs84[0]} {start_wgs84[1]})",  # wgs84
                f"SRID=4326;POINT({end_wgs84[0]} {end_wgs84[1]})",      # wgs84
                'bd09ll'  # source_crs
            ])
        buf.seek(0)
        cur.copy_expert(
            sql=(
                f"COPY {table_name} (user_id, company_id, start_time, end_time, "
                f"start_geom_raw, end_geom_raw, start_geom_wgs84, end_geom_wgs84, source_crs) "
                f"FROM STDIN WITH (FORMAT csv)"
            ),
            file=buf,
        )
    conn.commit()
```

### 增量续跑（确定起止日）

```python
from datetime import date, timedelta

def daterange(d1: date, d2: date):
  while d1 <= d2:
    yield d1
    d1 += timedelta(days=1)

# 从数据库读取已入库的最大日期（伪码）
max_in_db = get_max_date_from_db()  # None 表示空表
start = max_in_db + timedelta(days=1) if max_in_db else CONFIG_START
end = min(CONFIG_END, date.today())
```

## 性能与稳定性的取舍

- **rows/page**：5k~20k；过大失败代价高，过小请求数爆炸。
- **并发**：按天×按页分层调参，观察接口 429/超时曲线动态收敛。
- **事务批**：COPY 按日或按块提交，降低长事务风险。
- **索引**：时间（分区键）+ 空间（GIST）+ 过滤列，确保审计与导出查询高效。
- **TimescaleDB 调优**：合理设置 chunk_time_interval，平衡查询性能和管理复杂度。

## 失败模式演练

- **429/限流**：退避到稳定区间；必要时降低 MAX_CONCURRENCY。
- **HTML/空页**：记日志、计数、跳过；由审计报表推动补采。
- **DB 写入背压**：减小批次、调低并发或拆分事务。
- **TimescaleDB 分区问题**：确保分区键包含在主键中，避免约束冲突。

## 为什么不是线程/进程/CSV 管道

- **线程**：IO 密集下收益有限且管理复杂；协程更轻。
- **进程**：主要瓶颈不在 CPU，进程间合并写入与内存占用成本高。
- **纯 CSV 管道**：I/O 成本大、恢复与幂等复杂、分析链路长。
- **传统关系表**：面对亿级时序数据查询性能不佳，TimescaleDB 分区带来显著提升。

## TimescaleDB + PostGIS 的工程收益

- **时序优化**：自动分区 + 压缩，亿级数据仍保持高效查询
- **原生 geometry + GIST**：在分区基础上仍可做距离/相交等空间查询
- **COPY + 索引**：入库快、分析快；视图和物化视图标准化产出
- **运维友好**：利用 TimescaleDB 的数据保留、压缩策略自动管理历史数据

## 可观测性与审计

- 审计脚本输出 `day, db_count, api_total, delta`，用于对账与补采计划。
- 关键指标：错误率、退避次数、吞吐、DB TPS、每日 delta。

## 与代码位置对应

- 采集：`scr/data_pipline/fetcher.py`
- 回填：`scr/data_pipline/backfill_wgs84_from_raw.py`
- 审计：`scr/data_pipline/audit_days.py`
- 导出：`scr/data_pipline/export_share.py`（导出包含 user_id 以便做“同一用户”口径的统计，但不用于身份识别）

> 运行指引请见项目 README 的“快速运行/审计/导出”章节；本文侧重设计与取舍。
