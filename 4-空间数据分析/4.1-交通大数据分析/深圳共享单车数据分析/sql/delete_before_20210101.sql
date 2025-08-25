-- 删除 2021-01-01 之前的数据（按北京时间判断）
-- 安全流程：先归档到新表，再分批删除，最后 VACUUM ANALYZE 原表。
-- 使用方法（psql）：
--   psql -h <host> -p <port> -U <user> -d <db> -f sql/delete_before_20210101.sql

-- 说明：
--  - 以 (start_time AT TIME ZONE 'Asia/Shanghai')::date < '2021-01-01' 为判定条件，
--    保证按北京时间筛选；如需按 UTC，请改为 start_time < '2021-01-01'::timestamptz
--  - 脚本默认归档到 public.shenzhen_rides_archive_before_20210101
--  - 分批删除避免长事务与 WAL 暴涨；可修改 batch_size

BEGIN;

-- 1) 归档要删除的数据（若表很大，执行时间视数据量而定）
CREATE TABLE IF NOT EXISTS public.shenzhen_rides_archive_before_20210101 AS
SELECT *
FROM public.shenzhen_rides
WHERE (start_time AT TIME ZONE 'Asia/Shanghai')::date < '2021-01-01';

-- 可选：为归档表创建索引（加速后续查询/验证），视需要取消注释并调整索引列
-- CREATE INDEX ON public.shenzhen_rides_archive_before_20210101 (start_time);
-- CREATE INDEX ON public.shenzhen_rides_archive_before_20210101 (user_id);

-- 2) 分批删除原表中对应数据（使用 ctid 分批，兼容 PostgreSQL）
DO $$
DECLARE
  batch_size int := 10000;  -- 每批删除行数，可根据 I/O 与 WAL 考量调整
  deleted int := 0;
BEGIN
  LOOP
    DELETE FROM public.shenzhen_rides
    WHERE ctid IN (
      SELECT ctid FROM public.shenzhen_rides
      WHERE (start_time AT TIME ZONE 'Asia/Shanghai')::date < '2021-01-01'
      LIMIT batch_size
    );

    GET DIAGNOSTICS deleted = ROW_COUNT;
    RAISE NOTICE '删除批量 % 行', deleted;
    EXIT WHEN deleted = 0;
    -- 短暂休息以缓解 IO 峰值（可调整或移除）
    PERFORM pg_sleep(0.1);
  END LOOP;
END$$;

-- 3) 维护：回收空间并更新统计信息
VACUUM (VERBOSE, ANALYZE) public.shenzhen_rides;

COMMIT;

-- 附注：
-- - 如果你希望在删除前先确认归档正确无误，可以先运行到 CREATE TABLE 部分，验证归档表，
--   然后注释掉分批删除部分再手动运行删除步骤。
-- - 若想保守：不要创建归档表，而是先导出（COPY）到文件系统，再执行删除。
