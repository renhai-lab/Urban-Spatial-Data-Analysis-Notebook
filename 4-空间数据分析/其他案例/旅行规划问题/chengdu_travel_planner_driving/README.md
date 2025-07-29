# 成都一日游智能规划系统使用指南

❗❗❗ 本系列还在测试

## 快速开始

### 1. 环境配置

1. **获取高德地图API密钥**
   - 访问 [高德开放平台](https://lbs.amap.com/)
   - 注册账号并创建应用
   - 获取Web服务API Key

2. **配置API密钥**
   ```bash
   # 第一次运行时，程序会自动复制 .env.example 到 .env
   # 编辑 .env 文件，填入您的API密钥
   AMAP_API_KEY=your_actual_api_key_here
   ```

### 2. 安装依赖

```bash
pip install requests folium eviltransform python-dotenv pathlib
```

### 3. 运行方式

#### 方式一：交互式设置（推荐）
```bash
python interactive_travel_setup.py
```
- 程序会引导您输入景点名称
- 自动获取坐标并生成预览地图
- 运行路线规划算法并生成最终地图

#### 方式二：直接运行主程序
```bash
# 基本运行
python travel_planner_driving.py

# 生成GeoJSON文件
python travel_planner_driving.py --generate-geojson

# 指定坐标系
python travel_planner_driving.py --generate-geojson --coordinate-system wgs84
python travel_planner_driving.py --generate-geojson --coordinate-system gcj02
python travel_planner_driving.py --generate-geojson --coordinate-system both
```

## 项目结构

```
chengdu_travel_planner_driving/
├── travel_planner_driving.py          # 主程序
├── interactive_travel_setup.py        # 交互式设置
├── plot_locations.py                  # 地图绘制
├── cache/                             # 缓存目录（自动创建）
│   ├── chengdu_locations.json         # 景点位置数据
│   ├── chengdu_travel_time_cache_*.json    # 时间缓存
│   └── chengdu_travel_path_cache_*.json    # 路径缓存
├── data/                              # 输出目录（自动创建）
│   ├── *.geojson                      # GeoJSON数据文件
│   └── route_map_*.html               # 路线地图文件
└── .env                               # 环境变量配置（从.env.example复制）
```

## 坐标系说明

### GCJ02坐标系（高德地图）
- 中国国家测绘局坐标系，又称"火星坐标系"
- 高德地图、腾讯地图等国内地图服务使用
- 原始API返回的坐标格式

### WGS84坐标系（国际标准）
- 国际通用坐标系，GPS原始坐标
- 适用于国际地图服务和前端应用
- 可通过 `eviltransform.gcj2wgs()` 转换

## 常见问题

### API密钥相关
- **问题**: `在 .env 文件中未找到或未设置 AMAP_API_KEY`
- **解决**: 检查 `.env` 文件是否存在且格式正确

### 坐标获取失败
- **问题**: `获取 XXX 坐标失败`
- **解决**: 
  1. 检查地点名称是否准确
  2. 确认API密钥是否有效
  3. 检查网络连接是否正常

### 路径规划失败
- **问题**: 无法获取路线信息
- **解决**:
  1. 确认起终点距离合理
  2. 检查API配额是否充足
  3. 使用Haversine公式备用方案

