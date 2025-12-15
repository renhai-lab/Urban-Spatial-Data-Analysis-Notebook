-- 深圳范围自动站实况格点信息表 -> 数据加载与索引脚本（第3步）
-- 前置：已执行 create_sz_weather_grid_cells.sql 并用 \copy 导入 stage

BEGIN;

-- 从 stage 转换并去重（以 RECID 映射 grid_id 为准）
INSERT INTO public.sz_weather_grid_cells (recid, rel_x, rel_y, grid_code, geom, centroid)
SELECT DISTINCT ON (recid)
  s.recid,
  s.rel_x,
  s.rel_y,
  s.grid_code,
  ST_SetSRID(
    ST_MakePolygon(
      ST_MakeLine(ARRAY[
        ST_MakePoint(ll_lon, ll_lat),
        ST_MakePoint(ur_lon, ll_lat),
        ST_MakePoint(ur_lon, ur_lat),
        ST_MakePoint(ll_lon, ur_lat),
        ST_MakePoint(ll_lon, ll_lat)
      ])
    ), 4326
  ) AS geom,
  ST_SetSRID(ST_MakePoint((ll_lon + ur_lon)/2.0, (ll_lat + ur_lat)/2.0), 4326) AS centroid
FROM (
  SELECT 
  RECID         AS recid,
  XINDEX        AS rel_x,
  YINDEX        AS rel_y,
  CODE          AS grid_code,
    -- 将文本转为数值（兼容科学计数法），遇到异常转为 NULL
  NULLIF(regexp_replace(trim(X1), ',', '', 'g'), '')::double precision AS ll_lon,
  NULLIF(regexp_replace(trim(Y1), ',', '', 'g'), '')::double precision AS ll_lat,
  NULLIF(regexp_replace(trim(X2), ',', '', 'g'), '')::double precision AS ur_lon,
  NULLIF(regexp_replace(trim(Y2), ',', '', 'g'), '')::double precision AS ur_lat
  FROM public.sz_weather_grid_cells_stage
) s
WHERE ll_lon IS NOT NULL AND ll_lat IS NOT NULL AND ur_lon IS NOT NULL AND ur_lat IS NOT NULL
  AND ur_lon > ll_lon AND ur_lat > ll_lat
ON CONFLICT (recid) DO UPDATE
SET rel_x = EXCLUDED.rel_x,
    rel_y = EXCLUDED.rel_y,
    grid_code = EXCLUDED.grid_code,
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid;

-- 索引（若不存在则创建）
CREATE INDEX IF NOT EXISTS idx_sz_weather_grid_cells_geom_gist ON public.sz_weather_grid_cells USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_sz_weather_grid_cells_centroid_gist ON public.sz_weather_grid_cells USING GIST (centroid);
CREATE INDEX IF NOT EXISTS idx_sz_weather_grid_cells_relxy ON public.sz_weather_grid_cells (rel_x, rel_y);

COMMIT;

-- 可选：加载完成后清理 stage 表
-- DROP TABLE IF EXISTS public.sz_weather_grid_cells_stage;
