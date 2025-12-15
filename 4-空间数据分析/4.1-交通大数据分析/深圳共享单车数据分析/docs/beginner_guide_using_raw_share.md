# 小白入门：拿到 data/share 数据后怎么用？

这篇指南教你"不开发也能用数据"。前提是你已经从别人那里拿到了本仓库导出的 data/share 目录（或压缩包）。

你将学到：

- 如何快速查看和筛选 CSV/GeoJSON 文件
- 如何把数据放到免费可视化工具中做地图
- raw 和 wgs84 两套坐标的区别和使用场景

## 常见问题（FAQ）

- **为什么我看到的点和底图不完全重合？**

  - 这是坐标系问题。如果使用 raw 目录，可能有偏移；建议换用 wgs84 目录的数据，会与底图精确对齐。

- **raw 和 wgs84 两个目录有什么区别？**

  - raw：原始坐标，可能是 BD09LL 或 GCJ-02 坐标系，适合快速浏览
  - wgs84：标准 WGS84 坐标系，与 GPS、卫星图像兼容，适合正式分析

- **文件太大打开很慢怎么办？**

  - 先用 zip 里的 CSV 按需解压，或者只取 GeoJSON 的一部分做演示；做地图时可以抽样（比如每隔 100 行取一行）。

- **我只想拿某个时间段的数据？**

  - 先在 CSV 里用表格筛选 start_time_cn 的小时范围，然后另存为一个小文件即可。

- **数据质量如何保证？**

  - 数据来源于深圳市政府开放平台，经过实时坐标转换和质量检查
  - wgs84 目录的数据已经过坐标系标准化处理，推荐用于正式分析选链接清单

## 目录里有什么？

data/share/ 下通常有这些子目录：

```
data/share/
  wgs84/                    # WGS84坐标系（推荐用于分析）
    csv_zip/                # 每天一个 zip，里面是 CSV 表格
    geojson_zip/            # 每天一个 zip，里面是 GeoJSON（可以直接做地图）
    parquet/、geoparquet/   # 大数据分析专用（先跳过也没关系）
  raw/                      # 原始坐标系（快速浏览用）
    csv_zip/                # 同上
    geojson_zip/            # 同上
    parquet/、geoparquet/   # 同上
```

## 坐标系选择指南

- **wgs84 目录**：推荐用于正式分析、地图叠加、与其他数据集结合
  - 坐标系标准，与 GPS、卫星图像、OpenStreetMap 等兼容
  - 字段名：start_lng_wgs84/start_lat_wgs84，end_lng_wgs84/end_lat_wgs84

- **raw 目录**：适合快速浏览、教学演示
  - 保留原始坐标，可能与地图底图有轻微偏移
  - 字段名：start_lng_raw/start_lat_raw，end_lng_raw/end_lat_rawre\\raw 后怎么用？

这篇指南教你“不开发也能用数据”。前提是你已经从别人那里拿到了本仓库导出的 data/share/raw 目录（或压缩包）。

你将学到：

- 如何快速查看和筛选 CSV/GeoJSON 文件
- 如何把数据放到免费可视化工具中做地图
- 下一步该学什么：给你一份精选链接清单

## 目录里有什么？

data/share/raw/ 下通常有这些子目录：

- csv_zip/：每天一个 zip，里面是 CSV 表格（体积小，通用）
- geojson_zip/：每天一个 zip，里面是 GeoJSON（可以直接做地图）

注意：raw 目录保存的是“原始坐标”，没有声明坐标系。适合快速浏览与教学；若用于分析或与其他地图叠加，建议改用 wgs84 目录的数据。

## 方式一：只想看看——直接用 Excel/表格

1. **选择坐标系**：建议从 wgs84/csv_zip/ 开始（更标准）
2. 找到某个日期（例如 bike_data_20210101_wgs84.zip），解压缩得到 CSV。
3. 用 Excel、WPS 或 Numbers 打开。
4. 常见字段：

**基础信息**：
- start_time_cn / end_time_cn：北京时间字符串
- user_id：匿名化的用户标识（仅用于同一用户内的统计，如行程计数；不用于身份识别）
- company_id：运营公司

**坐标信息**（根据目录不同）：
- wgs84 目录：start_lng_wgs84/start_lat_wgs84，end_lng_wgs84/end_lat_wgs84
- raw 目录：start_lng_raw/start_lat_raw，end_lng_raw/end_lat_raw

5. 你可以用筛选功能看看某天、某公司、或某个时间段的数据量。

不过公司字段不是很准

小提示：CSV 行数可能很多，Excel 会变卡。只做浏览的话，过滤后保存一小份就行。

## 方式二：想看地图——用免费 Web 工具

准备 GeoJSON 文件：

- **推荐**：在 wgs84/geojson_zip/ 里选一个日期，解压得到 .geojson（标准坐标系）
- **或者**：在 raw/geojson_zip/ 里选择（快速浏览用，可能有轻微偏移）

三个简单路线：

