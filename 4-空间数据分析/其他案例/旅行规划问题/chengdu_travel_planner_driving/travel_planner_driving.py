"""
成都一日游智能规划系统 - 驾车版 - demo
使用百度地图API获取真实驾车时间
"""
import os
import math
import time
import random

import eviltransform
import requests
from typing import List, Tuple

import json
import configparser

import folium
import shutil

class TravelPlanner:

    def __init__(self, mode: str = "driving"):
        config = configparser.ConfigParser()
        
        self.base_url = "https://api.map.baidu.com"
        self.mode = mode

        # 尝试读取baidu api key
        if not os.path.exists("config.ini"):
            print("未找到 config.ini 文件。")
            try:
                shutil.copy("config.ini.example", "config.ini")
                print("已自动从 config.ini.example 复制生成 config.ini。")
                print("请在 config.ini 文件中填写您的百度地图API key后，重新运行程序。")
                exit() # 退出程序，让用户填写key
            except Exception as e:
                print(f"自动复制文件失败: {e}")

        config.read("config.ini")
        self.api_key = config["baidu_map"]["api_key"]

        # 从JSON文件加载地点
        with open("chengdu_travel_planner_driving/cache/chengdu_locations.json", "r", encoding="utf-8") as f:
            self.locations = json.load(f)

        self.location_names = list(self.locations.keys())
        self.n = len(self.location_names)

        # 缓存机制：点对缓存，减少重复计算
        self.cache_file = f"chengdu_travel_planner_driving/cache/chengdu_travel_time_cache_{self.mode}.json"
        self.path_cache_file = f"chengdu_travel_planner_driving/cache/chengdu_travel_path_cache_{self.mode}.json"
        
        # 先初始化路径缓存，再计算距离矩阵
        self.path_cache = self._load_path_cache()
        self.distance_matrix = self._load_or_calc_travel_time_matrix_optimized()


    def _load_path_cache(self) -> dict:
        """加载路径缓存"""
        if os.path.exists(self.path_cache_file):
            try:
                with open(self.path_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[PATH_CACHE] 读取路径缓存失败: {e}")
        return {}

    def _load_or_calc_travel_time_matrix_optimized(self) -> list:
        """优化：点对缓存，动态补全，减少重复计算"""


        # 加载点对缓存
        cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                print(f"[CACHE] 已加载本地缓存: {self.cache_file}")
            except Exception as e:
                print(f"[CACHE] 读取缓存失败: {e}，将重新获取并缓存。")

        updated = False
        matrix = []
        for i, origin in enumerate(self.location_names):
            row = []
            for j, destination in enumerate(self.location_names):
                if i == j:
                    row.append(0)
                else:
                    key = f"{origin}|{destination}"
                    if key in cache:
                        time_minutes = cache[key]
                    else:
                        time_minutes = self._get_travel_time(origin, destination)
                        cache[key] = time_minutes
                        updated = True
                        print(f"[CACHE] 新增: {key} = {time_minutes:.1f}分钟")
                        # 实时写入，防止中断丢失
                        try:
                            with open(self.cache_file, "w", encoding="utf-8") as f:
                                json.dump(cache, f, ensure_ascii=False, indent=2)
                            # 同时保存路径缓存
                            with open(self.path_cache_file, "w", encoding="utf-8") as f:
                                json.dump(self.path_cache, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            print(f"[CACHE] 保存缓存失败: {e}")
                    row.append(time_minutes)
            matrix.append(row)

        # 最后再整体写一次，防止遗漏
        if updated:
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                print(f"[CACHE] 已保存本地缓存: {self.cache_file}")
                # 同时保存路径缓存
                with open(self.path_cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.path_cache, f, ensure_ascii=False, indent=2)
                print(f"[PATH_CACHE] 已保存路径缓存: {self.path_cache_file}")
            except Exception as e:
                print(f"[CACHE] 保存缓存失败: {e}")
        return matrix

    def _get_travel_time(self, origin: str, destination: str) -> float:
        """使用百度地图API获取两点间的出行时间（分钟）"""
        try:
            # 根据模式选择不同API
            url_map = {
                "driving": "/direction/v2/driving", # TODO 支持18个以内的途径点，可以测试一下直接让百度api规划的路程是怎样的，但是必须要指定途径点顺序，不符合项目要求。目前我们还无法确定途径点顺序。
                "walking": "/direction/v2/walking",
                "transit": "/direction/v2/transit",
            }
            api_url = (
                f"{self.base_url}{url_map.get(self.mode, '/direction/v2/driving')}"
            )

            params = {
                "origin": f"{self.locations[origin][1]},{self.locations[origin][0]}",  # 纬度,经度
                "destination": f"{self.locations[destination][1]},{self.locations[destination][0]}",
                "ak": self.api_key,
                # "tactics": 2,  # 距离最短（只返回一条路线，不考虑限行和路况，距离最短且稳定，用于估价场景）
            }
            # 公交模式需要指定城市
            if self.mode == "transit":
                params["region"] = "成都市" #　TODO: 这里可以改为动态获取城市名

            response = requests.get(api_url, params=params, timeout=10)
            data = response.json()

            if data.get("status") == 0 and "result" in data:
                # 不同模式下，API返回的耗时字段不同
                if self.mode in ["driving", "walking"]:
                    duration = data["result"]["routes"][0]["duration"]
                    # 提取真实路径坐标
                    self._extract_and_save_path(origin, destination, data["result"]["routes"][0])
                elif self.mode == "transit":
                    raise NotImplementedError("公交路线的路径提取暂未测试")
                    duration = data["result"]["routes"][0].get(
                        "duration", 0
                    )  # 公交可能存在查不到路线的情况
                    # 公交路线的路径提取较复杂，暂时跳过
                else:
                    duration = 0

                return duration / 60  # 转换为分钟
            else:
                print(f"API错误: {data.get('message', '未知错误')}")
                return self._fallback_distance(origin, destination)

        except Exception as e:
            print(f"获取出行时间失败: {e}")
            return self._fallback_distance(origin, destination)

    def _extract_and_save_path(self, origin: str, destination: str, route_data: dict):
        """提取并保存真实路径坐标"""
        try:
            # 确保path_cache已初始化
            if not hasattr(self, 'path_cache'):
                self.path_cache = {}
                
            key = f"{origin}|{destination}"
            path_coords = []
            
            # 提取steps中的path信息
            if "steps" in route_data:
                for step in route_data["steps"]:
                    if "path" in step:
                        # path格式: "116.339646,40.010519;116.340006,40.010546;..."
                        path_str = step["path"]
                        coords = path_str.split(";")
                        for coord in coords:
                            if coord.strip():
                                lon, lat = map(float, coord.split(","))
                                path_coords.append([lat, lon])  # 存储为[纬度, 经度]
            
            # 保存到路径缓存
            if path_coords:
                self.path_cache[key] = path_coords
                print(f"[PATH_CACHE] 保存路径: {key} ({len(path_coords)}个坐标点)")
            else:
                print(f"[PATH_CACHE] 未找到路径数据: {key}")
            
        except Exception as e:
            print(f"[PATH_CACHE] 提取路径失败 {origin}->{destination}: {e}")
            # 确保path_cache存在以避免后续错误
            if not hasattr(self, 'path_cache'):
                self.path_cache = {}

    def _fallback_distance(self, origin: str, destination: str) -> float:
        """备用方案：使用Haversine公式计算直线距离并估算驾车时间"""
        lat1, lon1 = self.locations[origin]
        lat2, lon2 = self.locations[destination]

        # Haversine公式计算直线距离
        R = 6371  # 地球半径（公里）
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        distance_km = R * c

        # 根据模式估算时间
        speed_kmh = 30  # 默认驾车速度
        if self.mode == "walking":
            speed_kmh = 5  # 步行速度
        elif self.mode == "transit":
            speed_kmh = 20  # 公交估算速度

        estimated_time_hours = distance_km / speed_kmh
        return estimated_time_hours * 60  # 转换为分钟

    def _calculate_travel_time_matrix(self) -> List[List[float]]:
        """计算所有景点间的出行时间矩阵"""
        print(f"[{self.mode.upper()}] 正在获取真实出行时间...")
        matrix = []

        for i, origin in enumerate(self.location_names):
            row = []
            for j, destination in enumerate(self.location_names):
                if i == j:
                    row.append(0)
                else:
                    time_minutes = self._get_travel_time(origin, destination)
                    row.append(time_minutes)
                    print(f"{origin} → {destination}: {time_minutes:.1f}分钟")
                    time.sleep(0.3)  # 避免API调用过于频繁
            matrix.append(row)

        return matrix

    def nearest_neighbor_tsp(self) -> Tuple[List[int], float]:
        """最近邻算法求解TSP，指定终点为最后一个点"""
        print("\n=== 最近邻算法 ===")
        if self.n < 2:
            return [0], 0
        start = 0
        end = self.n - 1
        unvisited = set(range(self.n))
        unvisited.remove(start)
        if end != start:
            unvisited.remove(end)
        current = start
        path = [current]
        total_time = 0

        while unvisited:
            # 如果只剩最后一个未访问点且是终点，则直接跳出
            if len(unvisited) == 1 and end in unvisited:
                break
            # 找到最近的未访问景点（不包括终点）
            candidates = unvisited - {end}
            if not candidates:
                break
            nearest = min(candidates, key=lambda x: self.distance_matrix[current][x])
            time_to_next = self.distance_matrix[current][nearest]
            total_time += time_to_next
            print(
                f"从 {self.location_names[current]} 到 {self.location_names[nearest]}: {time_to_next:.1f}分钟"
            )
            current = nearest
            path.append(current)
            unvisited.remove(current)

        # 最后加上终点
        if end != start:
            time_to_next = self.distance_matrix[current][end]
            total_time += time_to_next
            print(
                f"从 {self.location_names[current]} 到 {self.location_names[end]}: {time_to_next:.1f}分钟"
            )
            path.append(end)
        return path, total_time

    def genetic_algorithm_tsp(
        self, population_size: int = 50, generations: int = 100
    ) -> Tuple[List[int], float]:
        """遗传算法求解TSP，指定终点为最后一个点"""
        print(f"\n=== 遗传算法 (种群大小: {population_size}, 代数: {generations}) ===")
        if self.n < 2:
            return [0], 0
        start = 0
        end = self.n - 1
        # 初始化种群，个体以end结尾
        population = []
        for _ in range(population_size):
            middle = (
                list(range(1, self.n - 1)) if end != start else list(range(1, self.n))
            )
            random.shuffle(middle)
            if end != start:
                individual = [start] + middle + [end]
            else:
                individual = [start] + middle
            population.append(individual)

        # 初始化最优解
        if end != start:
            best_individual = [start] + list(range(1, self.n - 1)) + [end]
        else:
            best_individual = list(range(self.n))
        best_fitness = self._calculate_path_time(best_individual)

        for generation in range(generations):
            # 计算适应度
            fitness_scores = []
            for individual in population:
                fitness = self._calculate_path_time(individual)
                fitness_scores.append(fitness)
                if fitness < best_fitness:
                    best_fitness = fitness
                    best_individual = individual[:]

            # 选择
            new_population = []
            for _ in range(population_size):
                total_fitness = sum(1 / f for f in fitness_scores)
                r = random.uniform(0, total_fitness)
                cumulative = 0
                for i, fitness in enumerate(fitness_scores):
                    cumulative += 1 / fitness
                    if cumulative >= r:
                        new_population.append(population[i][:])
                        break

            # 交叉和变异，保证终点固定
            for i in range(0, population_size, 2):
                if i + 1 < population_size:
                    if random.random() < 0.8:
                        child1, child2 = self._crossover_with_end(
                            new_population[i], new_population[i + 1], end
                        )
                        new_population[i] = child1
                        new_population[i + 1] = child2
                    if random.random() < 0.1:
                        new_population[i] = self._mutate_with_end(
                            new_population[i], end
                        )
                    if random.random() < 0.1:
                        new_population[i + 1] = self._mutate_with_end(
                            new_population[i + 1], end
                        )

            population = new_population

            if generation % 20 == 0:
                print(f"第 {generation} 代，最佳时间: {best_fitness:.1f}分钟")

        return best_individual, best_fitness

    def ant_colony_optimization_tsp(
        self,
        num_ants: int = 50,
        iterations: int = 100,
        alpha: float = 1.0,
        beta: float = 2.0,
        rho: float = 0.5,
        q: float = 100,
    ) -> Tuple[List[int], float]:
        """蚁群算法求解TSP，指定终点为最后一个点

        参数:
        - num_ants: 蚂蚁数量
        - iterations: 迭代次数
        - alpha: 信息素重要程度
        - beta: 启发式信息重要程度
        - rho: 信息素挥发率
        - q: 信息素增强系数
        """
        print(f"\n=== 蚁群算法 (蚂蚁数量: {num_ants}, 迭代次数: {iterations}) ===")
        if self.n < 2:
            return [0], 0

        start = 0
        end = self.n - 1

        # 初始化信息素矩阵
        pheromone = [[1.0 for _ in range(self.n)] for _ in range(self.n)]

        # 计算启发式信息矩阵（1/距离）
        heuristic = [[0.0 for _ in range(self.n)] for _ in range(self.n)]
        for i in range(self.n):
            for j in range(self.n):
                if i != j and self.distance_matrix[i][j] > 0:
                    heuristic[i][j] = 1.0 / self.distance_matrix[i][j]
                else:
                    heuristic[i][j] = 0.0

        # 初始化最优解
        if end != start:
            best_path = [start] + list(range(1, self.n - 1)) + [end]
        else:
            best_path = list(range(self.n))
        best_length = self._calculate_path_time(best_path)

        for iteration in range(iterations):
            # 存储本轮所有蚂蚁的路径和长度
            ant_paths = []
            ant_lengths = []

            for ant in range(num_ants):
                path = self._ant_construct_path(
                    start, end, pheromone, heuristic, alpha, beta
                )
                length = self._calculate_path_time(path)
                ant_paths.append(path)
                ant_lengths.append(length)

                # 更新最优解
                if length < best_length:
                    best_length = length
                    best_path = path[:]

            # 更新信息素
            self._update_pheromones(pheromone, ant_paths, ant_lengths, rho, q)

            if iteration % 20 == 0:
                print(f"第 {iteration} 次迭代，最佳时间: {best_length:.1f}分钟")

        return best_path, best_length

    def _ant_construct_path(
        self,
        start: int,
        end: int,
        pheromone: List[List[float]],
        heuristic: List[List[float]],
        alpha: float,
        beta: float,
    ) -> List[int]:
        """单只蚂蚁构造路径"""
        path = [start]
        unvisited = set(range(self.n))
        unvisited.remove(start)
        if end != start:
            unvisited.remove(end)  # 终点最后访问

        current = start

        # 构造路径直到只剩终点
        while unvisited:
            # 如果只剩下一个城市且不是终点，直接选择
            if len(unvisited) == 1 and end not in unvisited:
                next_city = list(unvisited)[0]
            else:
                # 计算转移概率
                probabilities = []
                cities = list(
                    unvisited - {end}
                    if end in unvisited and len(unvisited) > 1
                    else unvisited
                )

                if not cities:  # 如果没有可选城市，跳出循环
                    break

                total_prob = 0.0
                for city in cities:
                    tau = pheromone[current][city] ** alpha
                    eta = heuristic[current][city] ** beta
                    prob = tau * eta
                    probabilities.append(prob)
                    total_prob += prob

                # 避免除零错误
                if total_prob == 0:
                    next_city = random.choice(cities)
                else:
                    # 轮盘赌选择
                    probabilities = [p / total_prob for p in probabilities]
                    next_city = self._roulette_wheel_selection(cities, probabilities)

            path.append(next_city)
            unvisited.remove(next_city)
            current = next_city

        # 最后添加终点
        if end != start:
            path.append(end)

        return path

    def _roulette_wheel_selection(
        self, cities: List[int], probabilities: List[float]
    ) -> int:
        """轮盘赌选择"""
        r = random.random()
        cumulative = 0.0
        for i, prob in enumerate(probabilities):
            cumulative += prob
            if cumulative >= r:
                return cities[i]
        return cities[-1]  # 防止浮点数精度问题

    def _update_pheromones(
        self,
        pheromone: List[List[float]],
        ant_paths: List[List[int]],
        ant_lengths: List[float],
        rho: float,
        q: float,
    ):
        """更新信息素"""
        # 信息素挥发
        for i in range(self.n):
            for j in range(self.n):
                pheromone[i][j] *= 1 - rho

        # 信息素增强
        for path, length in zip(ant_paths, ant_lengths):
            if length > 0:  # 避免除零错误
                delta_pheromone = q / length
                for i in range(len(path) - 1):
                    from_city = path[i]
                    to_city = path[i + 1]
                    pheromone[from_city][to_city] += delta_pheromone
                    pheromone[to_city][from_city] += delta_pheromone  # 对称更新

    def _crossover_with_end(
        self, parent1: List[int], parent2: List[int], end: int
    ) -> Tuple[List[int], List[int]]:
        """交叉操作，保证终点固定"""


        # 不动首尾
        start = 1
        stop = len(parent1) - 1 if parent1[-1] == end else len(parent1)
        if stop - start <= 1:
            return parent1[:], parent2[:]
        a, b = sorted(random.sample(range(start, stop), 2))

        def cross(p1, p2):
            child = p1[:a] + [x for x in p2[a:b] if x not in p1[:a]]
            child += [x for x in p1[a:stop] if x not in child]
            if stop < len(p1):
                child += p1[stop:]
            if end not in child:
                child.append(end)
            return child

        return cross(parent1, parent2), cross(parent2, parent1)

    def _mutate_with_end(self, individual: List[int], end: int) -> List[int]:
        """变异操作，保证终点固定"""

        mutated = individual[:]
        if len(mutated) > 3:
            i, j = random.sample(range(1, len(mutated) - 1), 2)
            mutated[i], mutated[j] = mutated[j], mutated[i]
        return mutated

    def _calculate_path_time(self, path: List[int]) -> float:
        """计算路径总时间"""
        total_time = 0
        for i in range(len(path) - 1):
            total_time += self.distance_matrix[path[i]][path[i + 1]]
        return total_time

    def _crossover(
        self, parent1: List[int], parent2: List[int]
    ) -> Tuple[List[int], List[int]]:
        """交叉操作"""

        start, end = sorted(random.sample(range(1, len(parent1)), 2))

        child1 = parent1[:start] + [
            x for x in parent2[start:end] if x not in parent1[:start]
        ]
        child1 += [x for x in parent1[start:] if x not in child1]

        child2 = parent2[:start] + [
            x for x in parent1[start:end] if x not in parent2[:start]
        ]
        child2 += [x for x in parent2[start:] if x not in child2]

        return child1, child2

    def _mutate(self, individual: List[int]) -> List[int]:
        """变异操作"""

        mutated = individual[:]
        if len(mutated) > 2:
            i, j = random.sample(range(1, len(mutated)), 2)
            mutated[i], mutated[j] = mutated[j], mutated[i]
        return mutated

    def print_route_details(
        self, path: List[int], total_time: float, algorithm_name: str
    ):
        """打印路线详情"""
        print(f"\n=== {algorithm_name} 路线详情 ===")
        print(f"总驾车时间: {total_time:.1f}分钟 ({total_time/60:.1f}小时)")
        print("\n详细路线:")

        for i in range(len(path)):
            current = self.location_names[path[i]]
            if i < len(path) - 1:
                next_loc = self.location_names[path[i + 1]]
                time_to_next = self.distance_matrix[path[i]][path[i + 1]]
                print(f"{i+1}. {current} → {next_loc} ({time_to_next:.1f}分钟)")
            else:
                print(f"{i+1}. {current} (终点)")

        print(f"\n时间安排建议:")
        n_spots = len(path)
        visit_time = 1 * n_spots
        print(f"假设每个景点游览1小时，总游览时间: {visit_time}小时")
        print(f"总驾车时间: {total_time / 60:.1f}小时")
        total_trip_time = visit_time + total_time / 60
        print(f"总行程时间: {total_trip_time:.1f}小时")
        if total_trip_time <= 16:
            print("✅ 一天内可以完成！")
        else:
            print("⚠️ 建议分两天游览")

    def plot_route_on_map(self, path: list, map_filename: str = "route_map.html"):
        """使用folium可视化路线，生成HTML地图 - 使用真实车行路径"""

        # 获取景点坐标顺序
        coords = [self.locations[self.location_names[i]] for i in path]
        # folium要求坐标为(纬度, 经度)
        coords_latlng = [(latlng[1], latlng[0]) for latlng in coords]
        # 转换为WGS84坐标系
        coords_latlng = [eviltransform.bd2wgs(lat, lon) for lat, lon in coords_latlng]

        # 以第一个景点为中心，自动调整缩放
        m = folium.Map(location=coords_latlng[0], zoom_start=12)
        
        # 收集所有真实路径坐标用于调整地图边界
        all_route_coords = coords_latlng.copy()

        # 添加景点标记和名称
        for idx, (lat, lon) in enumerate(coords_latlng):
            marker = folium.Marker(
                location=(lat, lon),
                popup=f"<b>{idx+1}. {self.location_names[path[idx]]}</b>",
                icon=folium.Icon(
                    color=(
                        "green"
                        if idx == 0
                        else "red" if idx == len(coords_latlng) - 1 else "blue"
                    ),
                    icon="info-sign",
                ),
            )
            # 添加永久显示的标签
            folium.Tooltip(
                f"{idx+1}. {self.location_names[path[idx]]}",
                permanent=True,
                direction="right",
                offset=(10, 0),
                style="color: navy; font-weight: bold;",
            ).add_to(marker)
            marker.add_to(m)

        # 绘制真实车行路线
        total_path_points = 0
        for i in range(len(path) - 1):
            origin = self.location_names[path[i]]
            destination = self.location_names[path[i + 1]]
            key = f"{origin}|{destination}"
            
            if key in self.path_cache and self.path_cache[key]:
                # 使用真实路径
                real_path_coords = self.path_cache[key]
                # 转换为WGS84坐标系
                real_path_wgs84 = [eviltransform.bd2wgs(lat, lon) for lat, lon in real_path_coords]
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
                start_coord = coords_latlng[i]
                end_coord = coords_latlng[i + 1]
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
        m.save(map_filename)
        print(f"已生成路线地图: {map_filename} (共使用{total_path_points}个真实路径点)")
        if total_path_points == 0:
            print("⚠️ 未找到真实路径数据，建议重新运行以获取路径信息")


def main():
    print("🚗 成都一日游智能规划系统 - 驾车版")
    print("=" * 50)

    planner = TravelPlanner()

    # 最近邻算法
    nn_path, nn_time = planner.nearest_neighbor_tsp()
    planner.print_route_details(nn_path, nn_time, "最近邻算法")
    planner.plot_route_on_map(nn_path, map_filename="route_map_nn.html")

    # 遗传算法
    ga_path, ga_time = planner.genetic_algorithm_tsp(
        population_size=500, generations=200
    )
    planner.print_route_details(ga_path, ga_time, "遗传算法")
    planner.plot_route_on_map(ga_path, map_filename="route_map_ga.html")

    # 蚁群算法
    aco_path, aco_time = planner.ant_colony_optimization_tsp(
        num_ants=500, iterations=100, alpha=1.0, beta=2.0, rho=0.5, q=100
    )
    planner.print_route_details(aco_path, aco_time, "蚁群算法")
    planner.plot_route_on_map(aco_path, map_filename="route_map_aco.html")

    # 算法比较
    print(f"\n=== 算法比较 ===")
    print(f"最近邻算法: {nn_time:.1f}分钟")
    print(f"遗传算法: {ga_time:.1f}分钟")
    print(f"蚁群算法: {aco_time:.1f}分钟")

    # 找出最优算法
    results = [("最近邻算法", nn_time), ("遗传算法", ga_time), ("蚁群算法", aco_time)]
    best_algorithm, best_time = min(results, key=lambda x: x[1])

    print(f"\n🏆 最优算法: {best_algorithm} ({best_time:.1f}分钟)")

    # 计算改进百分比
    worst_time = max(results, key=lambda x: x[1])[1]
    if worst_time > best_time:
        improvement = ((worst_time - best_time) / worst_time) * 100
        print(f"相比最差算法优化了 {improvement:.1f}%")


if __name__ == "__main__":
    main()
