# 城市空间数据分析笔记 🏙️

**Urban-Spatial-Data-Analysis-Notebook**

[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Jupyter](https://img.shields.io/badge/Jupyter-Notebook-orange.svg)](https://jupyter.org/)

> **本笔记持续更新中...**

## 📖 简介

本仓库是个人城市空间数据分析的学习笔记合集，整理成系统性专栏，旨在：

- 🔍 **系统学习**：从 Python 基础到高级空间数据分析的完整学习路径
- 📊 **实践驱动**：通过真实案例掌握城市数据分析方法和工具
- 🛠️ **工程实践**：包含完整的数据获取、处理、分析和可视化流程
- 📝 **知识沉淀**：方便自己查漏补缺，也希望能帮助其他学习者

本仓库也是 [我的博客](https://www.renhai.online/) 中城市空间数据分析相关文章的代码仓库。如果你对相关内容感兴趣，欢迎访问博客获取更详细的说明和背景知识。

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
- 空间数据机器学习应用
- 预测模型构建
- 模式识别与分类

## 🛠️ 技术栈

### 核心工具
- **Python 3.8+** - 主要编程语言
- **Jupyter Notebook** - 交互式分析环境
- **PostgreSQL + PostGIS** - 空间数据库
- **TimescaleDB** - 时序数据处理

### 主要 Python 库
- **数据处理**: pandas, numpy, geopandas
- **空间分析**: shapely, pyproj, fiona
- **可视化**: matplotlib, folium, plotly
- **异步处理**: aiohttp, asyncio
- **数据库**: psycopg3, sqlalchemy

## 🚀 快速开始

### 环境要求
- Python 3.8 或更高版本
- PostgreSQL 数据库（可选，用于大规模数据处理）
- Jupyter Notebook 或 JupyterLab

### 安装依赖
```bash
# 克隆仓库
git clone https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook.git
cd Urban-Spatial-Data-Analysis-Notebook

# 安装基础依赖
pip install jupyter pandas geopandas matplotlib folium

# 安装特定项目依赖（以深圳共享单车项目为例）
cd "4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析"
pip install -r requirements.txt  # 如果存在
```

### 运行示例
```bash
# 启动 Jupyter Notebook
jupyter notebook

# 或启动 JupyterLab
jupyter lab
```

## 📚 学习路径建议

### 初学者
1. 从 **[1. 导言](./1-introduction%20导言/)** 开始了解 Python 在城市分析中的应用
2. 学习 **[2. Python 入门](./2-Pthon入门/)** 掌握基础语法
3. 尝试 **[其他案例](./4-空间数据分析/其他案例/)** 中的简单分析项目

### 进阶学习者
1. 深入 **[4.1 交通大数据分析](./4-空间数据分析/4.1-交通大数据分析/)** 的专题项目
2. 学习 **[深圳共享单车数据分析](./4-空间数据分析/4.1-交通大数据分析/深圳共享单车数据分析/)** 的完整工程实践
3. 探索 **[5. 机器学习](./5-机器学习/)** 在空间数据中的应用

## 🤝 贡献指南

欢迎贡献！你可以通过以下方式参与：

- 🐛 报告问题或提出改进建议
- 📝 完善文档和注释
- 💡 分享新的分析案例
- 🔧 优化代码实现

请查看各子项目的 README 文件获取具体的贡献指南。

## 📄 许可证

本项目采用 [Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/) 许可证。

这意味着你可以：
- ✅ 自由分享和改编内容
- ✅ 用于商业目的
- ✅ 基于此创建衍生作品

前提是：
- 📝 标明原作者和来源
- 🔄 以相同许可证分享衍生作品

## 📞 联系方式

- 💻 **博客**: [renhai.online](https://www.renhai.online/)
- 📧 **邮箱**: [通过 GitHub Issues 联系](https://github.com/renhai-lab/Urban-Spatial-Data-Analysis-Notebook/issues)
- 🐙 **GitHub**: [@renhai-lab](https://github.com/renhai-lab)

## 🙏 致谢

感谢所有为开源地理空间数据分析工具做出贡献的开发者和研究者，特别是：
- GDAL/OGR 开发团队
- PostGIS 和 PostgreSQL 社区
- Python 地理空间数据分析生态系统的维护者们

---

**如果这个项目对你有帮助，请考虑给它一个 ⭐️！**
