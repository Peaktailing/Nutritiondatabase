"""列映射的语义校验与纠正。

原理:营养数据有强物理约束,可用来检测并修正列错位。
约束(每 100g 可食部):
  1. 能量 ≈ 蛋白质×17 + 脂肪×37 + 碳水×17  (kcal,容差 ±25%)
  2. 蛋白质 + 脂肪 + 碳水 + 膳食纤维 + 灰分 + 水分 ≈ 100
  3. 脂肪 ≤ 总能量/37 × 1.2
  4. 碳水化合物通常 ≥ 脂肪(谷薯类)

当某列错位时(如脂肪列拿到碳水值 73.3),约束 1/2 会立刻失败,
据此在候选列之间做**局部换位搜索**,取满足约束的组合。
"""
import itertools

# 各宏量字段的合理范围(每 100g)
RANGES = {
    "water_g":        (0, 95),
    "protein_g":      (0, 40),
    "fat_g":          (0, 100),
    "carb_g":         (0, 100),
    "fiber_g":        (0, 30),
    "ash_g":          (0, 5),
    "edible_pct":     (50, 100),
    "cholesterol_mg": (0, 600),
    "energy_kcal":    (0, 950),
    "energy_kj":      (0, 4000),
    # 单位是 mg 的微量元素,原书多以整数或一位小数出现
    "calcium_mg":     (0, 2000), "phosphorus_mg": (0, 3000),
    "potassium_mg":   (0, 3000), "sodium_mg":     (0, 2000),
    "magnesium_mg":   (0, 400),  "iron_mg":       (0, 100),
    "zinc_mg":        (0, 50),   "selenium_ug":   (0, 100),
    "copper_mg":      (0, 20),   "manganese_mg":  (0, 20),
    "thiamin_mg":     (0, 5),    "riboflavin_mg": (0, 5),
    "niacin_mg":      (0, 80),   "vit_c_mg":      (0, 500),
    "vit_a_ug":       (0, 15000), "beta_carotene_ug": (0, 30000),
    "retinol_ug":     (0, 5000),
}

MACRO = ["water_g", "protein_g", "fat_g", "carb_g", "fiber_g", "ash_g"]


def in_range(field, v):
    if v is None:
        return True
    r = RANGES.get(field)
    if not r:
        return True
    return r[0] <= v <= r[1]


# Atwater 系数(单位 kJ/g)—— 注意算出来是 kJ,不是 kcal
ATWATER_KJ = {"protein_g": 17.0, "fat_g": 37.0, "carb_g": 17.0, "fiber_g": 8.0}
KCAL_PER_KJ = 1.0 / 4.184


def energy_kj_calc(rec):
    """由宏量营养素推算能量(kJ)。返回 None 表示数据不足。"""
    p = rec.get("protein_g")
    f = rec.get("fat_g")
    c = rec.get("carb_g")
    if p is None or f is None or c is None:
        return None
    v = p * ATWATER_KJ["protein_g"] + f * ATWATER_KJ["fat_g"] \
        + c * ATWATER_KJ["carb_g"]
    fib = rec.get("fiber_g")
    if fib is not None:
        v += fib * ATWATER_KJ["fiber_g"]
    return v


def score_record(rec, strict=True):
    """返回 (是否合理, 得分)。得分越高越符合物理约束。

    ⚠ 单位修正(实测踩坑):
      「蛋白×17 + 脂肪×37 + 碳水×17」算出来是 **kJ**,不是 kcal。
      此前误拿它与 energy_kcal 比(期望比值≈1),导致能量校验长期失效
      —— 正常的粳米(353kcal / 1469kJ)也会被判为"不符"。
      正确做法:推算值与 energy_kj 比(≈1),或与 energy_kcal 比(≈0.239)。
    """
    w = rec.get("water_g")
    p = rec.get("protein_g")
    f = rec.get("fat_g")
    c = rec.get("carb_g")
    fib = rec.get("fiber_g")
    ash = rec.get("ash_g")
    kcal = rec.get("energy_kcal")
    kj = rec.get("energy_kj")

    s = 0
    # 约束 1: 质量守恒
    parts = [x for x in (w, p, f, c, fib, ash) if x is not None]
    if len(parts) >= 4:
        tot = sum(parts)
        if 90 <= tot <= 108:
            s += 40
        elif 80 <= tot <= 118:
            s += 20
        else:
            if strict:
                return False, s
            s -= 30

    # 约束 2: 能量守恒(用 kJ 比对)
    calc_kj = energy_kj_calc(rec)
    target_kj = kj if kj is not None else (
        kcal / KCAL_PER_KJ if kcal is not None else None)
    if calc_kj and target_kj and calc_kj > 0:
        ratio = target_kj / calc_kj
        if 0.85 <= ratio <= 1.15:
            s += 40
        elif 0.7 <= ratio <= 1.35:
            s += 12
        else:
            if strict:
                return False, s
            s -= 30

    # 约束 3: kJ 与 kcal 一致性
    if kcal is not None and kj is not None and kcal > 0:
        ratio = kj / kcal
        if 3.9 <= ratio <= 4.5:
            s += 30
        elif 3.4 <= ratio <= 5.2:
            s += 10
        else:
            if strict:
                return False, s
            s -= 25
    return True, s


def check(rec):
    """返回 (ok, score)。"""
    return score_record(rec, strict=True)


def validate_columns(cols, recs):
    """用该页所有记录校验列映射,返回 (ok, score, bad_count)。"""
    if not recs:
        return True, 0, 0
    good, bad = 0, 0
    tot = 0
    for r in recs:
        ok, sc = check(r)
        tot += sc
        if ok:
            good += 1
        else:
            bad += 1
    return bad == 0, tot, bad
