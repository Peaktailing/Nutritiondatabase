"""数据全面校验 —— 生成校验报告,并标记每条记录的可信度。

校验维度:
1. 编码合法性:6 位数字、前缀属于已知分类
2. 名称合法性:非空、非纯数字、长度合理
3. 数值范围:各营养素生理合理区间
4. 质量守恒:六大宏量之和 ≈ 100
5. 能量守恒:能量 ≈ 蛋白×17 + 脂肪×37 + 碳水×17
6. kJ/kcal 一致性:kJ ≈ kcal × 4.184
7. 重复编码检测
"""
import json, os, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# 生理合理区间(每 100g 可食部,超出即标记异常)
RANGES = {
    "edible_pct": (30, 100), "water_g": (0, 100), "energy_kcal": (0, 950),
    "energy_kj": (0, 4000), "protein_g": (0, 95), "fat_g": (0, 110),
    "carb_g": (0, 105), "fiber_g": (0, 75), "ash_g": (0, 30),
    "cholesterol_mg": (0, 3500), "vit_a_ug": (0, 30000),
    "beta_carotene_ug": (0, 40000), "thiamin_mg": (0, 100),
    "riboflavin_mg": (0, 100), "niacin_mg": (0, 200), "vit_c_mg": (0, 3500),
    "vit_e_mg": (0, 200), "calcium_mg": (0, 2500), "phosphorus_mg": (0, 2500),
    "potassium_mg": (0, 3500), "sodium_mg": (0, 45000),
    "magnesium_mg": (0, 1500), "iron_mg": (0, 350), "zinc_mg": (0, 400),
    "selenium_ug": (0, 500), "copper_mg": (0, 100), "manganese_mg": (0, 200),
    "iodine_ug": (0, 20000),
}

VALID_PREFIX = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
                "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21"}

MACRO = ["water_g", "protein_g", "fat_g", "carb_g", "fiber_g", "ash_g"]


def to_f(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def check_record(r):
    """返回 (issues 列表, score 0-100)"""
    issues = []
    score = 100

    code = (r.get("food_code") or "").strip()
    if not code.isdigit() or len(code) != 6:
        issues.append("编码非法")
        score -= 30
    elif code[:2] not in VALID_PREFIX:
        issues.append(f"编码前缀异常({code[:2]})")
        score -= 15

    name = (r.get("food_name") or "").strip()
    if not name:
        issues.append("名称缺失")
        score -= 25
    elif name.replace(".", "").isdigit():
        issues.append("名称为纯数字")
        score -= 20
    elif len(name) > 60:
        issues.append("名称过长(可能串码)")
        score -= 10

    oor = []
    for k, (lo, hi) in RANGES.items():
        v = to_f(r.get(k))
        if v is not None and not (lo <= v <= hi):
            oor.append(k)
    if oor:
        issues.append("越界:" + ",".join(oor[:4]))
        score -= min(30, 8 * len(oor))

    parts = [to_f(r.get(k)) or 0 for k in MACRO]
    s = sum(parts)
    n = sum(1 for k in MACRO if to_f(r.get(k)) is not None)
    if n >= 4 and not (88 <= s <= 110):
        issues.append(f"宏量合计异常({s:.1f})")
        score -= 15

    # 能量守恒(Atwater 系数算出来是 kJ,须与 kJ 比对)
    kcal = to_f(r.get("energy_kcal"))
    kj = to_f(r.get("energy_kj"))
    p, f, c = (to_f(r.get("protein_g")), to_f(r.get("fat_g")),
               to_f(r.get("carb_g")))
    if p is not None and f is not None and c is not None:
        calc_kj = p * 17 + f * 37 + c * 17
        fib = to_f(r.get("fiber_g"))
        if fib is not None:
            calc_kj += fib * 8
        target_kj = kj if kj is not None else (
            kcal * 4.184 if kcal is not None else None)
        if calc_kj > 0 and target_kj:
            ratio = target_kj / calc_kj
            if not (0.72 <= ratio <= 1.35):
                issues.append(f"能量与宏量不符(比{ratio:.2f})")
                score -= 15

    kj = to_f(r.get("energy_kj"))
    if kcal and kj and kcal > 0:
        ratio = kj / kcal
        if not (3.6 <= ratio <= 4.8):
            issues.append(f"kJ/kcal不一致({ratio:.2f})")
            score -= 10

    return issues, max(0, score)


def grade(score):
    if score >= 90:
        return "A(可信)"
    if score >= 75:
        return "B(基本可信)"
    if score >= 55:
        return "C(需核对)"
    return "D(可疑)"


def main():
    src = os.path.join(BASE, "merged_v3.json")
    with open(src, encoding="utf-8") as f:
        recs = json.load(f)

    from build_db import classify
    results = []
    for r in recs:
        issues, score = check_record(r)
        r2 = dict(r)
        r2["_issues"] = "; ".join(i for i in issues if i)
        r2["_check_score"] = score
        r2["_grade"] = grade(score)
        r2["_category"] = classify(r)
        results.append(r2)

    cnt = Counter(r["food_code"] for r in results)
    dup = {k: v for k, v in cnt.items() if v > 1}

    g = Counter(r["_grade"] for r in results)
    iss = Counter()
    for r in results:
        for i in r["_issues"].split("; "):
            if i:
                iss[i.split("(")[0].split(":")[0]] += 1

    rep = os.path.join(BASE, "校验报告.txt")
    with open(rep, "w", encoding="utf-8") as f:
        f.write("《中国食物成分表 标准版 第6版》 数据校验报告\n")
        f.write("=" * 54 + "\n\n")
        f.write(f"校验记录数: {len(results)}\n")
        f.write(f"重复编码: {len(dup)} 个\n\n")
        f.write("可信度分级:\n")
        for k in ["A(可信)", "B(基本可信)", "C(需核对)", "D(可疑)"]:
            n = g.get(k, 0)
            f.write(f"  {k:14s} {n:5d}  ({n*100//max(1,len(results))}%)\n")
        f.write("\n主要问题分布:\n")
        for k, v in iss.most_common(14):
            f.write(f"  {k:24s} {v:5d}\n")
        f.write("\n分级说明:\n")
        f.write("  A 可信      无越界、守恒关系成立\n")
        f.write("  B 基本可信  轻微问题(如个别字段缺失)\n")
        f.write("  C 需核对    存在越界或守恒失守,建议比对原书\n")
        f.write("  D 可疑      多项异常,使用前务必核对\n")
        if dup:
            f.write(f"\n重复编码数: {len(dup)}\n")

    print(f"记录 {len(results)}  重复编码 {len(dup)}")
    for k in ["A(可信)", "B(基本可信)", "C(需核对)", "D(可疑)"]:
        print(f"  {k:14s} {g.get(k,0):5d}")
    print("\n主要问题:")
    for k, v in iss.most_common(10):
        print(f"  {k:24s} {v}")
    print(f"\n报告: {rep}")

    with open(os.path.join(BASE, "checked_v3.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("saved checked_v3.json")


if __name__ == "__main__":
    main()
