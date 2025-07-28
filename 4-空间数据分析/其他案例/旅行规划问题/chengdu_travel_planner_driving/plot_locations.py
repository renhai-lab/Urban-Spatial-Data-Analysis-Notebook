import json
import eviltransform
import sys

import folium

# 读取景点坐标
with open("chengdu_travel_planner_driving/cache/chengdu_locations.json", "r", encoding="utf-8") as f:
    locations = json.load(f)

# 先转换所有点为WGS84坐标，保持顺序
coords_wgs = []
names = []
for name, value in locations.items():
    lon, lat = value
    wgs_lat, wgs_lon = eviltransform.bd2wgs(lat, lon)
    coords_wgs.append((wgs_lat, wgs_lon))
    names.append(name)

print(f"正在绘制所有景点分布地图: {len(coords_wgs)}个景点:{locations}")

# 以第一个点为中心
m = folium.Map(location=coords_wgs[0], zoom_start=12)

# 添加所有景点标记
for idx, (name, (wgs_lat, wgs_lon)) in enumerate(zip(names, coords_wgs)):
    marker = folium.Marker(
        location=(wgs_lat, wgs_lon),
        popup=f"<b>{idx+1}. {name}</b>",
        icon=folium.Icon(color="blue", icon="info-sign"),
    )
    folium.Tooltip(
        f"{idx+1}. {name}",
        permanent=True,
        direction="right",
        offset=(10, 0),
        style="color: navy; font-weight: bold;",
    ).add_to(marker)
    marker.add_to(m)

m.save("all_locations_map.html")
print("已生成所有景点分布地图: all_locations_map.html")
