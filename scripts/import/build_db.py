#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 USDA FoodData Central 完整 CSV 整合包导入 SQLite，建成可查询的整合库。

特性：
  - 通用导入：自动发现解压目录中所有 *.csv，按文件名建表
  - 类型推断：采样前若干行，把每列推断为 INTEGER / REAL / TEXT
  - 索引：对常见主键/外键列自动建索引，加速联表查询
  - 整合视图：
      v_foods          统一食品视图（含分类名）
      v_food_nutrients 食品-营养素-数值 的人读视图
用法：
  python3 build_db.py [解压目录] [输出db路径]
默认：解压目录=/workspace/fdc/extract，db=/workspace/fdc/fooddata_central.db
"""
import sqlite3, csv, os, glob, sys, time

SAMPLE_ROWS = 8000
BATCH = 50000
KEY_COLS = {
    'id', 'fdc_id', 'nutrient_id', 'food_id', 'food_nutrient_id',
    'food_category_id', 'food_portion_id', 'unit_id', 'food_attribute_id',
    'food_attribute_type_id', 'retention_factor_id', 'src_id', 'derivation_id',
    'input_food_id', 'sub_sample_food_id', 'sample_food_id', 'measure_unit_id',
    'food_nutrient_source_id', 'food_nutrient_derivation_id', 'nutrient_nbr',
    'food_class', 'data_type',
}


def is_int(v):
    try:
        int(v)
        return True
    except (ValueError, TypeError):
        return False


def is_float(v):
    try:
        f = float(v)
        return f == f and f not in (float('inf'), float('-inf'))
    except (ValueError, TypeError):
        return False


def infer_types(path, columns):
    types = {c: 'TEXT' for c in columns}
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        next(r, None)
        n = 0
        for row in r:
            if not row:
                continue
            for i, c in enumerate(columns):
                if i >= len(row):
                    continue
                v = row[i].strip()
                if v == '':
                    continue
                s = types[c]
                if s == 'TEXT':
                    if is_int(v):
                        types[c] = 'INTEGER'
                    elif is_float(v):
                        types[c] = 'REAL'
                elif s == 'INTEGER':
                    if not is_int(v):
                        types[c] = 'REAL' if is_float(v) else 'TEXT'
                elif s == 'REAL':
                    if not is_float(v):
                        types[c] = 'TEXT'
            n += 1
            if n >= SAMPLE_ROWS:
                break
    return types


def convert(v, t):
    v = v.strip()
    if v == '':
        return None
    if t == 'INTEGER':
        try:
            return int(v)
        except ValueError:
            return v
    if t == 'REAL':
        try:
            return float(v)
        except ValueError:
            return v
    return v


def get_cols(cur, tbl):
    cur.execute(f'PRAGMA table_info("{tbl}")')
    return [r[1] for r in cur.fetchall()]


def table_exists(cur, tbl):
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (tbl,),
    )
    return cur.fetchone() is not None


def build_views(cur):
    # ---- v_foods：统一食品视图 ----
    if table_exists(cur, 'food'):
        cf = get_cols(cur, 'food')
        sel = ['f."fdc_id"', 'f."data_type"', 'f."description"']
        if 'food_category_id' in cf and table_exists(cur, 'food_category'):
            sel.append('f."food_category_id"')
            cfc = get_cols(cur, 'food_category')
            if 'description' in cfc:
                sel.append('fc."description" AS food_category')
                from_clause = 'food f LEFT JOIN food_category fc ON fc."id" = f."food_category_id"'
            else:
                from_clause = 'food f'
        else:
            from_clause = 'food f'
        if 'publication_date' in cf:
            sel.append('f."publication_date"')
        cur.execute(
            f'CREATE VIEW IF NOT EXISTS v_foods AS SELECT {", ".join(sel)} FROM {from_clause}'
        )

    # ---- v_food_nutrients：人读的营养素视图 ----
    if table_exists(cur, 'food_nutrient') and table_exists(cur, 'nutrient'):
        cn = get_cols(cur, 'food_nutrient')
        nn = get_cols(cur, 'nutrient')
        sel2 = ['fn."fdc_id"']
        if 'id' in cn:
            sel2.append('fn."id" AS food_nutrient_id')
        if 'nutrient_id' in cn:
            sel2.append('fn."nutrient_id"')
        if 'amount' in cn:
            sel2.append('fn."amount"')
        sel2.append('n."name" AS nutrient_name')
        if 'unit_name' in nn:
            sel2.append('n."unit_name"')
        join = 'food_nutrient fn JOIN nutrient n ON n."id" = fn."nutrient_id"'
        cur.execute(
            f'CREATE VIEW IF NOT EXISTS v_food_nutrients AS SELECT {", ".join(sel2)} FROM {join}'
        )


def main():
    extract_dir = sys.argv[1] if len(sys.argv) > 1 else "/workspace/fdc/extract"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/workspace/fdc/fooddata_central.db"

    csvs = sorted(glob.glob(os.path.join(extract_dir, "**", "*.csv"), recursive=True))
    if not csvs:
        print(f"未在 {extract_dir} 找到任何 CSV 文件，请先解压下载的 zip。")
        sys.exit(1)
    print(f"发现 {len(csvs)} 个 CSV 文件，开始导入到 {db_path}")

    # 追加模式：不删除已有库，这样 USDA 表可以并入已含中国数据的同一个整合库
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous=OFF")
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.execute("PRAGMA cache_size=-2000000")

    total_rows_all = 0
    for path in csvs:
        tbl = os.path.splitext(os.path.basename(path))[0]
        tbl = tbl.replace('-', '_').replace(' ', '_').replace('.', '_')
        with open(path, newline='', encoding='utf-8') as f:
            r = csv.reader(f)
            header = next(r)
            cols = [c.strip().strip('"') for c in header]
            types = infer_types(path, cols)
            coldefs = ", ".join(f'"{c}" {types[c]}' for c in cols)
            cur.execute(f'DROP TABLE IF EXISTS "{tbl}"')
            cur.execute(f'CREATE TABLE "{tbl}" ({coldefs})')
            collist = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join("?" for _ in cols)
            insert = f'INSERT INTO "{tbl}" ({collist}) VALUES ({placeholders})'

            batch = []
            total = 0
            t0 = time.time()
            for row in r:
                if not row:
                    continue
                vals = [
                    convert(row[i].strip() if i < len(row) else '', types[c])
                    for i, c in enumerate(cols)
                ]
                batch.append(vals)
                total += 1
                if len(batch) >= BATCH:
                    cur.executemany(insert, batch)
                    batch = []
            if batch:
                cur.executemany(insert, batch)
            conn.commit()
            dt = time.time() - t0
            print(f"  {tbl}: {total} 行, 用时 {dt:.1f}s  ({total/max(dt,0.01):.0f} 行/秒)")
            total_rows_all += total

            # 索引
            for kc in cols:
                if kc in KEY_COLS:
                    try:
                        cur.execute(
                            f'CREATE INDEX IF NOT EXISTS "idx_{tbl}_{kc}" ON "{tbl}" ("{kc}")'
                        )
                    except sqlite3.Error as e:
                        print(f"   索引警告 {kc}: {e}")
            conn.commit()

    build_views(cur)
    conn.commit()

    # 汇总
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"\n共导入 {len(tables)} 张表，{total_rows_all} 行数据。")
    print("视图：v_foods, v_food_nutrients")
    conn.close()
    print("DONE ->", db_path)


if __name__ == "__main__":
    main()
