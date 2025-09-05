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


## 发货 
- 发货：购买后平台私信发送提取连接，提供阿里云盘、夸克网盘和百度网盘的链接。

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

- [深圳市共享单车数据分析【文末附共享单车数据集清单】](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-dataset-list)

- [使用Python获取某个时间段的深圳共享单车数据集完整教程【纯小白向】附常见问题、可导出为csv](https://www.renhai.online/blog/city-transportation/深圳共享单车数据获取教程)

- [2.4 亿条深圳共享单车数据集获取完整教程【开发者版】](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers)
