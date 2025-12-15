# 数据获取和导出管道优化报告

## 优化内容

### 1. 配置修复
- 修复了 `config.py` 中数据类型问题：
  - `EXPORT_MAX_WORKERS`: str → int (4)
  - `EXPORT_BATCH_SIZE`: str → int (50000)  
  - `DB_BATCH_SIZE`: str → int (10000)
  - `ENABLE_PERFORMANCE_STATS`: str → bool (True)

### 2. 数据获取并发优化 (`fetcher.py`)

#### 原有问题：
- 天与天之间串行处理：获取数据 → 入库 → 导出 → 下一天
- `DAYS_CONCURRENCY` 配置无效

#### 优化方案：
- 实现真正的多天并发获取数据
- 支持分批处理，避免过多并发导致资源争用
- 改进错误处理，防止单个失败影响整体进度
- 并发获取 + 立即导出的流水线模式

#### 关键改进：
```python
# 分批并发处理日期
batch_size = min(settings.DAYS_CONCURRENCY, len(dates))
date_batches = [dates[i:i + batch_size] for i in range(0, len(dates), batch_size)]

# 并发获取数据
fetch_tasks = []
for target_date in date_batch:
    task = fetch_and_store_day(session, target_date, profile, conn_str, settings.MAX_CONCURRENCY)
    fetch_tasks.append(task)

results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
```

### 3. 导出性能优化 (`export_share.py`)

#### 原有问题：
- 每天数据完全加载到内存（250万条记录占用大量内存）
- 坐标系和格式串行处理
- `EXPORT_MAX_WORKERS` 配置类型错误且未充分利用

#### 优化方案：
- **流式处理**：按批次读取数据，避免内存溢出
- **并发导出**：不同坐标系和格式并发处理
- **内存管理**：及时释放内存，使用 `gc.collect()`
- **连接管理**：使用上下文管理器确保连接正确释放

#### 关键改进：
```python
# 流式处理大数据
while True:
    rows = cur.fetchmany(batch_size)
    if not rows:
        break
    # 处理数据...
    del rows
    gc.collect()

# 并发处理不同格式
max_workers = min(len(coord_sets) * len(formats), settings.EXPORT_MAX_WORKERS)
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    # 为每种格式创建并发任务
    futures.append((executor.submit(_export_csv_stream, ...), ...))
```

## 性能提升预期

### 数据获取方面：
- **并发度**：从 1 天/次 提升到最多 `DAYS_CONCURRENCY` 天/次 (默认100)
- **资源利用**：网络IO和数据库写入可以并行进行
- **容错性**：单天失败不影响其他天的处理

### 导出方面：
- **内存使用**：从一次性加载全天数据改为流式处理
- **并发度**：格式和坐标系可以并发导出（最多 2×2=4 个并发任务/天）
- **处理速度**：理论上可提升 2-4 倍（取决于数据量和系统资源）

## 配置建议

### 根据系统资源调整：

```python
# config.py 中的关键配置
DAYS_CONCURRENCY: int = 10  # 建议 5-20，取决于API限制和系统资源
MAX_CONCURRENCY: int = 30   # 单天内页面并发数
EXPORT_MAX_WORKERS: int = 4 # 导出并发数，建议 2-8
EXPORT_BATCH_SIZE: int = 50000  # 批处理大小，内存不足可减小
```

### 内存较小的系统：
- `DAYS_CONCURRENCY = 5`
- `EXPORT_MAX_WORKERS = 2`  
- `EXPORT_BATCH_SIZE = 20000`

### 高配置系统：
- `DAYS_CONCURRENCY = 20`
- `EXPORT_MAX_WORKERS = 8`
- `EXPORT_BATCH_SIZE = 100000`

## 使用方式

### 1. 数据获取（已优化）
```bash
uv run python -m src.data_pipeline.fetcher --auto-export --export-coord-sets raw,wgs84 --export-formats csv,geojson
```

### 2. 单独导出（已优化）
```bash
uv run python -m src.data_pipeline.export_share --start 20210101 --end 20210102 --workers 4
```

### 3. 测试优化效果
```bash
uv run python test_optimized_pipeline.py
```

## 监控建议

1. **观察并发数**：通过日志查看实际并发处理的天数
2. **内存使用**：监控导出过程中的内存占用
3. **处理速度**：对比优化前后的记录/秒处理速度
4. **错误率**：确保并发不会增加API请求失败率

## 注意事项

1. **API限制**：增加并发可能触发API限流，需要观察和调整
2. **数据库连接**：确保数据库支持足够的并发连接
3. **磁盘空间**：并发导出会临时占用更多磁盘空间
4. **系统资源**：根据CPU和内存情况调整并发参数
