>（更新上架）按日分的2.4亿条深圳共享单车企业每日订单表，分为csv和geojson文件
# 商品介绍（每日一个csv或者geojson文件，可导入数据库）

## 一句话概述
日级导出的深圳共享单车出行数据（含原始坐标 raw 与标准 WGS84 坐标双目录），CSV / GeoJSON，开箱即可用于可视化、统计分析与空间挖掘；兼容任意主流数据库 / 分析引擎导入（PostgreSQL/PostGIS、DuckDB、ClickHouse、SQLite、Pandas、GeoPandas 等）。

## 你将获得
```text
深圳共享单车企业每日订单表（每日一个csv或geojson文件）/
  wgs84/                    # 标准 WGS84 坐标（推荐用于分析与叠加）
    csv_zip/                # 每天一个 zip，内含该日 CSV
    geojson_zip/            # 每天一个 zip，内含该日 GeoJSON（起点点要素）
  raw/                      # 原始坐标（快速浏览/教学演示）
    csv_zip/
    geojson_zip/
  每日订单数量统计.csv
  README.pdf / 使用指引（可选）
  ```
- 日期覆盖：2021年1月1日到8月30日。 (结合官方和实际数据，只有20210101到20210830这一段时间的数据有意义。)
- 数据总量：244,412,855 条数据
- 双坐标系：原始坐标（可能为 GCJ-02 / BD09LL 等，未做纠偏）+ 已转换 WGS84 坐标（可用于对齐卫星 / OSM / GPS 底图）。
- 常见字段（精简示例，字段命名以实际文件为准）：
  - `user_id`：匿名化用户标识（仅用于同一用户聚合分析）
  - `company_id`：运营公司标识
  - `start_time_cn` / `end_time_cn`：北京时间字符串
  - `start_lng_wgs84` / `start_lat_wgs84`、`end_lng_wgs84` / `end_lat_wgs84`
  - `start_lng_raw` / `start_lat_raw`、`end_lng_raw` / `end_lat_raw`
  - （空间格式）GeoJSON 点几何表示行程起点（对应所在坐标系目录）

## 适用场景
- 高峰时段规律分析、出行强度统计
- OD（起终点）热点分布、聚类与格网聚合
- 骑行时长 / 时间分布特征挖掘
- 与天气 / 轨道 / 其它公共出行数据叠加（需外部数据源）
- 教学示例：GeoJSON 可直接拖入 kepler.gl / geojson.io / QGIS

## 为什么有两个目录？
| 目录 | 用途 | 特点 |
|------|------|------|
| `wgs84/` | 正式分析、地图叠加、跨数据集融合 | 坐标标准，对齐 OSM / GPS / 卫星底图 |
| `raw/`   | 快速浏览、教学演示 | 保留原始平台坐标，可能轻微偏移 |

## 格式选择建议
| 需求 | 推荐格式 | 说明 |
|------|----------|------|
| 表格浏览 / 快速筛选 | CSV (zip) | 兼容 Excel / WPS；体积较大已压缩 |
| 在线地图可视化 | GeoJSON (zip) | 直接拖入 kepler.gl / geojson.io |
| 大数据批处理 / 列存 | Parquet / GeoParquet | （如提供）高效压缩与向量化读取 |
| Python 空间分析 | GeoParquet / GeoJSON | GeoParquet 若提供优先 |

## 导入任意数据库 / 引擎示例
> 以下命令需根据你实际的文件名与路径替换；演示以单日解压后的 CSV（含 WGS84 坐标）为例。

### PostgreSQL / PostGIS
```sql
CREATE TABLE bike_trips (
  user_id text,
  company_id text,
  start_time_cn text,
  end_time_cn text,
  start_lng_wgs84 double precision,
  start_lat_wgs84 double precision,
  end_lng_wgs84 double precision,
  end_lat_wgs84 double precision
);
\copy bike_trips FROM 'bike_data_20210101_wgs84.csv' CSV HEADER ENCODING 'UTF8';
```
（如需空间列，可使用 `ST_SetSRID(ST_MakePoint(start_lng_wgs84,start_lat_wgs84),4326)` 衍生 Point 列）

### DuckDB（命令行 / Python）
```sql
CREATE TABLE bike_trips AS
SELECT * FROM read_csv_auto('bike_data_20210101_wgs84.csv');
```

### ClickHouse
```sql
CREATE TABLE bike_trips (
  user_id String,
  company_id String,
  start_time_cn String,
  end_time_cn String,
  start_lng_wgs84 Float64,
  start_lat_wgs84 Float64,
  end_lng_wgs84 Float64,
  end_lat_wgs84 Float64
) ENGINE = MergeTree ORDER BY (start_time_cn);

-- 导入 (替换为本地实际路径)
INSERT INTO bike_trips FORMAT CSVWithNames
< bike_data_20210101_wgs84.csv;
```

