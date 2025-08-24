-- 视图：几何 + 气象观测的便捷联接

BEGIN;

-- 全量联接视图（按 recid_int ↔ recid）
CREATE OR REPLACE VIEW public.v_sz_weather_grid AS
SELECT 
  c.recid,
  c.rel_x,
  c.rel_y,
  c.grid_code,
  c.geom,
  c.centroid,
  w.recid,
  w.recid_int,
  w.gridid,
  w.ddatetime,
  w.forecasttime,
  w.plevel,
  w.t,
  w.wspd,
  w.wdir,
  w.slp,
  w.rhsfc,
  w.rain01h,
  w.rain03h,
  w.rain06h,
  w.rain24h,
  w.v,
  w.tracerr01h,
  w.maxtofday,
  w.rain02h,
  w.wd3smaxdf,
  w.wd3smaxdd,
  w.crttime,
  w.keyid
FROM public.sz_weather_grid_cells c
JOIN public.sz_weather_grid w
  ON w.recid_int = c.recid;

-- 每个网格最新一条（以 ddatetime 优先，否则按 crttime），可用于快速绘图/分析
CREATE OR REPLACE VIEW public.v_sz_weather_grid_latest AS
WITH ranked AS (
  SELECT w.*, 
         COALESCE(w.ddatetime, w.crttime) AS ts,
         ROW_NUMBER() OVER (PARTITION BY w.recid_int ORDER BY COALESCE(w.ddatetime, w.crttime) DESC, w.id DESC) AS rn
  FROM public.sz_weather_grid w
)
SELECT 
  c.recid,
  c.rel_x,
  c.rel_y,
  c.grid_code,
  c.geom,
  c.centroid,
  r.recid,
  r.recid_int,
  r.gridid,
  r.ddatetime,
  r.forecasttime,
  r.plevel,
  r.t,
  r.wspd,
  r.wdir,
  r.slp,
  r.rhsfc,
  r.rain01h,
  r.rain03h,
  r.rain06h,
  r.rain24h,
  r.v,
  r.tracerr01h,
  r.maxtofday,
  r.rain02h,
  r.wd3smaxdf,
  r.wd3smaxdd,
  r.crttime,
  r.keyid
FROM ranked r
JOIN public.sz_weather_grid_cells c
  ON r.recid_int = c.recid
WHERE r.rn = 1;

COMMIT;
