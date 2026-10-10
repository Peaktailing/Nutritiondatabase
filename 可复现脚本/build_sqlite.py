"""生成完整 SQLite 数据库:主营养表 + 三张附录表。

表结构:
  food_nutrition  主营养表(1810 条)
  food_amino_acid 氨基酸(856 条)
  food_fatty_acid 脂肪酸(972 条)
  food_sample_desc 样品描述(1084 条)
  meta            元数据
全部以 food_code 关联。
"""
import csv, json, os, sqlite3, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from build_db import classify                      # noqa: E402
from postfix4 import macro_sum                     # noqa: E402
from build_appendix import OUT_COLS, FILE_NAME     # noqa: E402

DB = os.path.join(BASE, "中国食物成分表.db")

# 主表:内部键 -> (列名, 类型, 中文注释, 单位)
MAIN_COLS = [
    ("food_code", "TEXT", "食物编码", ""),
    ("food_name", "TEXT", "食物名称", ""),
    ("category",  "TEXT", "食物分类", ""),
    ("edible_pct", "REAL", "食部", "%"),
    ("water_g", "REAL", "水分", "g"),
    ("energy_kcal", "REAL", "能量_kcal", "kcal"),
    ("energy_kj", "REAL", "能量_kJ", "kJ"),
    ("protein_g", "REAL", "蛋白质", "g"),
    ("fat_g", "REAL", "脂肪", "g"),
    ("fat_sat_g", "REAL", "饱和脂肪", "g"),
    ("fat_mono_g", "REAL", "单不饱和脂肪", "g"),
    ("fat_poly_g", "REAL", "多不饱和脂肪", "g"),
    ("carb_g", "REAL", "碳水化合物", "g"),
    ("fiber_g", "REAL", "膳食纤维", "g"),
    ("cholesterol_mg", "REAL", "胆固醇", "mg"),
    ("ash_g", "REAL", "灰分", "g"),
    ("vit_a_ug", "REAL", "维生素A", "μgRAE"),
    ("beta_carotene_ug", "REAL", "β-胡萝卜素", "μg"),
    ("thiamin_mg", "REAL", "维生素B1", "mg"),
    ("riboflavin_mg", "REAL", "维生素B2", "mg"),
    ("niacin_mg", "REAL", "烟酸", "mg"),
    ("vit_c_mg", "REAL", "维生素C", "mg"),
    ("vit_e_mg", "REAL", "维生素E", "mg"),
    ("vit_e_te_mg", "REAL", "α-生育酚当量", "mg"),
    ("calcium_mg", "REAL", "钙", "mg"),
    ("phosphorus_mg", "REAL", "磷", "mg"),
    ("potassium_mg", "REAL", "钾", "mg"),
    ("sodium_mg", "REAL", "钠", "mg"),
    ("magnesium_mg", "REAL", "镁", "mg"),
    ("iron_mg", "REAL", "铁", "mg"),
    ("zinc_mg", "REAL", "锌", "mg"),
    ("selenium_ug", "REAL", "硒", "μg"),
    ("copper_mg", "REAL", "铜", "mg"),
    ("manganese_mg", "REAL", "锰", "mg"),
    ("iodine_ug", "REAL", "碘", "μg"),
]

TBL_COMMENT = {
    "food_nutrition": "主营养成分表(每100g可食部)",
    "food_amino_acid": "食物氨基酸含量(mg/100g可食部)",
    "food_fatty_acid": "食物脂肪酸含量(g/100g可食部)",
    "food_sample_desc": "食物样品描述(采样信息)",
}

# 附录表:sql 列名 -> 类型
def app_cols(table):
    out = [("food_code", "TEXT"), ("food_name", "TEXT")]
    for key, zh, u in OUT_COLS[table]:
        if key in ("food_code", "food_name"):
            continue
        t = "TEXT" if table == "sample_desc" and key in (
            "food_desc", "sample_process", "data_source",
            "sampling_date", "sampling_place", "origin") else "REAL"
        out.append((key, t))
    return out


def main():
    if os.path.exists(DB):
        os.remove(DB)
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # ——— 主表 ———
    cols_sql = ", ".join(f"{c} {t}" for c, t, _, _ in MAIN_COLS)
    cur.execute(f"CREATE TABLE food_nutrition ({cols_sql}, "
                f"n_fields INTEGER, macro_sum REAL, quality_score REAL, "
                f"check_grade TEXT, data_source TEXT)")
    cur.execute("CREATE INDEX idx_nut_code ON food_nutrition(food_code)")

    with open(os.path.join(BASE, "checked_v3.json"), encoding="utf-8") as f:
        recs = json.load(f)

    names = [c for c, *_ in MAIN_COLS]
    for r in recs:
        vals = []
        for c, *_ in MAIN_COLS:
            if c == "category":
                vals.append(classify(r))
            else:
                vals.append(r.get(c))
        vals += [r.get("_n_fields"), round(macro_sum(r), 1),
                 r.get("_quality_score"), r.get("_grade"),
                 "中国食物成分表 标准版 第6版"]
        cur.execute(
            f"INSERT INTO food_nutrition ({','.join(names)},n_fields,"
            f"macro_sum,quality_score,check_grade,data_source) "
            f"VALUES ({','.join('?'*len(vals))})", vals)

    # ——— 附录表 ———
    counts = {}
    for table, fname in FILE_NAME.items():
        cols = app_cols(table)
        cs = ", ".join(f"{c} {t}" for c, t in cols)
        cur.execute(f"CREATE TABLE {table} ({cs})")
        cur.execute(f"CREATE INDEX idx_{table}_code ON {table}(food_code)")
        p = os.path.join(BASE, fname)
        n = 0
        if os.path.exists(p):
            # CSV 使用中文表头,需把内部列名映射成中文表头去取值
            key2zh = {}
            for key, zh, u in OUT_COLS[table]:
                key2zh[key] = zh + (f"({u})" if u else "")
            with open(p, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    vals = []
                    for c, t in cols:
                        # 先按内部列名取,再按中文表头取
                        v = row.get(c)
                        if v is None:
                            v = row.get(key2zh.get(c, ""))
                        if t == "REAL":
                            try:
                                v = float(v) if v not in (None, "") else None
                            except ValueError:
                                v = None
                        vals.append(v)
                    cur.execute(
                        f"INSERT INTO {table} ({','.join(c for c, _ in cols)}) "
                        f"VALUES ({','.join('?'*len(vals))})", vals)
                    n += 1
        counts[table] = n

    # ——— 元数据 ———
    cur.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    meta = {
        "title": "中国食物成分表 标准版 第6版",
        "source": "两册扫描版 OCR 抽取(第一册植物性 387页 / 第二册动物性 454页)",
        "unit": "每100g可食部",
        "record_nutrition": str(len(recs)),
        "record_amino_acid": str(counts.get("food_amino_acid", 0)),
        "record_fatty_acid": str(counts.get("food_fatty_acid", 0)),
        "record_sample_desc": str(counts.get("food_sample_desc", 0)),
        "grade_a": str(sum(1 for r in recs if r.get("_grade", "").startswith("A"))),
        "energy_note": "Atwater: 蛋白17 脂肪37 碳水17 纤维8 (kJ/g)",
    }
    for k, v in meta.items():
        cur.execute("INSERT INTO meta VALUES (?,?)", (k, v))

    con.commit()
    print(f"数据库: {DB}")
    for t in cur.execute("SELECT name FROM sqlite_master "
                         "WHERE type='table'").fetchall():
        n = cur.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"  {t[0]:20s} {n:6d} 行")
    con.close()


if __name__ == "__main__":
    main()
