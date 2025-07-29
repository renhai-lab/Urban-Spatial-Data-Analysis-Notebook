"""
成都一日游智能规划系统 - 驾车版 - demo
使用高德地图API获取真实驾车时间
"""
import os
import math
import time
import random
import argparse
from pathlib import Path

import eviltransform
import requests
from typing import List, Tuple

import json
from dotenv import load_dotenv

import folium
import shutil

class TravelPlanner:
    def __init__(self, mode: str = "driving"):
        # 获取脚本所在目录
        self.script_dir = Path(__file__).parent
        self.base_url = "https://restapi.amap.com"
        self.mode = mode

        # 从.env文件加载环境变量
        
        env_file = self.script_dir.parent / ".env"
        env_example = self.script_dir.parent / ".env.example"

        # 检查.env文件是否存在，如果不存在则从.env.example复制
        if not env_file.exists():
            print("未找到 .env 文件。")
            if env_example.exists():
                try:
                    shutil.copy(env_example, env_file)
                    print("已自动从 .env.example 复制生成 .env 文件。")
                    print("请在 .env 文件中填写您的 AMAP_API_KEY 后，重新运行程序。")
                    exit()
                except Exception as e:
                    print(f"自动复制文件失败: {e}")
                    exit()
            else:
                print("也未找到 .env.example 文件。请创建一个 .env 文件并设置 AMAP_API_KEY。")
                exit()

        load_dotenv(dotenv_path=env_file)
        self.api_key = os.getenv("AMAP_API_KEY")

        if not self.api_key:
            print("在 .env 文件中未找到或未设置 AMAP_API_KEY。")
            print("请确保 .env 文件中有 'AMAP_API_KEY=your_key_here' 这一行。")
            exit()

        # 缓存和数据目录路径
        self.cache_dir = self.script_dir / "cache"
        self.data_dir = self.script_dir / "data"
        
        # 确保目录存在
        self.cache_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

        # 从JSON文件加载地点
        locations_file = self.cache_dir / "chengdu_locations_gcj02.json"
        with open(locations_file, "r", encoding="utf-8") as f:
            self.locations = json.load(f)

        self.location_names = list(self.locations.keys())
        self.n = len(self.location_names)

        # 缓存机制：点对缓存，减少重复计算
        self.cache_file = self.cache_dir / f"chengdu_travel_time_cache_{self.mode}.json"
        self.path_cache_file = self.cache_dir / f"chengdu_travel_path_cache_{self.mode}.json"
        
        # 先初始化路径缓存，再计算距离矩阵
        self.path_cache = self._load_path_cache()
        self.distance_matrix = self._load_or_calc_travel_time_matrix_optimized()


    def _load_path_cache(self) -> dict:
        """加载路径缓存"""
        if self.path_cache_file.exists():
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
        if self.cache_file.exists():
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
        """使用高德地图API获取两点间的出行时间（分钟）"""
        try:
            # 高德地图API URL
            if self.mode == "driving":
                api_url = f"{self.base_url}/v3/direction/driving"
            elif self.mode == "walking":
                api_url = f"{self.base_url}/v3/direction/walking"
            elif self.mode == "transit":
                api_url = f"{self.base_url}/v3/direction/transit/integrated"
            else:
                api_url = f"{self.base_url}/v3/direction/driving"

            params = {
                "origin": f"{self.locations[origin][0]},{self.locations[origin][1]}",  # 经度,纬度
                "destination": f"{self.locations[destination][0]},{self.locations[destination][1]}",
                "key": self.api_key,
                "strategy": 10,  # 10，返回结果会躲避拥堵，路程较短，尽量缩短时间，与高德地图的默认策略也就是不进行任何勾选一致
                "output": "json"
            }
            
            # 公交模式需要指定城市
            if self.mode == "transit":
                params["city"] = "成都"
                params["cityd"] = "成都"

            response = requests.get(api_url, params=params, timeout=10)
            data = response.json()

            if data.get("status") == "1" and "route" in data:
                # 不同模式下，API返回的结构不同
                if self.mode in ["driving", "walking"]:
                    if "paths" in data["route"] and len(data["route"]["paths"]) > 0:
                        duration = int(data["route"]["paths"][0]["duration"])
                        # 提取真实路径坐标
                        self._extract_and_save_path_amap(origin, destination, data["route"]["paths"][0])
                    else:
                        return self._fallback_distance(origin, destination)
                elif self.mode == "transit":
                    if "transits" in data["route"] and len(data["route"]["transits"]) > 0:
                        duration = int(data["route"]["transits"][0]["duration"])
                        # 公交路线的路径提取较复杂，暂时跳过
                    else:
                        return self._fallback_distance(origin, destination)
                else:
                    duration = 0

                return duration / 60  # 转换为分钟
            else:
                print(f"API错误: {data.get('info', '未知错误')}")
                return self._fallback_distance(origin, destination)

        except Exception as e:
            print(f"获取出行时间失败: {e}")
            return self._fallback_distance(origin, destination)

    def _extract_and_save_path_amap(self, origin: str, destination: str, path_data: dict):
        """提取并保存高德地图API返回的真实路径坐标"""
        try:
            # 确保path_cache已初始化
            if not hasattr(self, 'path_cache'):
                self.path_cache = {}
                
            key = f"{origin}|{destination}"
            path_coords = []
            
            # 高德地图API返回的路径在steps中
            if "steps" in path_data:
                for step in path_data["steps"]:
                    if "polyline" in step:
                        # polyline格式: "116.339646,40.010519;116.340006,40.010546;..."
                        polyline_str = step["polyline"]
                        coords = polyline_str.split(";")
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
        # 转换为WGS84坐标系（从GCJ02转换）
        coords_latlng = [eviltransform.gcj2wgs(lat, lon) for lat, lon in coords_latlng]

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
                # 转换为WGS84坐标系（从GCJ02转换）
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
        output_dir = self.data_dir / "maps"
        output_dir.mkdir(parents=True, exist_ok=True)
        m.save(output_dir / map_filename)
        print(f"已生成路线地图: {output_dir / map_filename} (共使用{total_path_points}个真实路径点)")
        if total_path_points == 0:
            print("⚠️ 未找到真实路径数据，建议重新运行以获取路径信息")

    def generate_route_geojson(self, path: list, algorithm_name: str = "算法", convert_to_wgs84: bool = True) -> dict:
        """生成路线的GeoJSON数据，用于前端展示
        
        Args:
            path: 路径列表
            algorithm_name: 算法名称
            convert_to_wgs84: 是否转换为WGS84坐标系，默认True。False则保持GCJ02坐标系
        """
        
        # 获取景点坐标顺序 - 原始数据格式是 [经度, 纬度] (GCJ02)
        coords = [self.locations[self.location_names[i]] for i in path]
        
        # 处理坐标转换
        final_coords = []
        if convert_to_wgs84:
            # 转换为WGS84坐标系 - eviltransform.gcj2wgs(lat, lon) 返回 (lat, lon)
            for lon_gcj02, lat_gcj02 in coords:
                wgs_lat, wgs_lon = eviltransform.gcj2wgs(lat_gcj02, lon_gcj02)
                final_coords.append([wgs_lat, wgs_lon])  # [纬度, 经度]
            coord_system = "WGS84"
        else:
            # 保持GCJ02坐标系
            for lon_gcj02, lat_gcj02 in coords:
                final_coords.append([lat_gcj02, lon_gcj02])  # [纬度, 经度]
            coord_system = "GCJ02"
        
        # 创建GeoJSON结构
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }
        
        # 添加景点标记 (Points)
        for idx, (final_lat, final_lon) in enumerate(final_coords):
            point_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [final_lon, final_lat]  # GeoJSON格式：[经度, 纬度]
                },
                "properties": {
                    "id": idx,
                    "name": self.location_names[path[idx]],
                    "order": idx + 1,
                    "type": "start" if idx == 0 else "end" if idx == len(final_coords) - 1 else "waypoint",
                    "description": f"第{idx+1}站: {self.location_names[path[idx]]}",
                    "travel_time_from_previous": 0 if idx == 0 else self.distance_matrix[path[idx-1]][path[idx]],
                    "coordinate_system": coord_system
                }
            }
            geojson["features"].append(point_feature)
        
        # 添加路线 (LineStrings)
        for i in range(len(path) - 1):
            origin = self.location_names[path[i]]
            destination = self.location_names[path[i + 1]]
            key = f"{origin}|{destination}"
            
            # 尝试使用真实路径
            if key in self.path_cache and self.path_cache[key]:
                # 使用真实路径坐标 - path_cache中存储的是 [纬度, 经度] (GCJ02)
                real_path_coords = self.path_cache[key]
                
                if convert_to_wgs84:
                    # 转换为WGS84坐标系
                    real_path_converted = [eviltransform.gcj2wgs(lat_gcj02, lon_gcj02) for lat_gcj02, lon_gcj02 in real_path_coords]
                    # 转换为GeoJSON格式 [经度, 纬度]
                    linestring_coords = [[conv_lon, conv_lat] for conv_lat, conv_lon in real_path_converted]
                else:
                    # 保持GCJ02坐标系，转换为GeoJSON格式 [经度, 纬度]
                    linestring_coords = [[lon_gcj02, lat_gcj02] for lat_gcj02, lon_gcj02 in real_path_coords]
                
                route_type = "real_path"
            else:
                # 使用直线连接
                start_coord = final_coords[i]  # [纬度, 经度]
                end_coord = final_coords[i + 1]  # [纬度, 经度]
                # 转换为GeoJSON格式 [经度, 纬度]
                linestring_coords = [[start_coord[1], start_coord[0]], [end_coord[1], end_coord[0]]]
                route_type = "straight_line"
            
            line_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": linestring_coords
                },
                "properties": {
                    "from": origin,
                    "to": destination,
                    "from_order": i + 1,
                    "to_order": i + 2,
                    "travel_time": self.distance_matrix[path[i]][path[i + 1]],
                    "route_type": route_type,
                    "segment_id": i,
                    "description": f"{origin} → {destination} ({self.distance_matrix[path[i]][path[i + 1]]:.1f}分钟)",
                    "coordinate_system": coord_system
                }
            }
            geojson["features"].append(line_feature)
        
        # 添加路线总体信息
        total_time = sum(self.distance_matrix[path[i]][path[i + 1]] for i in range(len(path) - 1))
        geojson["metadata"] = {
            "algorithm": algorithm_name,
            "total_time_minutes": total_time,
            "total_time_hours": total_time / 60,
            "total_locations": len(path),
            "route_summary": [self.location_names[i] for i in path],
            "coordinate_system": coord_system,
            "bounds": self._calculate_bounds(final_coords)
        }
        
        return geojson
    
    def _calculate_bounds(self, coords: list) -> dict:
        """计算坐标边界
        
        Args:
            coords: 坐标列表，格式为 [[纬度, 经度], ...]
        """
        if not coords:
            return {}
        
        lats = [coord[0] for coord in coords]
        lons = [coord[1] for coord in coords]
        
        return {
            "north": max(lats),
            "south": min(lats),
            "east": max(lons),
            "west": min(lons),
            "center": [(max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2]
        }
    
    def save_route_geojson(self, path: list, algorithm_name: str = "算法", filename: str = None, convert_to_wgs84: bool = True):
        """保存路线GeoJSON到data文件夹
        
        Args:
            path: 路径列表
            algorithm_name: 算法名称
            filename: 文件名，如果为None则自动生成
            convert_to_wgs84: 是否转换为WGS84坐标系，默认True。False则保持GCJ02坐标系
        """
        if filename is None:
            coord_suffix = "wgs84" if convert_to_wgs84 else "gcj02"
            safe_algorithm_name = algorithm_name.lower().replace(' ', '_').replace('算法', 'algorithm')
            filename = f"route_{safe_algorithm_name}_{coord_suffix}.geojson"
        
        # 确保文件保存到data文件夹
        if isinstance(filename, str):
            filename = Path(filename)
        
        if not filename.is_absolute() and filename.parts[0] != "data":
            file_path = self.data_dir / filename.name
        else:
            file_path = self.data_dir / filename.name if filename.parts[0] == "data" else filename
        
        geojson_data = self.generate_route_geojson(path, algorithm_name, convert_to_wgs84=convert_to_wgs84)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
        coord_system = "WGS84" if convert_to_wgs84 else "GCJ02"
        print(f"已生成GeoJSON文件: {file_path} ({coord_system}坐标系)")
        return geojson_data
    
    def generate_locations_geojson(self, convert_to_wgs84: bool = True) -> dict:
        """生成所有景点位置的GeoJSON数据
        
        Args:
            convert_to_wgs84: 是否转换为WGS84坐标系，默认True。False则保持GCJ02坐标系
        """
        
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }
        
        # 转换所有景点坐标并生成GeoJSON
        for idx, (name, coords) in enumerate(self.locations.items()):
            lon, lat = coords  # 原始数据格式是 [经度, 纬度] (GCJ02)
            
            if convert_to_wgs84:
                # 转换为WGS84坐标系
                wgs_lat, wgs_lon = eviltransform.gcj2wgs(lat, lon)
                final_coords = [wgs_lon, wgs_lat]  # GeoJSON格式：[经度, 纬度]
                coord_system = "WGS84"
            else:
                # 保持GCJ02坐标系
                final_coords = [lon, lat]  # GeoJSON格式：[经度, 纬度]
                coord_system = "GCJ02"
            
            point_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": final_coords
                },
                "properties": {
                    "id": idx,
                    "name": name,
                    "description": f"{name}",
                    "coordinate_system": coord_system
                }
            }
            geojson["features"].append(point_feature)
        
        # 计算边界
        coords_for_bounds = []
        for name, coords in self.locations.items():
            lon, lat = coords
            if convert_to_wgs84:
                wgs_lat, wgs_lon = eviltransform.gcj2wgs(lat, lon)
                coords_for_bounds.append([wgs_lat, wgs_lon])  # [纬度, 经度]
            else:
                coords_for_bounds.append([lat, lon])  # [纬度, 经度]
        
        geojson["metadata"] = {
            "total_locations": len(self.locations),
            "coordinate_system": coord_system,
            "bounds": self._calculate_bounds(coords_for_bounds),
            "description": f"成都旅游景点位置数据 ({coord_system}坐标系)"
        }
        
        return geojson
    
    def save_locations_geojson(self, filename: str = None, convert_to_wgs84: bool = True):
        """保存景点位置GeoJSON到data文件夹
        
        Args:
            filename: 文件名，如果为None则自动生成
            convert_to_wgs84: 是否转换为WGS84坐标系，默认True。False则保持GCJ02坐标系
        """
        if filename is None:
            coord_suffix = "wgs84" if convert_to_wgs84 else "gcj02"
            filename = f"chengdu_locations_{coord_suffix}.geojson"
        
        # 确保文件保存到data文件夹
        if isinstance(filename, str):
            filename = Path(filename)
        
        if not filename.is_absolute() and filename.parts[0] != "data":
            file_path = self.data_dir / filename.name
        else:
            file_path = self.data_dir / filename.name if filename.parts[0] == "data" else filename
            
        geojson_data = self.generate_locations_geojson(convert_to_wgs84=convert_to_wgs84)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
        coord_system = "WGS84" if convert_to_wgs84 else "GCJ02"
        print(f"已生成景点位置GeoJSON文件: {file_path} ({coord_system}坐标系)")
        return geojson_data


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="成都一日游智能规划系统 - 驾车版")
    parser.add_argument(
        "--generate-geojson", 
        action="store_true", 
        help="生成GeoJSON文件用于前端展示"
    )
    parser.add_argument(
        "--coordinate-system",
        choices=["wgs84", "gcj02", "both"],
        default="wgs84",
        help="GeoJSON坐标系选择: wgs84(默认,国际标准), gcj02(高德/国内标准), both(生成两种)"
    )

    args = parser.parse_args()
    
    print("🚗 成都一日游智能规划系统 - 驾车版")
    print("=" * 50)

    planner = TravelPlanner()
    
    # 生成景点位置GeoJSON（如果启用）
    if args.generate_geojson:
        if args.coordinate_system in ["wgs84", "both"]:
            planner.save_locations_geojson(convert_to_wgs84=True)
        if args.coordinate_system in ["gcj02", "both"]:
            planner.save_locations_geojson(convert_to_wgs84=False)

    # 最近邻算法
    nn_path, nn_time = planner.nearest_neighbor_tsp()
    planner.print_route_details(nn_path, nn_time, "最近邻算法")
    planner.plot_route_on_map(nn_path, map_filename="route_map_nn.html")
    if args.generate_geojson:
        if args.coordinate_system in ["wgs84", "both"]:
            planner.save_route_geojson(nn_path, "nn", convert_to_wgs84=True)
        if args.coordinate_system in ["gcj02", "both"]:
            planner.save_route_geojson(nn_path, "nn", convert_to_wgs84=False)

    # 遗传算法
    ga_path, ga_time = planner.genetic_algorithm_tsp(
        population_size=500, generations=200
    )
    planner.print_route_details(ga_path, ga_time, "遗传算法")
    planner.plot_route_on_map(ga_path, map_filename="route_map_ga.html")
    if args.generate_geojson:
        if args.coordinate_system in ["wgs84", "both"]:
            planner.save_route_geojson(ga_path, "ga", convert_to_wgs84=True)
        if args.coordinate_system in ["gcj02", "both"]:
            planner.save_route_geojson(ga_path, "ga", convert_to_wgs84=False)

    # 蚁群算法
    aco_path, aco_time = planner.ant_colony_optimization_tsp(
        num_ants=500, iterations=100, alpha=1.0, beta=2.0, rho=0.5, q=100
    )
    planner.print_route_details(aco_path, aco_time, "蚁群算法")
    planner.plot_route_on_map(aco_path, map_filename="route_map_aco.html")
    if args.generate_geojson:
        if args.coordinate_system in ["wgs84", "both"]:
            planner.save_route_geojson(aco_path, "ant_colony", convert_to_wgs84=True)
        if args.coordinate_system in ["gcj02", "both"]:
            planner.save_route_geojson(aco_path, "ant_colony", convert_to_wgs84=False)

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
    
    # 提示GeoJSON生成
    if args.generate_geojson:
        coord_systems = {"wgs84": "WGS84", "gcj02": "GCJ02", "both": "WGS84和GCJ02"}
        print(f"\n📄 已生成GeoJSON文件到data文件夹 ({coord_systems[args.coordinate_system]}坐标系)")
    else:
        print(f"\n💡 提示: 使用 --generate-geojson 参数可生成用于前端展示的GeoJSON文件")
        print(f"   基本用法: python travel_planner_driving.py --generate-geojson")
        print(f"   指定坐标系: python travel_planner_driving.py --generate-geojson --coordinate-system wgs84")
        print(f"   坐标系选项: wgs84(国际标准), gcj02(高德/国内标准), both(生成两种)")
        print(f"   测试脚本: python test_coordinate_systems.py")


if __name__ == "__main__":
    main()
