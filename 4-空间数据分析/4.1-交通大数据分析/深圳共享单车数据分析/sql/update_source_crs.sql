-- 批量标记 source_crs 脚本（psql 参数化版本）
-- 用途：按北京时间的日期范围，将表内记录的 source_crs 批量设置为给定值。
-- 特点：
--   - 支持仅更新 source_crs 为空的行（ONLY_NULL=true），避免覆盖已有标记；
--   - 先 PREVIEW 统计将更新的条数，再执行 UPDATE；
--   - 避免无效写入：对已等于目标值的行不重复更新。
-- 使用方法（psql）：
--   \set TABLE_NAME public.shenzhen_rides
--   \set SOURCE_CRS 'GCJ-02'           -- 也可 'WGS-84' / 'BD-09' / 'UNKNOWN'
--   \set START_DATE '2021-01-01'       -- 北京时间开始日期（含）
--   \set END_DATE   '2021-08-30'       -- 北京时间结束日期（含）
--   \set ONLY_NULL  true               -- 仅更新 source_crs IS NULL 的行
--   \i sql/update_source_crs.sql

\echo ==== 参数 ====
\echo 表: :TABLE_NAME
\echo 目标 source_crs: :SOURCE_CRS
\echo 日期范围(北京时间): :'START_DATE' ~ :'END_DATE'
\echo 仅更新空值(ONLY_NULL): :ONLY_NULL

BEGIN;

-- 预览：将会更新的行数
SELECT COUNT(*) AS will_update
FROM :TABLE_NAME t
WHERE ((t.start_time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN :'START_DATE' AND :'END_DATE')
  AND (
        (:ONLY_NULL::boolean IS TRUE  AND t.source_crs IS NULL)
     OR (:ONLY_NULL::boolean IS FALSE)
      )
  AND (t.source_crs IS DISTINCT FROM :'SOURCE_CRS');

-- 如需再预览一些样本，可取消注释：
-- SELECT id, start_time, end_time, source_crs
-- FROM :TABLE_NAME t
-- WHERE ((t.start_time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN :'START_DATE' AND :'END_DATE')
--   AND ((:ONLY_NULL::boolean IS TRUE AND t.source_crs IS NULL) OR (:ONLY_NULL::boolean IS FALSE))
--   AND (t.source_crs IS DISTINCT FROM :'SOURCE_CRS')
-- ORDER BY id
-- LIMIT 20;

-- 执行更新（仅将不等于目标值的行更改为目标值）
UPDATE :TABLE_NAME AS t
SET source_crs = :'SOURCE_CRS'
WHERE ((t.start_time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN :'START_DATE' AND :'END_DATE')
  AND (
        (:ONLY_NULL::boolean IS TRUE  AND t.source_crs IS NULL)
     OR (:ONLY_NULL::boolean IS FALSE)
      )
  AND (t.source_crs IS DISTINCT FROM :'SOURCE_CRS');

-- 汇总报告
WITH s AS (
  SELECT :'SOURCE_CRS'::text AS crs,
         :'START_DATE'::date AS d1,
         :'END_DATE'::date   AS d2
)
SELECT s.crs, s.d1, s.d2,
       COUNT(*) AS updated_rows
FROM :TABLE_NAME t, s
WHERE ((t.start_time AT TIME ZONE 'Asia/Shanghai')::date BETWEEN s.d1 AND s.d2)
  AND t.source_crs = s.crs;

COMMIT;

-- 其它常见过滤（按需替换到上述 WHERE）：
-- 1) 仅标记已有 WGS84 坐标的行
--    AND t.start_geom_wgs84 IS NOT NULL
--    AND t.end_geom_wgs84   IS NOT NULL
-- 2) 仅标记有原始坐标但尚未生成 WGS84 的行
--    AND (t.start_geom_raw IS NOT NULL OR t.end_geom_raw IS NOT NULL)
--    AND (t.start_geom_wgs84 IS NULL OR t.end_geom_wgs84 IS NULL)