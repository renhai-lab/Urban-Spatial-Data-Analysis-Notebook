"""
深圳共享单车数据研究——获取数据（简化版，适合初学者）
数据名称：共享单车企业每日订单表
更新日期：2021-12-09    上架日期：2021-12-09
更新频率：不定期
数据量：244,638,540条
数据容量：1,957,108,320
开放方式：实名认证
开放数源单位：深圳市交通运输局
数据简介：共享单车企业每日订单表

说明：
- 本脚本不再依赖 MongoDB，数据将直接保存为 CSV 文件；
- 时间字段保留接口返回的原始本地时间字符串（不做时区转换）；
- 按页追加写入 CSV，首页写入表头，其余页不写入表头。
"""

import time
from pathlib import Path

import pandas as pd
import requests


def _build_output_csv(start_date: str, end_date: str) -> Path:
    """根据日期范围生成输出 CSV 路径，位于项目 data 目录。"""
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_dir = project_root / "data" / "raw"
    csv_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"bike_orders_{start_date}_{end_date}.csv"
        if start_date != end_date
        else f"bike_orders_{start_date}.csv"
    )
    return csv_dir / filename


# 主函数
if __name__ == "__main__":
    # 环境变量和初始化
    app_key = "41373f2b1ef34a56b0aa379aab68d0d5"  # TODO: 替换为你从深圳开放数据平台申请的 app_key
    page_num = 1
    rows = 4000
    # 日期范围 可以选择你要爬取的范围
    startDate = "20210101"  # TODO: 替换为你要爬取的开始日期，格式 YYYYMMDD
    endDate = "20210101"  # TODO: 替换为你要爬取的结束日期，格式 YYYYMMDD
    url = "https://opendata.sz.gov.cn/api/29200_00403627/1/service.xhtml"
    # 请求头 不加请求会被拒绝
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    # 输出 CSV
    output_csv = _build_output_csv(startDate, endDate)
    print(f"数据将保存到: {output_csv}")

    # 数据请求和处理循环
    while True:
        params = {
            "appKey": app_key,
            "page": page_num,
            "rows": rows,
            "startDate": startDate,
            "endDate": endDate,
        }
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"请求错误，状态码：{response.status_code}")
            break

        items = response.json().get("data", [])
        if not items:
            print("没有更多数据或数据为空，结束。")
            break

        # 将本页数据追加写入 CSV
        df = pd.DataFrame(items)
        write_header = (page_num == 1) and (not output_csv.exists())
        df.to_csv(
            output_csv, mode="a", index=False, encoding="utf-8-sig", header=write_header
        )
        print(f"已写入第 {page_num} 页，共 {len(df)} 条。")

        # 判断是否继续
        if len(items) < rows:
            print("最后一页已写完。")
            break
        else:
            page_num += 1
            # 轻微休眠，避免请求过快
            time.sleep(0.5)
