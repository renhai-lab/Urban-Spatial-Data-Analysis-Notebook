### 旅行商问题 (Traveling Salesperson Problem) 系列

本系列通过实际案例，探讨如何使用Python解决经典的旅行商问题。

---

### **项目一：成都一日游路线规划**

本项目以成都的8个热门地点为例，探索如何规划出最优的驾车游览顺序。

*   **对应文章**：[《花半天规划的旅行路线，为什么还不如Python跑10秒的结果？》](https://www.renhai.online/blog/geospatial-data-analysis/traveling-salesperson-problem-algorithm-vs-human-intuition)
*   **代码目录**：`4-空间数据分析/其他案例/旅行规划问题/`

### **如何运行**

#### **1. 环境准备**

首先，请确保您已安装 `uv`。然后进入项目主目录并安装所需依赖。

```bash
# 进入该案例的根目录
cd 4-空间数据分析/其他案例/旅行规划问题

# 使用 uv 安装依赖
# - eviltransform: 用于处理不同地图服务商（如WGS84, GCJ-02, BD-09）间的坐标转换
# - requests: 用于调用高德地图API
# - folium: 用于在地图上可视化路线
uv add eviltransform requests folium
```

#### **2. 运行脚本**

> **💡 重要提示：关于数据缓存与API Key**
> 
> 为了保证结果的可复现性，并避免因实时路况变化影响结论，本项目将首次通过高德地图API获取的景点间驾车时间矩阵，缓存到了 `cache/chengdu_travel_time_cache_driving.json` 等文件中。
>
> *   **直接运行**：默认情况下，脚本会优先使用此缓存文件，无需配置API Key即可复现文章中的结果。
> *   **获取最新数据**：如果您想使用实时的路况数据重新计算，请按以下步骤操作：
>     1.  在 `.env` 文件中填写您自己的高德地图应用Key (AK)。
>     2.  (可选) 删除 `cache/chengdu_travel_time_cache_driving.json` 和 `cache/chengdu_travel_path_cache_driving.json` 文件，以确保程序重新请求API。

准备就绪后，运行主脚本：

```bash
uv run chengdu_travel_planner_driving/travel_planner_driving.py```

#### **3. 查看结果**

脚本运行成功后，将在 `chengdu_travel_planner_driving` 目录下生成以下三个HTML文件。您可以直接在浏览器中打开它们，查看不同算法规划出的路线：

*   `route_map_nn.html`: **最近邻算法 (Nearest Neighbor)** - 一种简单的贪心策略。
*   `route_map_ga.html`: **遗传算法 (Genetic Algorithm)** - 一种模拟生物进化的全局优化算法。
*   `route_map_aco.html`: **蚁群算法 (Ant Colony Optimization)** - 模拟蚂蚁寻找食物路径的启发式算法。

### **4.手动规划**

支持手动规划路线，用于测试。

```bash
# 显示待规划的几个点
uv run chengdu_travel_planner_driving/plot_locations.py```

查看all_locations_map.html

```bash
uv run chengdu_travel_planner_driving/manual_route_time.py```

控制台查看时间，manual_route_map.html查看地图
