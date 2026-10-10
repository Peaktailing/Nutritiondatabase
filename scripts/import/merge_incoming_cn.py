#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 OCR 抽取的《中国食物成分表 标准版 第6版》合并进主库。

背景与决策依据（实测，勿改）:
  两个独立来源在 1,615 条共同 food_code 上做了逐字段比对:
    宏量营养素基本一致: 水分 99.4% / 蛋白 98.3% / 脂肪 97.0%
    微量营养素大面积偏离: 维E 25.4% / 胆固醇 63.9% / 铁 73.6% / 锌 75.4%
  第三方裁判(中国食物成分表第6版公认值):
    猪肝 Fe 权威=22.6  现有库=23.2 ✅   OCR包=1.93  ❌(差 12 倍,且大量字段漏抽为 NULL)
  OCR 包另有两类系统性问题:
    1) 漏抽: 猪肝/猪肉/苹果等的铁、钙大量为 NULL
    2) 越界: 10.5% 的铁值 >30mg/100g(现有库仅 2.56%),如「小麦粉(特制)」Fe=105mg 不可能

→ 决策: **不用 OCR 主表覆盖现有主表**。只并入两类增量:
     A. OCR 独有的 195 条食物 → 新表 china_food_ocr(带 source/check_grade 血缘)
     B. 三个全新维度表 → china_amino_acid / china_fatty_acid / china_sample_desc

用法: python3 merge_incoming_cn.py            # 执行合并
      python3 merge_incoming_cn.py --dry-run  # 只预览不入���
