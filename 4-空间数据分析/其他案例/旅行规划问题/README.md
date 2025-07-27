# 旅行商问题系列

# 环境

```bash
uv add eviltransform requests folium
```

# 内容

[1 成都一日游旅行规划](chengdu_travel_planner_driving)：文章：[我让算法帮我规划了一次成都一日游，结果它比我的直觉快了7分钟——旅行商问题系列（“最近邻算法”和“遗传算法”）](https://www.renhai.online/blog/geospatial-data-analysis/traveling-salesperson-problem-algorithm-vs-human-intuition)

复制 `4-空间数据分析\其他案例\旅行规划问题\config.ini.example` 为 `config.ini` 之后填写百度地图key之后执行：

```bash
uv run chengdu_travel_planner_driving/01travel_planner_driving.py
```
