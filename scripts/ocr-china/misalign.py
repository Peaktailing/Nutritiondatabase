"""列错位检测与修复 —— 利用同列跨记录的分布一致性。

原理:
一条记录里 fiber=9.9 而 fat=1.4(总和 122),说明这两列的内容互换了。
但单看一条记录无法断定是「fat/fiber 互换」还是「fiber 丢小数点」。

判据:看**整列**的数值分布。
  - 若某列在整页中,数值几乎都 < 10 且众数集中在 0~5 → 这是「膳食纤维」这类列
  - 若某列数值跨度大(0~90)且常有两位数 → 这是「碳水化合物」列
当列 a 的分布特征与列 b 明显不同,而它们的数值恰好可以互换使总和回到 100,
就应判定为错位。

实现:
1. 对每页每列,统计 median、IQR、是否常 >10
2. 与「该字段的先验分布」比对(RANGES + 典型量级)
3. 若某列数据分布与所标字段严重不符 → 尝试与相邻列交换,取使总得分提升者
"""
from itertools import combinations
from validate import score_record, RANGES
from postfix4 import macro_sum

# 各字段的典型量级(来自营养学常识,用于快速判别)
TYPICAL = {
    "water_g":        (5, 90),
    "protein_g":      (0.5, 35),
    "fat_g":          (0, 60),
    "carb_g":         (0, 90),
    "fiber_g":        (0, 30),
    "ash_g":          (0, 8),
    "cholesterol_mg": (0, 500),
    "thiamin_mg":     (0.02, 3),
    "riboflavin_mg":  (0.01, 3),
    "niacin_mg":      (0.3, 70),
    "vit_c_mg":       (0, 400),
    "calcium_mg":     (5, 1500),
    "phosphorus_mg":  (10, 2500),
    "potassium_mg":   (50, 2500),
    "sodium_mg":      (0, 1500),
    "magnesium_mg":   (5, 400),
    "iron_mg":        (0.2, 60),
    "zinc_mg":        (0.1, 20),
    "selenium_ug":    (0.02, 30),
    "copper_mg":      (0.02, 10),
    "manganese_mg":   (0.05, 10),
    "vit_a_ug":       (0, 10000),
    "beta_carotene_ug": (0, 20000),
    "retinol_ug":     (0, 3000),
    "vit_e_total_mg": (0, 30),
    "vit_e_alpha_g":  (0, 20),
    "vit_e_mg":       (0, 20),
    "vit_e_gamma_g":  (0, 20),
    "edible_pct":     (50, 100),
    "energy_kcal":    (0, 900),
    "energy_kj":      (0, 3800),
}


def col_stats(recs, field):
    """列统计。防御:某些列可能混入字符串(如备注列),只取数值。"""
    vals = sorted(v for v in (r.get(field) for r in recs)
                  if isinstance(v, (int, float)))
    if len(vals) < 4:
        return None
    n = len(vals)
    med = vals[n // 2]
    p90 = vals[int(n * 0.9)]
    return dict(n=n, med=med, p90=p90, mx=vals[-1], mn=vals[0])


def mismatch(recs, field):
    """该列数据分布与字段典型量级的偏离度(0=完全吻合,越大越不符)。"""
    st = col_stats(recs, field)
    t = TYPICAL.get(field)
    if not st or not t:
        return 0.0
    lo, hi = t
    pen = 0.0
    # 中位数应落在典型区间
    if st["med"] < lo:
        pen += (lo - st["med"]) / max(lo, 1)
    elif st["med"] > hi:
        pen += (st["med"] - hi) / max(hi, 1)
    # p90 也不应远超上限
    if st["p90"] > hi * 1.5:
        pen += (st["p90"] - hi * 1.5) / max(hi, 1)
    return pen


def try_swap(page_rows, lay, cols, extract_fn, max_swaps=1):
    """尝试交换列以修正错位,返回 (best_cols, best_recs, best_score, swaps)。"""
    recs = extract_fn(cols)
    base = _avg_score(recs)
    best = (cols, recs, base, 0)
    if base >= 60:
        return best

    # 找出可疑列(分布与字段不符)
    sus = []
    for i, (x, k) in enumerate(cols):
        if k and mismatch(recs, k) > 0.5:
            sus.append(i)
    if not sus:
        return best

    cands = []
    for i in sus:
        for j in range(max(0, i - 2), min(len(cols), i + 3)):
            if j != i:
                cands.append((i, j))
    for (i, j) in cands:
        c2 = list(cols)
        c2[i], c2[j] = c2[j], c2[i]
        r2 = extract_fn(c2)
        s2 = _avg_score(r2)
        if s2 > best[2] + 2:
            best = (c2, r2, s2, 1)
    return best


def _avg_score(recs):
    if not recs:
        return 0
    return sum(score_record(r, strict=False)[1] for r in recs) / len(recs)
