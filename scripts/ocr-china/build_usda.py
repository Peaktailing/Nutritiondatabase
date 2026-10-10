"""USDA 兼容格式转换。

USDA FoodData Central(branded / sr_legacy)的通用字段命名与单位约定:
  - 标识: fdc_id / ndb_number(数字) + description(英文名)
  - 能量: Energy(kcal)、Energy(kJ)
  - 宏量(g/100g): Protein、Total lipid (fat)、Carbohydrate, by difference、
                   Fiber, total dietary、Total Sugars、Ash、Water
  - 脂肪细分(g): Fatty acids, total saturated / monounsaturated / polyunsaturated
  - 矿物质(mg 或 µg): Calcium, Iron(Fe), Magnesium, Phosphorus(P),
                     Potassium(K), Sodium(Na), Zinc(Zn)
                     Copper(Cu, µg), Manganese(Mn, mg), Selenium(Se, µg)
  - 维生素: Vitamin A, RAE(µg)、Carotene, beta(µg)、Retinol(µg)、
            Thiamin(mg)、Riboflavin(mg)、Niacin(mg)、Vitamin C(mg)、
            Vitamin E (alpha-tocopherol)(mg)、Vitamin B-6(mg)、
            Vitamin B-12(µg)、Folate(µg)、Vitamin K(µg)
  - 胆固醇: Cholesterol(mg)
  - 氨基酸(g/100g): USDA 常用 g,原表是 mg → 需 ÷1000
  - 脂肪酸(g/100g): 与原表一致

本脚本:复制主库 → 生成一份字段改名、单位换算后的 USDA 兼容版,
并保留 cn_* 原始字段以便回溯。
"""
import json, os, shutil, sqlite3, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from build_db import classify                       # noqa: E402

SRC = os.path.join(BASE, "中国食物成分表.db")
DST = os.path.join(BASE, "中国食物成分表_USDA兼容版.db")

# USDA 命名映射: 原列名 -> (USDA 列名, 换算系数, 说明)
MAP = {
    # 标识与描述
    "food_code":      ("ndb_number", 1.0, "食物编码(6位)"),
    "food_name":      ("description_cn", 1.0, "中文名称"),
    "category":       ("food_category_cn", 1.0, "中文分类"),
    # 近似成分
    "water_g":        ("Water", 1.0, "g/100g"),
    "energy_kcal":    ("Energy (kcal)", 1.0, "kcal"),
    "energy_kj":      ("Energy (kJ)", 1.0, "kJ"),
    "protein_g":      ("Protein", 1.0, "g/100g"),
    "fat_g":          ("Total lipid (fat)", 1.0, "g/100g"),
    "carb_g":         ("Carbohydrate, by difference", 1.0, "g/100g"),
    "fiber_g":        ("Fiber, total dietary", 1.0, "g/100g"),
    "ash_g":          ("Ash", 1.0, "g/100g"),
    # 脂肪细分
    "fat_sat_g":      ("Fatty acids, total saturated", 1.0, "g/100g"),
    "fat_mono_g":     ("Fatty acids, total monounsaturated", 1.0, "g/100g"),
    "fat_poly_g":     ("Fatty acids, total polyunsaturated", 1.0, "g/100g"),
    "cholesterol_mg": ("Cholesterol", 1.0, "mg"),
    # 矿物质
    "calcium_mg":     ("Calcium, Ca", 1.0, "mg"),
    "iron_mg":        ("Iron, Fe", 1.0, "mg"),
    "magnesium_mg":   ("Magnesium, Mg", 1.0, "mg"),
    "phosphorus_mg":  ("Phosphorus, P", 1.0, "mg"),
    "potassium_mg":   ("Potassium, K", 1.0, "mg"),
    "sodium_mg":      ("Sodium, Na", 1.0, "mg"),
    "zinc_mg":        ("Zinc, Zn", 1.0, "mg"),
    "copper_mg":      ("Copper, Cu", 1.0, "mg"),
    "manganese_mg":   ("Manganese, Mn", 1.0, "mg"),
    "selenium_ug":    ("Selenium, Se", 1.0, "µg"),
    # 维生素
    "vit_a_ug":         ("Vitamin A, RAE", 1.0, "µg"),
    "beta_carotene_ug": ("Carotene, beta", 1.0, "µg"),
    "thiamin_mg":       ("Thiamin", 1.0, "mg"),
    "riboflavin_mg":    ("Riboflavin", 1.0, "mg"),
    "niacin_mg":        ("Niacin", 1.0, "mg"),
    "vit_c_mg":         ("Vitamin C, total ascorbic acid", 1.0, "mg"),
    "vit_e_mg":         ("Vitamin E (alpha-tocopherol)", 1.0, "mg"),
    "vit_e_te_mg":      ("Vitamin E, added", 1.0, "mg"),
}

# 氨基酸:原表 mg/100g → USDA 惯用 g/100g
AA_MAP = {
    "ile_mg": "Isoleucine", "leu_mg": "Leucine", "lys_mg": "Lysine",
    "met_mg": "Methionine", "cys_mg": "Cystine",
    "phe_mg": "Phenylalanine", "tyr_mg": "Tyrosine",
    "thr_mg": "Threonine", "trp_mg": "Tryptophan", "val_mg": "Valine",
    "his_mg": "Histidine", "arg_mg": "Arginine", "ala_mg": "Alanine",
    "asp_mg": "Aspartic acid", "glu_mg": "Glutamic acid",
    "gly_mg": "Glycine", "pro_mg": "Proline", "ser_mg": "Serine",
    "saa_mg": "Sulfur AA (SAA, total)", "aaa_mg": "Aromatic AA (AAA, total)",
}

