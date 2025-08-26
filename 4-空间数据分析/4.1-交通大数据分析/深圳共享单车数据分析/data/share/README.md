# 数据分享导出说明

目录结构：

```text
data/share/
  wgs84/
    geojson_zip/
      YYYY-MM-DD.geojson.zip
    csv_zip/
      YYYY-MM-DD.csv.zip
    parquet/
      YYYY-MM-DD.parquet
    geoparquet/
      YYYY-MM-DD.parquet
  raw/
    geojson_zip/
      YYYY-MM-DD.geojson.zip
    csv_zip/
      YYYY-MM-DD.csv.zip
    parquet/
      YYYY-MM-DD.parquet
    geoparquet/
      YYYY-MM-DD.parquet
```

格式选择建议（默认仅提供两种）：

- CSV（zip）：推荐给表格分析/简单查看的用户；体积较大，已压缩。
- GeoJSON（zip）：推荐给地图可视化/空间分析的用户；体积较大，已压缩；几何为对应目录的“起点”坐标。

字段说明（核心）：

- user_id：匿名化用户标识，仅用于同一用户维度的统计（如行程计数、活跃度等），不用于身份识别。
- company_id：运营公司。
- start_time_cn/end_time_cn：北京时间字符串。
- 起终点经纬度：根据目录不同输出为 raw 或 wgs84 两套列名（见下）。


时间与坐标：

- 时间统一输出为北京时间字符串列：start_time_cn/end_time_cn。
- 坐标列（两套目录分开保存、互不混合）：
  - wgs84 目录：start_lng_wgs84/start_lat_wgs84，end_lng_wgs84/end_lat_wgs84（GeoJSON/GeoParquet 几何即为起点）。
  - raw 目录：start_lng_raw/start_lat_raw，end_lng_raw/end_lat_raw（GeoJSON/GeoParquet 几何即为起点；CRS 未声明）。
- 如何导出（示例）：

```powershell
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 --sets wgs84 --formats csv,geojson --batch 50000 --out data/share

# 同时导出两套坐标
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 --sets raw,wgs84 --formats csv,geojson --batch 50000 --out data/share
```

注意事项：

- 超大日数据建议适当调小 --batch 以降低内存占用；脚本使用流式读取，默认 50k/批。
- 若历史库尚未填充 \*_wgs84，将回退使用旧列 \*_geom。
- GeoParquet 已内置，依赖 pyarrow；若需更丰富几何类型可后续接入 geoarrow。
