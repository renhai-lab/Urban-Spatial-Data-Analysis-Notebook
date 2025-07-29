import json
import eviltransform
import sys
from pathlib import Path

import folium

# 获取脚本所在目录
script_dir = Path(__file__).parent

# 读取景点坐标
locations_file = script_dir / "cache" / "chengdu_locations_gcj02.json"
with open(locations_file, "r", encoding="utf-8") as f:
    locations = json.load(f)

# 先转换所有点为WGS84坐标，保持顺序
coords_wgs = []
names = []
for name, value in locations.items():
    lon, lat = value
    # 注意：现在坐标是GCJ02，需要用gcj2wgs转换
    wgs_lat, wgs_lon = eviltransform.gcj2wgs(lat, lon)
    coords_wgs.append((wgs_lat, wgs_lon))
    names.append(name)

print(f"正在绘制所有景点分布地图: {len(coords_wgs)}个景点:{locations}")

# 以第一个点为中心
m = folium.Map(location=coords_wgs[0], zoom_start=13)

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

output_file = script_dir / "data/maps/all_locations_map.html"
# 确保输出目录存在
output_file.parent.mkdir(parents=True, exist_ok=True)
# 保存地图到HTML文件
m.save(output_file)
print(f"已生成所有景点分布地图: {output_file}")
