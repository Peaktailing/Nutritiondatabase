#!/usr/bin/env python3
"""
导出整合层成品库为可分发的 SQL 文本。

只导出并排归一化层 + 各来源核心表，**不含 USDA 原始镜像**——
原始数据任何人可从 USDA 官网重新下载，放进仓库只会让体积涨 20 倍。

用法：
    python3 export_release.py [--db nutrition.db] [--out data/nutrition_data.sql.gz]
"""
import argparse
import gzip
import os
import sqlite3
import time

# 整合成果表：并排层 + 8 来源核心表 + 必要的 USDA 辅助表
KEEP = [
    # 并排归一化层（核心）
    'norm_nutrient', 'norm_canon_cat', 'norm_food', 'norm_value',
    # 中国
    'china_food_composition', 'china_dri_2023', 'china_food_gi',
    'china_amino_acid', 'china_fatty_acid', 'china_sample_desc', 'china_food_ocr',
    # 中国两版合并结果（并排层 CN 的真实数据源）+ 决策日志
    'china_food_merged', 'china_food_synthetic', 'china_merge_map',
    # 国际
    'ciqual_food', 'uk_cofid_food', 'jp_mext_food', 'jp_mext_amino_food',
    'fao_wafct_food', 'id_tkpi_food', 'asean_fcd_2014',
    # USDA 中有价值的衍生表（小）
    'foundation_food', 'sr_legacy_food', 'food_category', 'nutrient',
    'measure_unit', 'fndds_derivation', 'food_calorie_conversion_factor',
    'food_protein_conversion_factor', 'retention_factor', 'food_nutrient_conversion_factor',
]


def dump(con, tables, out_path, gzipped=True):
    tmp = out_path + '.tmp'
    opener = gzip.open if gzipped else open
    total = 0
    t0 = time.time()
    with opener(tmp, 'wt', encoding='utf-8') as f:
        f.write("-- 营养数据整合库 · 数据导出\n")
        f.write(f"-- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-- 还原: sqlite3 nutrition.db < nutrition_data.sql\n")
        f.write("-- 内容: 并排归一化层 + 8 来源核心表 + 中国两版合并表（不含 USDA 原始镜像，可从官网重下）\n\n")
        f.write("PRAGMA foreign_keys=OFF;\nBEGIN;\n")

        for n in tables:
            row = con.execute(
                "select sql from sqlite_master where name=? and sql is not null", (n,)
            ).fetchone()
            if row and row[0].strip().upper().startswith('CREATE TABLE'):
                f.write(row[0].rstrip() + ";\n")

        for n in tables:
            cur = con.execute(f"select * from '{n}'")
            if not cur.description:
                continue
            cnt, batch = 0, []
            for row in cur:
                esc = []
                for v in row:
                    if v is None:
                        esc.append('NULL')
                    elif isinstance(v, (int, float)):
                        esc.append(repr(v))
                    else:
                        esc.append("'" + str(v).replace("'", "''") + "'")
                batch.append(f"INSERT INTO '{n}' VALUES ({','.join(esc)});\n")
                cnt += 1
                if len(batch) >= 20000:
                    f.writelines(batch)
                    batch = []
            f.writelines(batch)
            total += cnt
            print(f"  {n:<34}{cnt:>9,} 行")

        f.write("COMMIT;\n-- 校验\n")
        for n in tables:
            f.write(f"SELECT '{n}' AS tbl, count(*) AS rows FROM '{n}';\n")

    os.replace(tmp, out_path)
    return total, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='nutrition.db')
    ap.add_argument('--out', default='data/nutrition_data.sql.gz')
    ap.add_argument('--plain', action='store_true', help='输出未压缩 .sql')
    a = ap.parse_args()

    if not os.path.exists(a.db):
        raise SystemExit(f"找不到数据库 {a.db}")

    # 曾经在这里做过 `out = a.out[:-3]` 来剥掉 .gz 后缀——那是个真 bug：
    # 剥掉后 gzipped 判断必然为 False，于是 --out foo.gz 实际写出未压缩的
    # foo.sql（103 MB），而仓库里那个 foo.gz 就永远停在旧内容，表面看
    # 「导出成功」实则交付的是陈旧文件。压缩与否只看 --plain 开关。
    out = a.out
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    print(f"导出 {a.db} -> {out}\n")
    con = sqlite3.connect(a.db)
    total, dt = dump(con, KEEP, out, gzipped=not a.plain)
    con.close()

    sz = os.path.getsize(out)
    print(f"\n合计 {total:,} 行 / {sz/1048576:.1f} MB / {dt:.1f}s")


if __name__ == '__main__':
    main()