"""
将表中的 start_geom_raw / end_geom_raw 流式（低内存）转换为 WGS84，写入 *_wgs84(geometry,4326) 列，一次跑完整库。

特性：
- 键集分页（id > last_id ORDER BY id LIMIT batch），每批转换后提交；
- 仅填充空的 *_wgs84，不覆盖已有值；
- 使用本地 GCJ-02 -> WGS84（eviltransform）；source_crs 不改，后续人工标记；

用法示例：
    # 全库，一次跑完，单批 10000
    uv run python -m scr.data_pipline.backfill_wgs84_from_raw --batch 10000 --dry-run false

    # 指定日期范围（北京时间）
    uv run python -m scr.data_pipline.backfill_wgs84_from_raw --start 20210101 --end 20210830 --batch 5000 --dry-run false --log-every 1 --scan-all-ids true

    # 断点续跑（从 last_id 继续）
    uv run python -m scr.data_pipline.backfill_wgs84_from_raw --resume-id 55860000 --batch 10000 --dry-run false --scan-all-ids true
"""

from __future__ import annotations

import argparse
from datetime import datetime, date
from typing import Optional, Iterable, List, Tuple
import time

import psycopg
from psycopg.rows import dict_row
from psycopg import sql

from .config import settings
from .coords import gcj02_to_wgs84


def parse_day(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%Y%m%d").date()


def _iter_batches(
    conn: psycopg.Connection,
    table: str,
    batch: int,
    start: Optional[date],
    end: Optional[date],
    scan_all_ids: bool,
    resume_id: int = 0,
) -> Iterable[List[dict]]:
    """流式获取批次数据：每批返回行字典列表。"""
    date_filter_sql = ""
    params: list = []
    if start and end:
        date_filter_sql = (
            "AND ((start_time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN %s AND %s)"
        )
        params.extend([start, end])
    elif start:
        date_filter_sql = "AND ((start_time AT TIME ZONE 'Asia/Shanghai')::date >= %s)"
        params.append(start)
    elif end:
        date_filter_sql = "AND ((start_time AT TIME ZONE 'Asia/Shanghai')::date <= %s)"
        params.append(end)

    last_id = int(resume_id) if resume_id else 0
    while True:
        where_need_sql = (
            ""
            if scan_all_ids
            else "AND (start_geom_wgs84 IS NULL OR end_geom_wgs84 IS NULL)"
        )
        q = sql.SQL(
            """
            SELECT id,
                   CASE WHEN start_geom_raw IS NOT NULL THEN ST_X(start_geom_raw) END AS s_lng,
                   CASE WHEN start_geom_raw IS NOT NULL THEN ST_Y(start_geom_raw) END AS s_lat,
                   CASE WHEN end_geom_raw   IS NOT NULL THEN ST_X(end_geom_raw)   END AS e_lng,
                   CASE WHEN end_geom_raw   IS NOT NULL THEN ST_Y(end_geom_raw)   END AS e_lat,
                   (start_geom_wgs84 IS NULL) AS need_start,
                   (end_geom_wgs84   IS NULL) AS need_end
            FROM {table}
            WHERE id > %s
              AND (start_geom_raw IS NOT NULL OR end_geom_raw IS NOT NULL)
              {where_need}
              {date_filter}
            ORDER BY id
            LIMIT %s
            """
        ).format(
            table=sql.Identifier(table),
            date_filter=sql.SQL(date_filter_sql),
            where_need=sql.SQL(where_need_sql),
        )
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q, (last_id, *params, batch))
            rows = cur.fetchall()
        if not rows:
            break
        yield rows
        last_id = rows[-1]["id"]


