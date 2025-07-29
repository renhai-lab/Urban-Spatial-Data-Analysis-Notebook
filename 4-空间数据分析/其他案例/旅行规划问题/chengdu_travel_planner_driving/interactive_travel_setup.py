import json
import subprocess
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv
import os


def get_location_from_amap(place, api_key):
    """使用高德地图API获取地点坐标（GCJ02坐标系）"""
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "address": place,
        "output": "json", 
        "key": api_key,
        "city": "成都市",  # 指定城市，避免歧义
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        print(f"获取 {place} 坐标响应: {data}")     
        if data.get("status") == "1" and data.get("geocodes"):
            location = data["geocodes"][0]["location"]
            lng, lat = map(float, location.split(","))
            return [lng, lat]  # 返回[经度, 纬度] (GCJ02坐标系)
        else:
            print(f"获取 {place} 坐标失败: {data.get('info', data)}")
            return None
    except Exception as e:
        print(f"获取 {place} 坐标失败: {e}")
        return None


def main():
    """交互式旅行规划设置"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent
    
    # 从.env文件加载环境变量
    env_file = script_dir.parent / ".env"
    env_example = script_dir.parent / ".env.example"

    # 检查.env文件是否存在
    if not env_file.exists():
        print("未找到 .env 文件。")
        if env_example.exists():
            try:
                import shutil
                shutil.copy(env_example, env_file)
                print("已自动从 .env.example 复制生成 .env 文件。")
                print("请在 .env 文件中填写您的 AMAP_API_KEY 后，重新运行程序。")
                sys.exit(1)
            except Exception as e:
                print(f"自动复制文件失败: {e}")
                sys.exit(1)
        else:
            print("也未找到 .env.example 文件。请创建一个 .env 文件并设置 AMAP_API_KEY。")
            sys.exit(1)

    # 加载环境变量
    load_dotenv(dotenv_path=env_file)
    api_key = os.getenv("AMAP_API_KEY")
    
    if not api_key:
        print("在 .env 文件中未找到或未设置 AMAP_API_KEY。")
        print("请确保 .env 文件中有 'AMAP_API_KEY=your_key_here' 这一行。")
        sys.exit(1)

    print("🗺️ 成都一日游智能规划系统 - 交互式设置")
    print("=" * 50)
    print("请输入你想去的景点名称（每行一个，输入空行结束）")
    print("第一个景点将作为起点，最后一个将作为终点")
    print("\n示例景点：")
    print("- 成都东站")
    print("- 成都西村大院") 
    print("- 成都水井坊博物馆")
    print("- 成都太古里")
    print("- 成都当代美术馆")
    print("- 成都来福士广场")
    print("\n开始输入景点名称：")
    
    places = []
    while True:
        place = input(f"你的输入: ").strip()
        if not place:
            break
        places.append(place)

    if len(places) < 2:
        print("⚠️ 至少需要输入2个景点才能进行路线规划。")
        sys.exit(1)

    print(f"\n📍 正在获取 {len(places)} 个景点的坐标...")
    
    # 获取景点坐标
    locations = []
    for i, place in enumerate(places, 1):
        print(f"[{i}/{len(places)}] 获取 {place} 的坐标...")
        coords = get_location_from_amap(place, api_key)
        if coords:
            locations.append((place, coords))
            print(f"✅ {place}: [{coords[0]:.6f}, {coords[1]:.6f}] (GCJ02)")
        else:
            print(f"❌ 无法获取 {place} 的坐标，跳过此景点")
    
    if len(locations) < 2:
        print("❌ 有效景点少于2个，无法进行路线规划。")
        sys.exit(1)

    # 确保缓存目录存在
    cache_dir = script_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    
    # 保存景点坐标到JSON文件
    from collections import OrderedDict
    locations_dict = OrderedDict(locations)
    locations_file = cache_dir / "chengdu_locations_gcj02.json"
    
    with open(locations_file, "w", encoding="utf-8") as f:
        json.dump(locations_dict, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存景点位置到: {locations_file}")
    print("\n📋 景点列表:")
    for i, (name, coords) in enumerate(locations_dict.items(), 1):
        role = "起点" if i == 1 else "终点" if i == len(locations_dict) else "途经点"
        print(f"  {i}. {name} ({role}) - [{coords[0]:.6f}, {coords[1]:.6f}]")

    # 生成预览地图
    plot_script = script_dir / "plot_locations.py"
    if plot_script.exists():
        print(f"\n🗺️ 正在生成预览地图...")
        try:
            subprocess.run([sys.executable, str(plot_script)], check=True)
            print("✅ 地图已生成，请确认地图是否正确。")
            input("确认无误后按回车继续...")
        except subprocess.CalledProcessError:
            print("⚠️ 地图生成失败，但可以继续进行路线规划。")
    else:
        print("⚠️ 未找到 plot_locations.py，跳过地图预览。")

    # 运行路线规划
    print(f"\n🚗 开始运行路线规划算法...")
    try:
        # 直接导入并运行
        from travel_planner_driving import TravelPlanner
        
        planner = TravelPlanner()
        print("正在运行遗传算法...")
        path, time_cost = planner.genetic_algorithm_tsp()
        
        planner.print_route_details(path, time_cost, "遗传算法")
        planner.plot_route_on_map(path, map_filename="route_map_ga.html")
        
        print(f"\n🎉 路线规划完成！")
        print(f"📄 HTML地图已生成: route_map_ga.html")
        
    except Exception as e:
        print(f"❌ 路线规划失败: {e}")
        print("请检查API密钥是否正确配置。")


if __name__ == "__main__":
    main()
