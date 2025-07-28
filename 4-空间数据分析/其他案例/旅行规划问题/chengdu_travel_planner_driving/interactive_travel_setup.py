import json
import subprocess
import sys
import os
import requests


def get_location_from_baidu(place, api_key):
    url = "https://api.map.baidu.com/geocoding/v3/"
    params = {"address": place, "output": "json", "ak": api_key}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data.get("status") == 0:
        lng = data["result"]["location"]["lng"]
        lat = data["result"]["location"]["lat"]
        return [lng, lat]
    else:
        print(f"获取 {place} 坐标失败: {data.get('msg', data)}")
        return None


def main():
    # 读取API KEY
    import configparser

    config = configparser.ConfigParser()
    config.read("config.ini")
    api_key = config["baidu_map"]["api_key"]

    print(
        "请输入你想去的景点名称（每行一个，输入空行结束,第一个是起点），示例：成都东站\n成都西村大院\n成都水井坊博物馆\n成都太古里\n成都当代美术馆\n成都来福士广场"
    )
    places = []
    while True:
        place = input()
        if not place.strip():
            break
        places.append(place.strip())

    # 保证第一个输入的点为第一个key
    locations = []
    for place in places:
        coords = get_location_from_baidu(place, api_key)
        if coords:
            locations.append((place, coords))
    if not locations:
        print("未获取到任何有效坐标，程序退出。")
        sys.exit(1)

    # 按输入顺序保存到有序dict
    from collections import OrderedDict

    locations_dict = OrderedDict(locations)
    with open("chengdu_travel_planner_driving/cache/chengdu_locations.json", "w", encoding="utf-8") as f:
        json.dump(locations_dict, f, ensure_ascii=False, indent=2)
    print("已保存chengdu_travel_planner_driving/cache/chengdu_locations.json：")
    print(json.dumps(locations_dict, ensure_ascii=False, indent=2))

    # 调用plot_locations.py画图
    print("正在生成地图...")
    subprocess.run([sys.executable, "plot_locations.py"])
    print("地图已生成，请确认地图是否正确。")
    input("确认无误后按回车继续...")

    # 调用travel_planner_driving.py，仅运行遗传算法部分
    print("开始运行travel_planner_driving.py的遗传算法...")
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from travel_planner_driving import TravelPlanner; p=TravelPlanner(); path, t=p.genetic_algorithm_tsp(); p.print_route_details(path, t, '遗传算法'); p.plot_route_on_map(path, map_filename='route_map_ga.html')",
        ]
    )


if __name__ == "__main__":
    main()