# 脂肪酸:原表已是 g/100g,直接改名
FA_MAP = {
    "fat_g":     "Total lipid (fat)",
    "fa_total_g": "Fatty acids, total",
    "sfa_g":     "Fatty acids, total saturated",
    "mufa_g":    "Fatty acids, total monounsaturated",
    "pufa_g":    "Fatty acids, total polyunsaturated",
    "c40_g": "4:0", "c60_g": "6:0", "c80_g": "8:0", "c100_g": "10:0",
    "c120_g": "12:0", "c140_g": "14:0", "c150_g": "15:0", "c160_g": "16:0",
    "c170_g": "17:0", "c180_g": "18:0", "c200_g": "20:0", "c220_g": "22:0",
    "c240_g": "24:0", "c141_g": "14:1", "c161_g": "16:1", "c181_g": "18:1",
    "c201_g": "20:1", "c221_g": "22:1", "c182_g": "18:2", "c183_g": "18:3",
    "c204_g": "20:4", "c205_g": "20:5 (EPA)", "c226_g": "22:6 (DHA)",
}


def q(name):
    """SQLite 标识符加引号(含空格/逗号/冒号的列名必须引起来)。"""
    return '"' + name.replace('"', '""') + '"'


def copy_and_convert():
    if os.path.exists(DST):
        os.remove(DST)
    shutil.copy2(SRC, DST)
    con = sqlite3.connect(DST)
    cur = con.cursor()

    def has(t, c):
        return cur.execute(
            f"SELECT COUNT(*) FROM pragma_table_info('{t}') "
            f"WHERE name=?", (c,)).fetchone()[0] > 0

    # —— 1) 主表:新增 USDA 命名列 ——
    added = 0
    for src, (dst, k, _note) in MAP.items():
        if not has("food_nutrition", src):
            continue
        if has("food_nutrition", dst):
            continue
        cur.execute(f'ALTER TABLE food_nutrition ADD COLUMN {q(dst)} REAL')
        cur.execute(
            f"UPDATE food_nutrition SET {q(dst)} = "
            f'(CASE WHEN "{src}" IS NULL THEN NULL ELSE "{src}" * {k} END)')
        added += 1

    # —— 2) 氨基酸表:mg → g ——
    aa_added = 0
    for src, dst in AA_MAP.items():
        if not has("amino_acid", src) or has("amino_acid", dst):
            continue
        cur.execute(f'ALTER TABLE amino_acid ADD COLUMN {q(dst)} REAL')
        cur.execute(
            f"UPDATE amino_acid SET {q(dst)} = "
            f'(CASE WHEN "{src}" IS NULL THEN NULL ELSE "{src}" / 1000.0 END)')
        aa_added += 1

    # —— 3) 脂肪酸表:直接改名 ——
    fa_added = 0
    for src, dst in FA_MAP.items():
        if not has("fatty_acid", src) or has("fatty_acid", dst):
            continue
        cur.execute(f'ALTER TABLE fatty_acid ADD COLUMN {q(dst)} REAL')
        cur.execute(f'UPDATE fatty_acid SET {q(dst)} = "{src}"')
        fa_added += 1

    # —— 4) 建立跨表联查视图(主表 + 氨基酸 + 脂肪酸 + 样品描述)——
    nut_cols = ", ".join(f'n.{q(d)}' for _, (d, _, _) in MAP.items()
                         if has("food_nutrition", d))
    aa_cols = ", ".join(
        f'a.{q(d)} AS "aa_{d}"' for d in AA_MAP.values()
        if has("amino_acid", d))
    fa_cols = ", ".join(
        f'f.{q(d)} AS "fa_{d}"' for d in FA_MAP.values()
        if has("fatty_acid", d))
    cur.execute("DROP VIEW IF EXISTS v_full")
    cur.execute(f"""
      CREATE VIEW v_full AS
      SELECT n.food_code AS ndb_number, n.food_name, n.category,
             {nut_cols},
             {aa_cols},
             {fa_cols},
             s.food_desc, s.sample_process, s.data_source,
             s.sampling_date, s.sampling_place, s.origin,
             n.check_grade
      FROM food_nutrition n
      LEFT JOIN amino_acid a ON a.food_code = n.food_code
      LEFT JOIN fatty_acid f ON f.food_code = n.food_code
      LEFT JOIN sample_desc s ON s.food_code = n.food_code
    """)

    # —— 5) 元数据 ——
    cur.execute("""CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY,
                                                   v TEXT)""")
    for k, v in {
        "format": "USDA FoodData Central 兼容命名",
        "base": "中国食物成分表 标准版 第6版",
        "unit": "每100g可食部",
        "aa_unit": "氨基酸已由 mg/100g 换算为 g/100g",
        "join_key": "food_code (= ndb_number)",
        "note": "USDA 命名列与 cn_ 原始列并存,原始列名保持不变",
    }.items():
        cur.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))

    con.commit()
    n = cur.execute("SELECT COUNT(*) FROM food_nutrition").fetchone()[0]
    print(f"USDA 兼容库: {DST}")
    print(f"  主表 {n} 行,新增 USDA 列 {added} 个")
    print(f"  氨基酸表新增 {aa_added} 个(g/100g)")
    print(f"  脂肪酸表新增 {fa_added} 个")
    con.close()


if __name__ == "__main__":
    copy_and_convert()