- **kepler.gl（强烈推荐，新手友好）**

  1. 打开 [https://kepler.gl/demo](https://kepler.gl/demo)
  2. 拖拽 .geojson 文件到页面
  3. 点开图层设置（Layer），选择 Point
  4. 可以调颜色、大小，按时间刷（Filter 里选择 start_time_cn）
  5. 支持多图层叠加，可以同时查看起点和终点

- **geojson.io（极简）**

  1. 打开 [https://geojson.io](https://geojson.io)
  2. 拖拽 .geojson 到页面
  3. 左侧会显示地图点位，右侧可以看属性

- **QGIS (专业 GIS 软件，免费)**
  1. 下载：[https://qgis.org/download/](https://qgis.org/download/)
  2. 安装后可以加载 GeoJSON，做更复杂的空间分析

**坐标系说明**：
- 如果使用 wgs84 目录的数据，点位会与底图精确对齐
- 如果使用 raw 目录的数据，可能会有轻微偏移（这是正常的）

## 方式三：想做一点数据分析（入门版）

如果你愿意安装 Python（推荐新版 3.13）并用终端执行命令，可以这样：

1. 安装依赖管理器 uv：

- 访问 [https://docs.astral.sh/uv/getting-started/](https://docs.astral.sh/uv/getting-started/) 按步骤安装


2. 可视化[最简单的散点图](notebooks\可视化（最简单的散点图）.ipynb) ：

```python
# 读取并构造 GeoDataFrame（放在一个单元格）
import zipfile
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely import wkt
from pathlib import Path

zip_path = Path('../data/share/wgs84/csv_zip/bike_data_20210101_wgs84.zip')

with zipfile.ZipFile(zip_path) as z:
    with z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f)

# 检查列名并构造经纬度列（容错）
if 'start_lng_wgs84' not in df.columns or 'start_lat_wgs84' not in df.columns:
    if 'start_geom_wgs84' in df.columns:
        pts = df['start_geom_wgs84'].map(lambda s: wkt.loads(s) if pd.notna(s) else None)
        df['start_lng_wgs84'] = pts.map(lambda p: p.x if p else None)
        df['start_lat_wgs84'] = pts.map(lambda p: p.y if p else None)

if 'end_lng_wgs84' not in df.columns or 'end_lat_wgs84' not in df.columns:
    if 'end_geom_wgs84' in df.columns:
        pts = df['end_geom_wgs84'].map(lambda s: wkt.loads(s) if pd.notna(s) else None)
        df['end_lng_wgs84'] = pts.map(lambda p: p.x if p else None)
        df['end_lat_wgs84'] = pts.map(lambda p: p.y if p else None)

# 构造起点/终点 GeoDataFrame（只包含有坐标的行）
start_df = df.dropna(subset=['start_lng_wgs84', 'start_lat_wgs84']).copy()
end_df = df.dropna(subset=['end_lng_wgs84', 'end_lat_wgs84']).copy()

gdf_start = gpd.GeoDataFrame(
    start_df,
    geometry=gpd.points_from_xy(start_df['start_lng_wgs84'], start_df['start_lat_wgs84']),
    crs="EPSG:4326"
)
gdf_end = gpd.GeoDataFrame(
    end_df,
    geometry=gpd.points_from_xy(end_df['end_lng_wgs84'], end_df['end_lat_wgs84']),
    crs="EPSG:4326"
)

# 合并用于统一绘图（添加类型标签）
gdf_start['point_type'] = 'start'
gdf_end['point_type'] = 'end'
gdf = gpd.GeoDataFrame(pd.concat([gdf_start, gdf_end], ignore_index=True), crs="EPSG:4326")
```


## 我应该学哪些下一步？（精选清单）

- 可视化与地图

  - kepler.gl 快速入门：[https://docs.kepler.gl/docs/user-guides/get-started/get-started](https://docs.kepler.gl/docs/user-guides/get-started/get-started)
  - QGIS（桌面 GIS）下载与基础：[https://qgis.org](https://qgis.org)
  - geojson.io 简介：[https://geojson.io](https://geojson.io)
- 数据分析（零基础）

  - Python 与 Pandas 入门（官方教程集合）：[https://pandas.pydata.org/docs/getting_started/index.html](https://pandas.pydata.org/docs/getting_started/index.html)
  - 可视化：Matplotlib 入门：[https://matplotlib.org/stable/tutorials/introductory/pyplot.html](https://matplotlib.org/stable/tutorials/introductory/pyplot.html)
- 进阶（等本仓库后续补充数据分析代码）

  - GeoPandas（在 Python 里做空间分析）：[https://geopandas.org](https://geopandas.org)
  - PostGIS（在数据库里做空间查询）：[https://postgis.net/documentation/](https://postgis.net/documentation/)

## 常见问题（FAQ）

- 为什么我看到的点和底图不完全重合？

  - 可能是坐标系问题。raw 目录的坐标是“原始坐标”，建议换用我转换后的 wgs84 目录的数据。
- 文件太大打开很慢怎么办？

  - 先用 zip 里的 CSV 按需解压，或者只取 GeoJSON 的一部分做演示；做地图时可以抽样（比如每隔 100 行取一行）。
- 我只想拿某个时间段的数据？

  - 先在 CSV 里用表格筛选 start_time_cn 的小时范围，然后另存为一个小文件即可。

祝你玩得开心。有任何反馈与想看的教程主题，可以在仓库提 issue。
