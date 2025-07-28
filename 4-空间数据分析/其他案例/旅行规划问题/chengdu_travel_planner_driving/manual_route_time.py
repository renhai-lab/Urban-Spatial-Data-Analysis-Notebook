import json
from travel_planner_driving import TravelPlanner


def main():
    # 加载地点
    with open("cache/chengdu_locations.json", "r", encoding="utf-8") as f:
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
        with open("travel_time_cache_driving.json", "r", encoding="utf-8") as f:
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


if __name__ == "__main__":
    main()
