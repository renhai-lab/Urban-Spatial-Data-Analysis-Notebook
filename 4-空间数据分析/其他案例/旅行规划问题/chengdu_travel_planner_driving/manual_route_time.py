import json
import folium
import eviltransform
from pathlib import Path
from travel_planner_driving import TravelPlanner


def plot_manual_route(waypoints, locations, path_cache, map_filename="manual_route_map.html"):
    """绘制手动输入的路线图"""
    print(f"\n正在生成路线地图...")
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    
    # 获取景点坐标顺序
    coords_latlng = []
    for waypoint in waypoints:
        lon, lat = locations[waypoint] # locations现在是GCJ02坐标
        coords_latlng.append((lat, lon))
    
    # 转换为WGS84坐标系
    coords_latlng_wgs84 = [eviltransform.gcj2wgs(lat, lon) for lat, lon in coords_latlng]
    
    # 以第一个景点为中心，自动调整缩放
    m = folium.Map(location=coords_latlng_wgs84[0], zoom_start=12)
    
    # 收集所有真实路径坐标用于调整地图边界
    all_route_coords = coords_latlng_wgs84.copy()
    
    # 添加景点标记和名称
    for idx, (lat, lon) in enumerate(coords_latlng_wgs84):
        marker = folium.Marker(
            location=(lat, lon),
            popup=f"<b>{idx+1}. {waypoints[idx]}</b>",
            icon=folium.Icon(
                color=(
                    "green"
                    if idx == 0
                    else "red" if idx == len(coords_latlng_wgs84) - 1 else "blue"
                ),
                icon="info-sign",
            ),
        )
        # 添加永久显示的标签
        folium.Tooltip(
            f"{idx+1}. {waypoints[idx]}",
            permanent=True,
            direction="right",
            offset=(10, 0),
            style="color: navy; font-weight: bold;",
        ).add_to(marker)
        marker.add_to(m)
    
    # 绘制真实车行路线
    total_path_points = 0
    for i in range(len(waypoints) - 1):
        origin = waypoints[i]
        destination = waypoints[i + 1]
        key = f"{origin}|{destination}"
        
        if key in path_cache and path_cache[key]:
            # 使用真实路径
            real_path_coords = path_cache[key]
            # 转换为WGS84坐标系（现在路径是GCJ02坐标）
            real_path_wgs84 = [eviltransform.gcj2wgs(lat, lon) for lat, lon in real_path_coords]
            all_route_coords.extend(real_path_wgs84)
            
            # 绘制这段路径
            folium.PolyLine(
                real_path_wgs84, 
                color="red", 
                weight=3, 
                opacity=0.8,
                popup=f"{origin} → {destination}"
            ).add_to(m)
            
            total_path_points += len(real_path_coords)
            print(f"绘制真实路径: {origin} → {destination} ({len(real_path_coords)}个坐标点)")
        else:
            # 降级到直线连接
            start_coord = coords_latlng_wgs84[i]
            end_coord = coords_latlng_wgs84[i + 1]
            folium.PolyLine(
                [start_coord, end_coord], 
                color="blue", 
                weight=2, 
                opacity=0.6,
                popup=f"{origin} → {destination} (直线)"
            ).add_to(m)
            print(f"使用直线连接: {origin} → {destination} (缺少真实路径数据)")
    
    # 调整地图边界以包含所有路径点
    if all_route_coords:
        m.fit_bounds(all_route_coords)
    
    # 保存为HTML
    output_path = script_dir.parent / "data/map" / map_filename
    m.save(output_path)
    print(f"已生成路线地图: {output_path} (共使用{total_path_points}个真实路径点)")
    if total_path_points == 0:
        print("⚠️ 未找到真实路径数据，建议重新运行以获取路径信息")
    else:
        print(f"✅ 地图已保存，请打开 {output_path} 查看路线")


def main():
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    
    # 加载地点
    locations_file = script_dir / "cache" / "chengdu_locations_gcj02.json"
    with open(locations_file, "r", encoding="utf-8") as f:
        locations = json.load(f)
    location_names = list(locations.keys())
    print("可用景点：")
    for idx, name in enumerate(location_names):
        print(f"{idx+1}. {name}")
    print("请输入途径点序号（如1 5 6 9 3 4 7 2 8 10，空格分隔，按顺序）：")
    idx_line = input().strip()
    if not idx_line:
        print("未输入任何内容！")
        return
    try:
        idxs = [int(x) - 1 for x in idx_line.split()]
    except Exception:
        print("输入格式有误，请输入空格分隔的数字序号！")
        return
    waypoints = []
    for idx in idxs:
        if 0 <= idx < len(location_names):
            waypoints.append(location_names[idx])
        else:
            print(f"序号{idx+1}超出范围，已忽略。")
    if len(waypoints) < 2:
        print("至少需要两个有效点！")
        return
    # 优先查缓存
    try:
        cache_file = script_dir / "cache" / "chengdu_travel_time_cache_driving.json"
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    planner = TravelPlanner()
    total_time = 0
    print("\n路线时间明细：")
    for i in range(len(waypoints) - 1):
        a, b = waypoints[i], waypoints[i + 1]
        key = f"{a}|{b}"
        if key in cache:
            t = cache[key]
        else:
            t = planner._get_travel_time(a, b)
        print(f"{a} → {b}: {t:.1f} 分钟")
        total_time += t
    print(f"\n总行程时间：{total_time:.1f} 分钟（{total_time/60:.2f} 小时）")
    
    # 绘制路线图
    plot_manual_route(waypoints, locations, planner.path_cache)


if __name__ == "__main__":
    main()
