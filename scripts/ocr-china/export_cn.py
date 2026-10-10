"""导出中文表头 CSV —— 支持分册或合并输出。"""
import argparse, csv, json, os, re, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from build_db import symbol_columns                    # noqa: E402
from postfix4 import macro_sum                         # noqa: E402

# 列 → (键, 中文表头, 单位)
COLMAP = [
    ("food_code",        "食物编码", ""),
    ("food_name",        "食物名称", ""),
    ("_category",        "食物分类", ""),
    ("edible_pct",       "食部", "%"),
    ("water_g",          "水分", "g"),
    ("energy_kcal",      "能量", "kcal"),
    ("energy_kj",        "能量", "kJ"),
    ("protein_g",        "蛋白质", "g"),
    ("fat_g",            "脂肪", "g"),
    ("fat_sat_g",        "饱和脂肪", "g"),
    ("fat_mono_g",       "单不饱和脂肪", "g"),
    ("fat_poly_g",       "多不饱和脂肪", "g"),
    ("carb_g",           "碳水化合物", "g"),
    ("fiber_g",          "膳食纤维", "g"),
    ("cholesterol_mg",   "胆固醇", "mg"),
    ("ash_g",            "灰分", "g"),
    ("vit_a_ug",         "维生素A", "μgRAE"),
    ("beta_carotene_ug", "β-胡萝卜素", "μg"),
    ("thiamin_mg",       "维生素B1(硫胺素)", "mg"),
    ("riboflavin_mg",    "维生素B2(核黄素)", "mg"),
    ("niacin_mg",        "烟酸", "mg"),
    ("vit_c_mg",         "维生素C", "mg"),
    ("vit_e_mg",         "维生素E", "mg"),
    ("vit_e_te_mg",      "α-生育酚当量", "mg"),
    ("calcium_mg",       "钙", "mg"),
    ("phosphorus_mg",    "磷", "mg"),
    ("potassium_mg",     "钾", "mg"),
    ("sodium_mg",        "钠", "mg"),
    ("magnesium_mg",     "镁", "mg"),
    ("iron_mg",          "铁", "mg"),
    ("zinc_mg",          "锌", "mg"),
    ("selenium_ug",      "硒", "μg"),
    ("copper_mg",        "铜", "mg"),
    ("manganese_mg",     "锰", "mg"),
    ("iodine_ug",        "碘", "μg"),
    ("_n_fields",        "已识别字段数", ""),
    ("_macro_sum",       "宏量合计(约100)", ""),
    ("_quality_score",   "质量得分", ""),
    ("_symbols",         "数据符号", ""),
]


def clean_name(s):
    """清理 OCR 串码的名称,如「2 19043鱼肚（T）」→「鱼肚（T）」。"""
    if not s:
        return ""
    s = s.strip()
    # 去掉前面粘连的其他编码
    s = re.sub(r"^\d{1,6}\s*", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BASE, "merged_v3.json"))
    ap.add_argument("--vol", default="", help="只输出该册:vol1 / vol2;空=全部")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    with open(a.src, encoding="utf-8") as f:
        recs = json.load(f)

    from build_db import classify
    if a.vol:
        recs = [x for x in recs
                if any(p.startswith(a.vol) for p in x.get("_pages", []))]

    rows = []
    for r in recs:
        row = {}
        for key, zh, unit in COLMAP:
            if key == "_category":
                v = classify(r)
            elif key == "_symbols":
                v = ";".join(symbol_columns(r))
            elif key == "_macro_sum":
                v = round(macro_sum(r), 1)
            else:
                v = r.get(key)
            row[zh + (f"({unit})" if unit else "")] = v
        row["食物名称"] = clean_name(r.get("food_name"))
        rows.append(row)

    rows.sort(key=lambda z: str(z.get("食物编码") or ""))
    cols = [zh + (f"({unit})" if unit else "") for _, zh, unit in COLMAP]

    out = a.out or os.path.join(BASE, "中国食物成分表_营养数据库.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    ok = sum(1 for r in recs if 94 <= (r.get("_macro_sum") or 0) <= 106)
    print(f"saved {out}")
    print(f"记录 {len(rows)}  列 {len(cols)}  守恒通过 {ok}/{len(rows)} "
          f"({ok*100//max(1,len(rows))}%)")
    print("分类:", dict(Counter(r["食物分类"] for r in rows).most_common(12)))


if __name__ == "__main__":
    main()
