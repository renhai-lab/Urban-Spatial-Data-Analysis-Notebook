-- 为气象格点观测表添加整数型键、索引与外键（可选）
-- 目的：与 public.sz_weather_grid_cells(grid_id) 高效匹配，保持两表分离

BEGIN;

-- 1) 生成列：将 recid 转为整数，非数字行产生 NULL（不报错）
DO $$ BEGIN
  ALTER TABLE public.sz_weather_grid
    ADD COLUMN recid_int INT GENERATED ALWAYS AS (
      NULLIF(regexp_replace(COALESCE(recid, ''), '[^0-9]', '', 'g'), '')::INT
    ) STORED;
EXCEPTION WHEN duplicate_column THEN
  RAISE NOTICE 'column recid_int already exists, skip';
END $$;

-- 2) 索引（便于按网格与时间查询）
CREATE INDEX IF NOT EXISTS idx_wg_recid_int ON public.sz_weather_grid (recid_int);
CREATE INDEX IF NOT EXISTS idx_wg_crttime ON public.sz_weather_grid (crttime);
CREATE INDEX IF NOT EXISTS idx_wg_ddatetime ON public.sz_weather_grid (ddatetime);

-- 3) 外键（可选）。若历史数据存在脏键，可先 NOT VALID，后续再 VALIDATE。
DO $$ BEGIN
  ALTER TABLE public.sz_weather_grid
    ADD CONSTRAINT fk_wg_cells
    FOREIGN KEY (recid_int) REFERENCES public.sz_weather_grid_cells(recid)
    NOT VALID;
EXCEPTION WHEN duplicate_object THEN
  RAISE NOTICE 'constraint fk_wg_cells already exists, skip';
END $$;

COMMIT;

-- 可选：校验外键
-- ALTER TABLE public.sz_weather_grid VALIDATE CONSTRAINT fk_wg_cells;