### SQLite（命令行）
```bash
sqlite3 bike.db <<'EOF'
.mode csv
.import bike_data_20210101_wgs84.csv bike_trips
EOF
```

### Pandas / GeoPandas（Python）
```python
import zipfile, pandas as pd
from pathlib import Path

zip_path = Path('data/share/wgs84/csv_zip/bike_data_20210101_wgs84.zip')
with zipfile.ZipFile(zip_path) as z:
    with z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f)
print(df.head())
```
（若需 GeoDataFrame：使用 `geopandas.points_from_xy(df.start_lng_wgs84, df.start_lat_wgs84, crs="EPSG:4326")`）

## 可视化快速路径
| 工具 | 步骤 | 适用人群 |
|------|------|----------|
| kepler.gl | 打开官网 → 拖入解压后的 `.geojson` | 新手 / 快速地图 |
| geojson.io | 打开网址 → 拖文件 | 超轻量预览 |
| QGIS | 添加矢量图层 → 选 GeoJSON | 进阶空间分析 |

（时间动画：在 kepler.gl 中以 `start_time_cn` 作为时间字段加 Filter 即可。）

## 坐标与精度提示
- `wgs84/` 目录：适合与其它标准数据叠加；经纬度字段或导出的 geometry 均为 EPSG:4326。
- `raw/` 目录：未标准化；仅用于快速演示；用于严谨分析需先转换。

## 性能与使用建议
| 目标 | 建议 |
|------|------|
| 大批量统计 | 先导入列式（DuckDB / ClickHouse / Parquet）再聚合 |
| 地图点渲染卡顿 | 采样（每 50~200 行取 1）或做网格聚合（Hex / Quadbin） |
| 追加更多日期 | 保持同一字段模式即可追加写入 |
| 空间分析 | 优先使用 WGS84 列；必要时建立空间索引（PostGIS GIST） |

## 合规与限制（务必阅读）
- 数据来源：**[深圳市政府数据开放平台](https://opendata.sz.gov.cn/)发布的**共享单车企业每日订单表**了，数据量包含 2.4 亿条数据。
- 使用范围：科研、教学、学习、公共政策分析等合规用途；严禁试图还原个人真实身份。
- 若你基于数据发布成果，请注明来源并遵守平台条款。
- 原始数据存在：少量日期缺失、异常行程（极短 / 坐标偏移）等情况属常见客观现象。

## 免责声明（交付侧）
| 项目 | 说明 |
|------|------|
| 日期覆盖 | 以随包日期列表 CSV 记载为准（请交付时确保文件完整） |
| 行数规模 | 若未明确标注“全量 2.4 亿”，则默认为子集或阶段性导出 |
| 坐标偏移 | raw 目录存在偏移属正常，不构成质量问题 |
| 数据真实度 | 基于公开平台输出，未额外做语义修补 |
| 售后 | 若链接失效，可在约定窗口内申请补发（需自定义填充） |

> 若计划售卖：请自行补充定价、发货方式（例如：购买后私信提供云盘链接）、售后策略及会员优惠说明。下面提供可填模板：

## 发货 
- 发货：购买后平台私信发送提取连接，提供阿里云盘（还在上传）、夸克网盘和百度网盘的链接。

## FAQ（可自行裁剪）
**Q：点与底图有偏移？**  
A：检查是否误用了 `raw/` 目录，建议换用 `wgs84/`。

**Q：文件太大打不开？**  
A：只解压需要的日文件；或在 CSV 里抽样（每隔 100 行取 1）。

**Q：如何做时间动画？**  
A：kepler.gl 添加时间过滤器，字段选 `start_time_cn`。

**Q：可以继续追加更多天吗？**  
A：保持相同字段与目录规范即可追加。

**Q：如何转空间格式？**  
A：用 GeoPandas 读取 CSV，构造 Point 列后另存为 GeoParquet / Shapefile。

## 增值服务

可以根据私信的联系方式，咨询任何数据集有关的问题。
> 为了集中讨论，欢迎在[Github Issue](https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook/issues?q=sort%3Aupdated-desc+is%3Aissue+is%3Aopen)上面提出问题。
>

**博客相关文章：**

- [深圳市共享单车数据分析【文末附共享单车数据集清单】](/blog/city-transportation/shenzhen-shared-bike-dataset-list)

- [使用Python获取某个时间段的深圳共享单车数据集完整教程【纯小白向】附常见问题、可导出为csv](/blog/city-transportation/深圳共享单车数据获取教程)

- [2.4 亿条深圳共享单车数据集获取完整教程【开发者版】](/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers)