def backfill(
    batch: int,
    start: Optional[date],
    end: Optional[date],
    dry_run: bool,
    log_every: int,
    scan_all_ids: bool,
    resume_id: int = 0,
    update_chunk: int = 2000,
    fast_commit: bool = False,
    commit_every_chunks: int = 1,
) -> int:
    conn_str = settings.get_conn_str()
    updated = 0
    with psycopg.connect(conn_str) as conn:
        # 尝试减少锁等待导致的“卡住”感知
        with conn.cursor() as cset:
            cset.execute("SET application_name = 'backfill_wgs84_from_raw';")
            cset.execute("SET lock_timeout = '2s';")
            if fast_commit and not dry_run:
                # 提升吞吐（风险：主从延迟或极端断电风险，按需开启）
                cset.execute("SET synchronous_commit = off;")
        table = settings.TABLE_NAME

        def _bulk_update(
            rows_params: List[
                Tuple[
                    int,
                    Optional[float],
                    Optional[float],
                    Optional[float],
                    Optional[float],
                ]
            ],
        ):
            """使用单条 UPDATE ... FROM (VALUES ...) 批量更新，rows_params: [(id, sx, sy, ex, ey), ...]"""
            if not rows_params:
                return
            values_nodes = [
                sql.SQL(
                    "(%s::bigint,%s::double precision,%s::double precision,%s::double precision,%s::double precision)"
                )
            ] * len(rows_params)
            placeholders = sql.SQL(",").join(values_nodes)
            flat_params: List[Optional[float]] = []
            for rid, sx, sy, ex, ey in rows_params:
                flat_params.extend([rid, sx, sy, ex, ey])

            q = sql.SQL(
                """
                UPDATE {table} AS t
                SET start_geom_wgs84 = CASE
                        WHEN v.sx IS NULL OR v.sy IS NULL THEN t.start_geom_wgs84
                        ELSE COALESCE(t.start_geom_wgs84, ST_SetSRID(ST_MakePoint(v.sx, v.sy), 4326))
                    END,
                    end_geom_wgs84 = CASE
                        WHEN v.ex IS NULL OR v.ey IS NULL THEN t.end_geom_wgs84
                        ELSE COALESCE(t.end_geom_wgs84, ST_SetSRID(ST_MakePoint(v.ex, v.ey), 4326))
                    END
                FROM (VALUES {values}) AS v(id, sx, sy, ex, ey)
                WHERE t.id = v.id
                """
            ).format(table=sql.Identifier(table), values=placeholders)
            with conn.cursor() as cu:
                cu.execute(q, flat_params)

        t0 = time.time()
        batch_idx = 0
        for rows in _iter_batches(
            conn, table, batch, start, end, scan_all_ids, resume_id=resume_id
        ):
            batch_idx += 1
            if dry_run:
                updated += len(rows)
                if batch_idx % max(1, log_every) == 0:
                    print(
                        f"[dry-run] 扫描第 {batch_idx} 批，共 {len(rows)} 行；累计 {updated} 行；last_id={rows[-1]['id']}"
                    )
                continue

            # 先在 Python 侧完成 GCJ->WGS 转换，再进行批量更新
            to_update: List[
                Tuple[
                    int,
                    Optional[float],
                    Optional[float],
                    Optional[float],
                    Optional[float],
                ]
            ] = []
            for r in rows:
                sid = r["id"]
                need_start = bool(r.get("need_start"))
                need_end = bool(r.get("need_end"))
                s_lng = r.get("s_lng")
                s_lat = r.get("s_lat")
                e_lng = r.get("e_lng")
                e_lat = r.get("e_lat")

                sx, sy = (None, None)
                ex, ey = (None, None)
                if need_start and s_lng is not None and s_lat is not None:
                    wx, wy = gcj02_to_wgs84(float(s_lng), float(s_lat))
                    sx, sy = wx, wy
                if need_end and e_lng is not None and e_lat is not None:
                    wx, wy = gcj02_to_wgs84(float(e_lng), float(e_lat))
                    ex, ey = wx, wy

                # 仅当至少一个目标坐标可写入时才进入更新列表
                if (sx is not None and sy is not None) or (
                    ex is not None and ey is not None
                ):
                    to_update.append((sid, sx, sy, ex, ey))

            # 大批量写入拆成较小 SQL 分块，减少往返与锁持有时间
            commit_every = max(1, int(commit_every_chunks))
            pending = 0
            for i in range(0, len(to_update), max(1, update_chunk)):
                chunk = to_update[i : i + update_chunk]
                if not chunk:
                    continue
                _bulk_update(chunk)
                pending += 1
                if pending % commit_every == 0:
                    conn.commit()
                    pending = 0
            if pending:
                conn.commit()
            updated += len(rows)

            if batch_idx % max(1, log_every) == 0:
                elapsed = time.time() - t0
                rate = updated / elapsed if elapsed > 0 else 0.0
                print(
                    f"已提交第 {batch_idx} 批，更新 {len(rows)} 行；累计 {updated} 行，用时 {elapsed:.1f}s（~{rate:.0f} 行/秒）；last_id={rows[-1]['id']}"
                )

    return updated


def main():
    ap = argparse.ArgumentParser(
        description="从 raw 坐标批量生成 *_wgs84 列（GCJ-02 -> WGS84）"
    )
    ap.add_argument(
        "--batch", type=int, default=10000, help="单批处理条数（避免内存过大）"
    )
    ap.add_argument(
        "--start", type=str, default=None, help="开始日期 YYYYMMDD（北京时）"
    )
    ap.add_argument("--end", type=str, default=None, help="结束日期 YYYYMMDD（北京时）")
    ap.add_argument(
        "--dry-run", type=str, default="true", help="仅统计数量，不写入（true/false）"
    )
    ap.add_argument(
        "--scan-all-ids",
        type=str,
        default="false",
        help="为避免稀疏 NULL 过滤导致首批极慢，按 id 连续分页扫描（true/false）",
    )
    ap.add_argument(
        "--log-every", type=int, default=1, help="每多少批输出一次进度（默认每批）"
    )
    ap.add_argument(
        "--resume-id",
        type=int,
        default=0,
        help="从给定 id 开始继续扫描（WHERE id > resume_id）",
    )
    ap.add_argument(
        "--update-chunk",
        type=int,
        default=2000,
        help="单条 UPDATE 内部 VALUES 的最大行数（避免参数过多，默认 2000）",
    )
    ap.add_argument(
        "--fast-commit",
        type=str,
        default="false",
        help="设置 synchronous_commit=off，加速提交（存在极端断电风险）（true/false）",
    )
    ap.add_argument(
        "--commit-every-chunks",
        type=int,
        default=1,
        help="每处理多少个 update 子块提交一次事务（默认每块提交一次）",
    )
    args = ap.parse_args()

    start = parse_day(args.start)
    end = parse_day(args.end)
    dry_run = str(args.dry_run).lower() in {"1", "true", "yes"}

    scan_all_ids = str(args.scan_all_ids).lower() in {"1", "true", "yes"}
    fast_commit = str(args.fast_commit).lower() in {"1", "true", "yes"}
    n = backfill(
        args.batch,
        start,
        end,
        dry_run,
        args.log_every,
        scan_all_ids,
        resume_id=args.resume_id,
        update_chunk=args.update_chunk,
        fast_commit=fast_commit,
        commit_every_chunks=args.commit_every_chunks,
    )
    print(("将要更新" if dry_run else "已更新"), n, "行")


if __name__ == "__main__":
    main()