"""
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/import/merge_incoming_cn.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))
import sqlite3, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_DB = os.path.join(BASE, "incoming_cn", "数据库", "中国食物成分表.db")
DB = os.path.join(BASE, "nutrition.db")
DRY = "--dry-run" in sys.argv


def main():
    if not os.path.exists(IN_DB):
        sys.exit(f"找不到 {IN_DB}")
    src = sqlite3.connect(IN_DB)
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA synchronous=OFF")

    # 现有主表已有哪些编码，避免重复追加
    have = {r[0] for r in cur.execute(
        "select foodCode from china_food_composition")}
    print(f"现有主表 china_food_composition: {len(have):,} 条")

    # ------------------------------------------------ A. OCR 独有主表记录
    new_rows = []
    for r in src.execute("select * from food_nutrition"):
        d = dict(zip([x[1] for x in src.execute(
            "PRAGMA table_info(food_nutrition)")], r))
        if d["food_code"] in have:
            continue
        if not (d.get("food_name") or "").strip():
            continue          # 空名记录无意义，直接丢弃
        new_rows.append((
            d["food_code"], (d.get("category") or "").strip() or None,
            d["food_name"].strip(), d.get("edible_pct"), d.get("water_g"),
            d.get("energy_kcal"), d.get("energy_kj"), d.get("protein_g"),
            d.get("fat_g"), d.get("carb_g"), d.get("fiber_g"),
            d.get("cholesterol_mg"), d.get("ash_g"), d.get("vit_a_ug"),
            d.get("beta_carotene_ug"), d.get("thiamin_mg"),
            d.get("riboflavin_mg"), d.get("niacin_mg"), d.get("vit_c_mg"),
            d.get("vit_e_mg"), d.get("calcium_mg"), d.get("phosphorus_mg"),
            d.get("potassium_mg"), d.get("sodium_mg"), d.get("magnesium_mg"),
            d.get("iron_mg"), d.get("zinc_mg"), d.get("selenium_ug"),
            d.get("copper_mg"), d.get("manganese_mg"), d.get("iodine_ug"),
            d.get("check_grade"), d.get("macro_sum"),
        ))
    print(f"OCR 独有且具名的新增食物: {len(new_rows):,} 条")

    # ------------------------------------------------ B. 三个新维度表
    SPEC = {
        "china_amino_acid": ("""food_code TEXT, food_name TEXT, water_g REAL, protein_g REAL,
            ile_mg REAL, leu_mg REAL, lys_mg REAL, met_mg REAL, cys_mg REAL, saa_mg REAL,
            phe_mg REAL, tyr_mg REAL, aaa_mg REAL, thr_mg REAL, trp_mg REAL, val_mg REAL,
            his_mg REAL, arg_mg REAL, ala_mg REAL, asp_mg REAL, glu_mg REAL, gly_mg REAL,
            pro_mg REAL, ser_mg REAL""",
            """select food_code, food_name, water_g, protein_g,
                    ile_mg, leu_mg, lys_mg, met_mg, cys_mg, saa_mg,
                    phe_mg, tyr_mg, aaa_mg, thr_mg, trp_mg, val_mg,
                    his_mg, arg_mg, ala_mg, asp_mg, glu_mg, gly_mg,
                    pro_mg, ser_mg from amino_acid""", 24),
        "china_fatty_acid": ("""food_code TEXT, food_name TEXT, fat_g REAL, fa_total_g REAL,
            sfa_g REAL, mufa_g REAL, pufa_g REAL, fa_unk_g REAL,
            c40_g REAL, c60_g REAL, c80_g REAL, c100_g REAL, c120_g REAL, c140_g REAL,
            c150_g REAL, c160_g REAL, c170_g REAL, c180_g REAL, c200_g REAL, c220_g REAL,
            c240_g REAL, c141_g REAL, c161_g REAL, c181_g REAL, c201_g REAL, c221_g REAL,
            c182_g REAL, c183_g REAL, c204_g REAL, c205_g REAL, c226_g REAL""",
            """select food_code, food_name, fat_g, fa_total_g, sfa_g, mufa_g,
                    pufa_g, fa_unk_g, c40_g, c60_g, c80_g, c100_g, c120_g,
                    c140_g, c150_g, c160_g, c170_g, c180_g, c200_g, c220_g,
                    c240_g, c141_g, c161_g, c181_g, c201_g, c221_g, c182_g,
                    c183_g, c204_g, c205_g, c226_g from fatty_acid""", 31),
        "china_sample_desc": ("""food_code TEXT, food_name TEXT, food_desc TEXT,
            sample_process TEXT, data_source TEXT, sampling_date TEXT,
            sampling_place TEXT, origin TEXT""",
            """select food_code, food_name, food_desc, sample_process,
                    data_source, sampling_date, sampling_place, origin
             from sample_desc""", 8),
    }

    if DRY:
        print("\n[dry-run] 未写入任何数据。将执行的动作：")
        print(f"  新建表 china_food_ocr            +{len(new_rows):,} 行")
        for t, (_, q, _) in SPEC.items():
            n = src.execute(f"select count(*) from ({' '.join(q.split())})").fetchone()[0]
            print(f"  新建表 {t:<24} +{n:,} 行")
        return

    cur.execute("BEGIN")
    # A
    cur.execute("DROP TABLE IF EXISTS china_food_ocr")
    cur.execute("""CREATE TABLE china_food_ocr (
        foodCode TEXT PRIMARY KEY, category TEXT, foodName TEXT,
        edible REAL, water REAL, energyKCal REAL, energyKJ REAL,
        protein REAL, fat REAL, CHO REAL, dietaryFiber REAL,
        cholesterol REAL, ash REAL, vitaminA REAL, carotene REAL,
        thiamin REAL, riboflavin REAL, niacin REAL, vitaminC REAL,
        vitaminETotal REAL, Ca REAL, P REAL, K REAL, Na REAL, Mg REAL,
        Fe REAL, Zn REAL, Se REAL, Cu REAL, Mn REAL, iodine REAL,
        check_grade TEXT, macro_sum REAL, source TEXT)""")
    cur.executemany(
        "INSERT INTO china_food_ocr VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
        "?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [r + ("ocr_scan_v6",) for r in new_rows])

    # B
    for t, (ddl, q, _) in SPEC.items():
        cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute(f"CREATE TABLE {t} ({ddl})")
        rows = src.execute(" ".join(q.split())).fetchall()
        cur.executemany(
            f"INSERT INTO {t} VALUES ({','.join('?' * len(rows[0]))})", rows)

    # china_food_ocr 沿用主表列名 foodCode，其余三表用 food_code
    for t in ("china_amino_acid", "china_fatty_acid", "china_sample_desc"):
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_code ON {t}(food_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_china_food_ocr_code "
                "ON china_food_ocr(foodCode)")
    cur.execute("COMMIT")

    print("\n合并完成：")
    for t in ("china_food_ocr", "china_amino_acid", "china_fatty_acid",
              "china_sample_desc"):
        n = cur.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"  {t:<22} {n:>7,} 行")
    # 主表未被改动，验证一下
    n_main = cur.execute("select count(*) from china_food_composition").fetchone()[0]
    print(f"\n  现有主表仍为 {n_main:,} 行（未被覆盖 —— 现有库数值质量优于 OCR）")
    con.close()


if __name__ == "__main__":
    main()
