# 城市空间数据分析笔记 🏙️

**Urban-Spatial-Data-Analysis-Notebook**

[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Jupyter](https://img.shields.io/badge/Jupyter-Notebook-orange.svg)](https://jupyter.org/)

> 城市空间数据分析的系统性学习笔记与实战案例合集。从 Python 基础到空间回归、交通大数据、热岛效应、深度学习建筑识别——用数据读懂城市。
>
> 📖 配套博客：[renhai.online](https://www.renhai.online/) · 📊 项目展示：[renhai.online/projects](https://www.renhai.online/projects)

---

## 📖 简介

本仓库是我的城市空间数据分析学习笔记合集，涵盖：

- 🔍 **系统学习路径**：从 Python 基础到高级空间分析的完整路线
- 📊 **真实案例驱动**：共享单车、房价、热岛、绿地可达性等城市课题
- 🛠️ **工程化实践**：完整的数据获取 → 处理 → 分析 → 可视化流程
- 📝 **持续更新**：新项目和博客文章同步维护

---

## 🗺️ 分析项目一览

### 🚲 [深圳共享单车数据分析](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers)

- **规模**：2.4 亿条骑行记录，异步高并发采集
- **技术**：PostGIS 空间分析 + TimescaleDB 时序存储 + DBSCAN 聚类 + KDE 密度估计
- **产出**：OD 流量分析、骑行热点图、时间规律挖掘
- 🔗 [代码仓库](https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook/tree/master/4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析) · [博客文章](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers)

### 🌡️ 城市热岛效应分析

- **课题**：城市热岛效应的空间分布与驱动因素
- **技术**：遥感数据 + GIS 空间分析 + 地理加权回归
- 🔗 [项目详情](https://www.renhai.online/projects)

### 🏠 城市房价空间分析

- **课题**：房价空间异质性与驱动因子识别
- **技术**：OLS / GWR / MGWR 空间回归 + 可视化
- 🔗 [博客文章](https://www.renhai.online/blog/geospatial-data-analysis)

### 🌳 城市绿地可达性分析

- **课题**：公园绿地的空间可达性与服务覆盖评估
- **技术**：网络分析 + 两步移动搜索法（2SFCA）
- 🔗 [项目详情](https://www.renhai.online/projects)

### 🏗️ 空置办公改造住房 — 空间分析

- **课题**：后疫情时代空置办公建筑改造为住宅的可行性
- **技术**：空间数据可视化 + 政策分析
- 🔗 [博客文章](https://www.renhai.online/blog/geospatial-data-analysis/vacant-to-housing)

### 🌿 深圳绿视率分析

- **课题**：基于街景图片计算城市街道绿色视觉占比
- **技术**：百度街景 API + 图像语义分割 + 空间可视化

### 🦠 刚果（金）埃博拉疫情数据分析

- **课题**：2026 年本迪布焦型埃博拉疫情的数据叙事
- **技术**：GIS 空间分析 + 数据新闻 + 公共卫生可视化
- 🔗 [博客文章](https://www.renhai.online/blog)

### ⚽ 2026 世界杯数据冷知识

- **课题**：基于历史世界杯数据的深度分析
- **技术**：数据清洗 + 统计分析 + 可视化叙事
- 🔗 [博客文章](https://www.renhai.online/blog/sports-analytics/world-cup-cold-facts)

---

## 📁 Notebook 目录结构

### 🌟 [1. 导言](./1-introduction%20导言/)
- Python 语言介绍与城市空间分析的技术栈概览
- 最新技术发展趋势

### 🐍 [2. Python 入门](./2-Pthon入门/)
- Python 基础语法、面向对象编程
- 常用数据处理库（pandas、numpy、geopandas）

### 🗺️ [4. 空间数据分析](./4-空间数据分析/)

#### 🚗 [4.1 交通大数据分析](./4-空间数据分析/4.1-交通大数据分析/)
- **[深圳共享单车数据分析](./4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析/)** — 2.4 亿条数据的完整 ETL 流程
- 出租车 GPS 数据分析
- 地铁 IC 刷卡数据客流分析
- 共享单车轨道站点衔接需求（上海）
- 公交 GPS 数据运行分析
- TransBigData 交通时空大数据工具

#### 🖥️ [4.2 ArcGIS Python 系列](./4-空间数据分析/4.2-ArcGIS%20Python系列/)
- ArcPy 脚本开发、地理数据自动化处理、制图模块

#### 🏘️ [其他案例](./4-空间数据分析/其他案例/)
- 上海路网聚合分析、旅行规划、城市空间综合分析

### 🤖 [5. 机器学习](./5-机器学习/)
- CNN 图像分类、空间数据预测模型

---

## 🛠️ 技术栈

| 类别 | 工具 |
|------|------|
| **语言** | Python 3.10+ |
| **环境** | Jupyter Notebook / JupyterLab |
| **空间数据库** | PostgreSQL + PostGIS、TimescaleDB |
| **数据处理** | pandas、numpy、geopandas |
| **空间分析** | shapely、pyproj、fiona、TransBigData |
| **可视化** | matplotlib、folium、plotly、keplergl |
| **异步采集** | aiohttp、asyncio |
| **数据库驱动** | psycopg3、sqlalchemy |
| **深度学习** | PyTorch、torchvision |

---

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook.git
cd Urban-Spatial-Data-Analysis-Notebook

# 安装基础依赖
pip install jupyter pandas geopandas matplotlib folium

# 启动 Jupyter
jupyter notebook
```

---

## 📚 学习路径

### 初学者
1. **[导言](./1-introduction%20导言/)** — 了解 Python 在城市分析中的定位
2. **[Python 入门](./2-Pthon入门/)** — 掌握基础语法和数据处理
3. **[其他案例](./4-空间数据分析/其他案例/)** — 动手做简单分析

### 进阶
1. **[交通大数据](./4-空间数据分析/4.1-交通大数据分析/)** — 完整的数据工程实践
2. **[深圳共享单车](./4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析/)** — 亿级数据处理经验
3. **[机器学习](./5-机器学习/)** — 空间数据的 ML 应用

### 探索更多
- 访问 [renhai.online/blog](https://www.renhai.online/blog) 获取配套文章和深度解读
- 浏览 [renhai.online/projects](https://www.renhai.online/projects) 查看完整项目列表

---

## 📰 相关博客文章

| 文章 | 主题 |
|------|------|
| [2.4 亿条深圳共享单车数据集获取教程](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers) | 数据采集、异步并发 |
| [共享单车数据坐标系排查实录](https://www.renhai.online/blog/city-transportation/bike-sharing-geo-coordinates-validation) | 坐标系、数据质量 |
| [花半天规划的旅行路线，为什么还不如 Python 跑 10 秒的结果？](https://www.renhai.online/blog/geospatial-data-analysis/traveling-salesperson-problem-algorithm-vs-human-intuition) | 路径优化算法 |
| [空置办公改造住房可行性分析](https://www.renhai.online/blog/geospatial-data-analysis/vacant-to-housing) | 空间分析、政策 |
| [世界杯历史数据冷知识合集](https://www.renhai.online/blog/sports-analytics/world-cup-cold-facts) | 体育数据可视化 |
| [FastAPI 协程指南](https://www.renhai.online/blog/notes/fastapi-async-def-vs-def-guide) | Python 异步编程 |
| [Django + Vue 地图实践分享](https://www.renhai.online/blog/notes/automated-interest-point-map-platform-geofence-notification) | Web GIS 开发 |

---

## 🤝 贡献

欢迎通过以下方式参与：

- 🐛 [提交 Issue](https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook/issues) 报告问题
- 📝 完善文档和注释
- 💡 分享新的分析案例

---

## 📄 许可证

本项目采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可证。

---

## 📞 联系

- 💻 博客：[renhai.online](https://www.renhai.online/)
- 🐙 GitHub：[@renhai-lab](https://github.com/renhai-lab)
- 📧 [通过 GitHub Issues 联系](https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook/issues)
