-- 深圳范围自动站实况格点信息表 -> 环境准备与表结构脚本（第1步）
-- 适配 CSV: data/raw/深圳范围自动站实况格点信息表_2920000903510.csv
-- 列头:
-- 格网左下角经度（度）,格网右上角纬度（度）,格网相对Y坐标,格网相对X坐标,格网ID（唯一）,格网左下角纬度（度）,格网右上角经度（度）,格网编码

BEGIN;

-- 1) 建 PostGIS（如未安装会失败，可忽略错误继续）
DO $$ BEGIN
  CREATE EXTENSION IF NOT EXISTS postgis;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'postgis extension create failed: %', SQLERRM;
END $$;

-- 2) 临时落地表（保持 CSV 原字段，类型以 text 为主，便于兼容科学计数法）
-- 序号	字段名称	字段描述
-- 1	RECID	格网ID（唯一）
-- 2	CODE	格网编码
-- 3	XINDEX	格网相对X坐标
-- 4	YINDEX	格网相对Y坐标
-- 5	X1	格网左下角经度（度）
-- 6	Y1	格网左下角纬度（度）
-- 7	X2	格网右上角经度（度）
-- 8	Y2	格网右上角纬度（度）
DROP TABLE IF EXISTS public.sz_weather_grid_cells_stage;
CREATE TABLE public.sz_weather_grid_cells_stage (
  X1    text,  -- 格网左下角经度（度）
  Y2    text,  -- 格网右上角纬度（度）
  YINDEX int,  -- 格网相对Y坐标
  XINDEX int,  -- 格网相对X坐标
  RECID  int,  -- 格网ID（唯一）
  Y1    text,  -- 格网左下角纬度（度）
  X2    text,  -- 格网右上角经度（度）
  CODE   text  -- 格网编码
);

-- 提示：第2步请手动用 psql 将 CSV 导入 stage 表，示例：
-- 注意：实际 CSV 头为中文，字段顺序为 X1,Y2,YINDEX,XINDEX,RECID,Y1,X2,CODE
-- 推荐带列名导入，避免顺序差异：
-- \copy public.sz_weather_grid_cells_stage (X1,Y2,YINDEX,XINDEX,RECID,Y1,X2,CODE)
--       FROM 'data/raw/深圳范围自动站实况格点信息表_2920000903510.csv' CSV HEADER ENCODING 'UTF8';

-- 3) 生成最终几何网格表（空表，后续第3步填充数据）
DROP TABLE IF EXISTS public.sz_weather_grid_cells;
CREATE TABLE public.sz_weather_grid_cells (
  recid     int PRIMARY KEY,
  rel_x     int NOT NULL,
  rel_y     int NOT NULL,
  grid_code text,
  geom      geometry(Polygon, 4326) NOT NULL,
  centroid  geometry(Point,   4326)
);

COMMIT;

-- 接下来，请执行：
--  1) 使用 \copy ... FROM data/深圳范围自动站实况格点信息表_2920000903510.csv 按列顺序导入到 sz_weather_grid_cells_stage
--  2) 运行 sql/load_sz_weather_grid_cells.sql 完成转换、建索引
