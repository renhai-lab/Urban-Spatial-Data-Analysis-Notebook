# 城市空间数据分析笔记 🏙️

**Urban-Spatial-Data-Analysis-Notebook**

[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Jupyter](https://img.shields.io/badge/Jupyter-Notebook-orange.svg)](https://jupyter.org/)

> 城市空间数据分析的系统性学习笔记，从 Python 基础到空间数据分析、交通大数据、ArcGIS 自动化、机器学习应用。
>
> 📖 配套博客：[renhai.online](https://www.renhai.online/) · 📊 更多项目：[renhai.online/projects](https://www.renhai.online/projects)

---

## 📖 简介

本仓库是个人城市空间数据分析的学习笔记合集，整理成系统性专栏：

- 🔍 **系统学习**：从 Python 基础到高级空间数据分析的完整学习路径
- 📊 **实践驱动**：通过真实案例掌握城市数据分析方法和工具
- 🛠️ **工程实践**：包含完整的数据获取、处理、分析和可视化流程
- 📝 **持续更新**：配套博客 [renhai.online](https://www.renhai.online/) 提供更详细的说明和背景知识

---

## 📁 内容结构

### 🌟 [1. 导言 (Introduction)](./1-introduction%20导言/)
- Python 语言介绍与特点
- 城市空间分析的 Python 技术栈介绍
- 最新技术发展趋势

### 🐍 [2. Python 入门](./2-Pthon入门/)
- Python 基础语法和核心概念
- 面向对象编程实践
- 常用数据处理库介绍

### 🗺️ [4. 空间数据分析](./4-空间数据分析/)

#### 🚗 [4.1 交通大数据分析](./4-空间数据分析/4.1-交通大数据分析/)
- **[深圳共享单车数据分析](./4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析/)**
  - 2.4 亿条共享单车数据获取与 PostGIS 分析流水线
  - 异步高并发数据获取系统
  - TimescaleDB 时序数据库优化
  - 完整的 ETL 数据处理流程

- **专题系列**：
  - 出租车 GPS 数据分析
  - 地铁 IC 刷卡数据城市轨道交通客流分析
  - 共享单车轨道站点衔接需求分析（上海案例）
  - 公交 GPS 数据城市公交运行状况分析
  - TransBigData 交通时空大数据处理工具

#### 🖥️ [4.2 ArcGIS Python 系列](./4-空间数据分析/4.2-ArcGIS%20Python系列/)
- ArcPy 脚本开发实践
- 地理数据处理自动化
- 制图模块应用

#### 🏘️ [其他案例](./4-空间数据分析/其他案例/)
- 上海路网聚合分析
- 旅行规划问题求解
- 城市空间分析综合案例

### 🤖 [5. 机器学习](./5-机器学习/)
- CNN 图像分类
- 空间数据机器学习应用
- 预测模型构建

---

## 🛠️ 技术栈

| 类别 | 工具 |
|------|------|
| **语言** | Python 3.8+ |
| **环境** | Jupyter Notebook / JupyterLab |
| **空间数据库** | PostgreSQL + PostGIS、TimescaleDB |
| **数据处理** | pandas、numpy、geopandas |
| **空间分析** | shapely、pyproj、fiona、TransBigData |
| **可视化** | matplotlib、folium、plotly |
| **异步采集** | aiohttp、asyncio |
| **数据库驱动** | psycopg3、sqlalchemy |

---

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook.git
cd Urban-Spatial-Data-Analysis-Notebook

# 安装基础依赖
pip install jupyter pandas geopandas matplotlib folium

# 启动 Jupyter Notebook
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
- 浏览 [renhai.online/projects](https://www.renhai.online/projects) 查看更多分析项目

---

## 📰 相关博客文章

以下是本仓库内容对应的博客文章，提供更详细的背景和解读：

| 文章 | 关联内容 |
|------|----------|
| [2.4 亿条深圳共享单车数据集获取教程](https://www.renhai.online/blog/city-transportation/shenzhen-shared-bike-data-acquisition-tutorial-multithreaded-concurrent-version-for-developers) | 4.1 交通大数据 |
| [共享单车数据坐标系排查实录](https://www.renhai.online/blog/city-transportation/bike-sharing-geo-coordinates-validation) | 4.1 交通大数据 |
| [花半天规划的旅行路线，为什么还不如 Python 跑 10 秒的结果？](https://www.renhai.online/blog/geospatial-data-analysis/traveling-salesperson-problem-algorithm-vs-human-intuition) | 其他案例 |
| [FastAPI 协程指南](https://www.renhai.online/blog/notes/fastapi-async-def-vs-def-guide) | Python 进阶 |
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
