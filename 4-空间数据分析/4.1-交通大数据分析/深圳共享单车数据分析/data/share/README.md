# 数据分享导出说明

本目录包含通过优化数据管道导出的## 坐标系说明

### WGS84 目录（推荐）
- **用途**：正式分析、地图叠加、与其他数据集结合
- **特点**：标准坐标系，与 GPS、卫星图像、OpenStreetMap 等完全兼容
- **精度**：点位与地图底图精确对齐

### RAW 目录
- **用途**：快速浏览、教学演示、保留原始数据
- **特点**：保留平台原始坐标（通常为 BD09LL 或 GCJ-02）
- **注意**：与标准地图可能有轻微偏移（几十到几百米）

## 格式选择建议

- **CSV（zip）**：推荐给表格分析/简单查看的用户；体积较大，已压缩
- **GeoJSON（zip）**：推荐给地图可视化/空间分析的用户；体积较大，已压缩；几何为对应目录的"起点"坐标
- **Parquet**：推荐大数据分析；无压缩但体积小，读取快
- **GeoParquet**：推荐地理大数据分析；包含原生空间几何类型单车数据，支持双坐标系和多种格式。

## 目录结构

```text
data/share/
  wgs84/                          # WGS84 标准坐标系（推荐用于分析）
    geojson_zip/
      YYYY-MM-DD.geojson.zip      # 地理空间数据，适合地图可视化
    csv_zip/
      YYYY-MM-DD.csv.zip          # 表格数据，适合统计分析
    parquet/
      YYYY-MM-DD.parquet          # 列式存储，适合大数据分析
    geoparquet/
      YYYY-MM-DD.parquet          # 空间列式存储，适合地理大数据
  raw/                            # 原始坐标系（BD09LL/GCJ-02）
    geojson_zip/
      YYYY-MM-DD.geojson.zip      # 原始坐标地理数据，快速浏览用
    csv_zip/
      YYYY-MM-DD.csv.zip          # 原始坐标表格数据
    parquet/
      YYYY-MM-DD.parquet          # 原始坐标列式存储
    geoparquet/
      YYYY-MM-DD.parquet          # 原始坐标空间列式存储
```

格式选择建议（默认仅提供两种）：

- CSV（zip）：推荐给表格分析/简单查看的用户；体积较大，已压缩。
- GeoJSON（zip）：推荐给地图可视化/空间分析的用户；体积较大，已压缩；几何为对应目录的“起点”坐标。

## 字段说明

### 核心字段（所有格式通用）

- **user_id**：匿名化用户标识，仅用于同一用户维度的统计（如行程计数、活跃度等），不用于身份识别
- **company_id**：运营公司
- **start_time_cn/end_time_cn**：北京时间字符串

### 坐标字段（根据目录不同）

#### WGS84 目录
- **start_lng_wgs84/start_lat_wgs84**：起点经纬度（WGS84坐标系）
- **end_lng_wgs84/end_lat_wgs84**：终点经纬度（WGS84坐标系）
- **GeoJSON/GeoParquet 几何**：起点坐标的空间几何

#### RAW 目录  
- **start_lng_raw/start_lat_raw**：起点经纬度（原始坐标系）
- **end_lng_raw/end_lat_raw**：终点经纬度（原始坐标系）
- **GeoJSON/GeoParquet 几何**：起点坐标的空间几何（原始坐标系）

## 数据来源与处理

- **来源**：深圳市政府数据开放平台
- **时间范围**：2021年1月1日 - 2021年8月30日（约2.44亿条记录）
- **处理流程**：
  1. 实时采集原始数据
  2. 同步完成坐标系转换（BD09LL/GCJ-02 → WGS84）
  3. TimescaleDB 分区存储
  4. 按需导出双坐标系数据
## 如何导出数据

```bash
# 导出 WGS84 坐标数据
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets wgs84 --formats csv,geojson --batch 50000 --out data/share

# 导出原始坐标数据  
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets raw --formats csv,geojson --batch 50000 --out data/share

# 同时导出两套坐标系
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets raw,wgs84 --formats csv,geojson --batch 50000 --out data/share

# 导出所有格式（包括 Parquet）
uv run python -m scr.data_pipline.export_share --start 20210101 --end 20210102 \
  --coord-sets wgs84 --formats csv,geojson,parquet,geoparquet --batch 50000 --out data/share
```

## 使用建议

1. **新用户**：建议从 wgs84/csv_zip/ 开始，用 Excel 或类似工具查看
2. **地图可视化**：使用 wgs84/geojson_zip/，配合 kepler.gl 或 QGIS
3. **大数据分析**：使用 parquet 或 geoparquet 格式，配合 pandas/dask
4. **快速浏览**：可以使用 raw 目录，但注意坐标系偏移

## 注意事项

- 超大日数据建议适当调小 --batch 以降低内存占用；脚本使用流式读取，默认 50k/批
- WGS84 坐标适合与其他地理数据集进行空间分析和叠加
- 原始坐标保留了数据的原始特征，适合特定场景的研究
