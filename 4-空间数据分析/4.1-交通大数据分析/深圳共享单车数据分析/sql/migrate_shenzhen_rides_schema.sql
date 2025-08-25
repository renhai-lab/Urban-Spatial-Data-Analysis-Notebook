-- 一次性迁移脚本：将旧版 shenzhen_rides 表演进为新版列设计（raw + wgs84 + source_crs）
-- 注意：请在维护窗口执行，先备份再运行。

BEGIN;

-- 1) 新增列（若不存在）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='shenzhen_rides' AND column_name='start_geom_raw'
  ) THEN
    ALTER TABLE public.shenzhen_rides ADD COLUMN start_geom_raw geometry(Point,4326);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='shenzhen_rides' AND column_name='end_geom_raw'
  ) THEN
    ALTER TABLE public.shenzhen_rides ADD COLUMN end_geom_raw geometry(Point,4326);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='shenzhen_rides' AND column_name='source_crs'
  ) THEN
    ALTER TABLE public.shenzhen_rides ADD COLUMN source_crs TEXT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='shenzhen_rides' AND column_name='start_geom_wgs84'
  ) THEN
    ALTER TABLE public.shenzhen_rides ADD COLUMN start_geom_wgs84 geometry(Point,4326);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='shenzhen_rides' AND column_name='end_geom_wgs84'
  ) THEN
    ALTER TABLE public.shenzhen_rides ADD COLUMN end_geom_wgs84 geometry(Point,4326);
  END IF;
END$$;

-- 2) 旧列处理（老表有 start_geom/end_geom，类型 geography(Point,4326)）
--    默认推荐：仅改名 + 必要时 geography->geometry 改型（零拷贝 + 一次重写），无需回填脚本。
--    如需保持旧列并复制到新列，可使用分批回填脚本（可选，现已移除，按需恢复）。


-- 3) 索引（若不存在）
CREATE INDEX IF NOT EXISTS idx_start_geom_raw ON public.shenzhen_rides USING GIST (start_geom_raw);
CREATE INDEX IF NOT EXISTS idx_end_geom_raw   ON public.shenzhen_rides USING GIST (end_geom_raw);
CREATE INDEX IF NOT EXISTS idx_start_geom_w84 ON public.shenzhen_rides USING GIST (start_geom_wgs84);
CREATE INDEX IF NOT EXISTS idx_end_geom_w84   ON public.shenzhen_rides USING GIST (end_geom_wgs84);
CREATE INDEX IF NOT EXISTS idx_source_crs     ON public.shenzhen_rides (source_crs);

-- 4) 可选：移除旧索引，避免混淆（若仍需兼容可保留）
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='idx_start_geom') THEN
    DROP INDEX public.idx_start_geom;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='idx_end_geom') THEN
    DROP INDEX public.idx_end_geom;
  END IF;
END$$;

-- 5) 可选：保留旧列以便回溯；如需删除请取消以下注释
-- ALTER TABLE public.shenzhen_rides DROP COLUMN start_geom;
-- ALTER TABLE public.shenzhen_rides DROP COLUMN end_geom;

COMMIT;

-- 运行方法（psql）：
-- \i sql/migrate_shenzhen_rides_schema.sql