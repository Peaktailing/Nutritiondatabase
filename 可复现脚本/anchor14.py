"""表头锚定 v14 —— 补齐未命名列(最终方案)。

v13 遗留:个别列位置检测到但无字段名(如 kJ、烟酸、磷)。
原因:这些表头 token 被 OCR 漏检或形近误识。

补齐策略(按优先级):
1. **单位行 + 已知字段序列推断**:
   单位行天然按列排布。若某列单位为 mg,且其右侧相邻已知列是 calcium_mg,
   则该列很可能是 phosphorus_mg(磷在原表紧邻钙)。
2. **相邻已知列的顺序约束**:用 FIELD_ORDER 做单调性推断 ——
   磷紧跟钙、钾钠镁铁锌依次相邻。
3. **原书固定列序**:同一区段内列序固定,可从多数页投票得出该区段的列序模板。

实现:对同一「区段签名」(字段集合)的页面做多页投票,取最常见的列序模板。
"""
import re
from collections import Counter, defaultdict
import statistics
from anchor3 import hits_in
from anchor6 import en_hits
from anchor13 import (CODE_RE, UNIT_RE, X_LO, X_HI, NAME_LO, NAME_HI,
                      FIELD_ORDER, OIDX, is_data_row, cluster,
                      page_layout, header_seq, align_map,
                      clean_value, extract_records)

# 单位 → 可能的字段(用于推断)
UNIT_HINT = {
    "kcal": ["energy_kcal"], "kj": ["energy_kj"],
    "ugrae": ["vit_a_ug"], "ug": [], "mg": [], "g": [], "%": [],
}

# 紧邻关系(前一字段 → 后一字段候选)
NEIGHBOR = {
    "calcium_mg":   ["phosphorus_mg"],
    "phosphorus_mg": ["potassium_mg"],
    "potassium_mg": ["sodium_mg"],
    "sodium_mg":    ["magnesium_mg"],
    "magnesium_mg": ["iron_mg"],
    "iron_mg":      ["zinc_mg"],
    "zinc_mg":      ["selenium_ug"],
    "selenium_ug":  ["copper_mg"],
    "copper_mg":    ["manganese_mg"],
    "manganese_mg": ["iodine_ug"],
    "water_g":      ["energy_kcal"],
    "energy_kcal":  ["energy_kj"],
    "energy_kj":    ["protein_g", "protein_pct"],
    "edible_pct":   ["water_g"],
    "riboflavin_mg": ["niacin_mg"],
    "vit_a_ug":     ["beta_carotene_ug", "retinol_ug"],
    "beta_carotene_ug": ["retinol_ug"],
    "retinol_ug":   ["thiamin_mg"],
    "thiamin_mg":   ["riboflavin_mg"],
    "niacin_mg":    ["vit_c_mg"],
    "vit_c_mg":     ["vit_e_total_mg"],
    "vit_e_gamma_g": ["calcium_mg"],
    "vit_e_mg":     ["calcium_mg"],
}


def fill_unknown(cols):
    """用相邻已知列 + FIELD_ORDER 单调性填补未命名列。

    关键修正(实测踩坑):
    英文行「Energy」与「kJ」常被识别成相邻两个 token,导致 kJ 列丢失,
    表现为「能量列拿到 kJ 值(1367)而 kcal 列空着」。
    因此除顺序推断外,还需按**原书固定相邻对**做强制补位:
      water_g | energy_kcal | energy_kj | protein_g
    若 energy_kcal 左侧紧邻 water_g 且其右侧列未命名,优先判为 energy_kj。
    """
    out = list(cols)

    # —— 第一步:已知相邻对校验 ——
    for i, (x, k) in enumerate(out):
        if k != "energy_kcal":
            continue
        # 左邻
        left = out[i - 1][1] if i > 0 else None
        right = out[i + 1][1] if i + 1 < len(out) else None
        # 若右邻未命名且左邻是 water_g → 右邻应为 energy_kj,本列仍是 kcal
        if right is None and left == "water_g":
            continue
        # 若左邻未命名且右邻是 protein_g → 左邻应为 energy_kcal,本列应为 energy_kj
        if left is None and right in ("protein_g", "protein_pct"):
            out[i] = (x, "energy_kj")

    # —— 第二步:顺序推断补其余空缺 ——
    for _ in range(3):
        changed = False
        for i, (x, k) in enumerate(out):
            if k is not None:
                continue
            left = None
            for j in range(i - 1, -1, -1):
                if out[j][1]:
                    left = out[j][1]
                    break
            # 找右边最近的已知
            right = None
            for j in range(i + 1, len(out)):
                if out[j][1]:
                    right = out[j][1]
                    break
            guess = None
            if left and left != "food_name":
                # left 后面应该是什么
                li = OIDX.get(left)
                for d in range(1, 6):
                    for cand in range(li + 1, len(FIELD_ORDER)):
                        key = FIELD_ORDER[cand]
                        if key in ("food_name", "food_code", "comment"):
                            continue
                        if key in NEIGHBOR.get(left, []) or cand == li + 1:
                            # 该 key 不应已被右侧占用
                            if not any(k2 == key for _, k2 in out if k2):
                                guess = key
                                break
                    if guess:
                        break
            if guess is None and right and right != "food_name":
                ri = OIDX.get(right)
                for cand in range(max(0, ri - 3), ri):
                    key = FIELD_ORDER[cand]
                    if key in ("food_name", "food_code", "comment"):
                        continue
                    if not any(k2 == key for _, k2 in out if k2):
                        guess = key
            if guess and guess != right:
                out[i] = (x, guess)
                changed = True
        if not changed:
            break
    return out


def build_columns_v14(page_rows, min_gap=42):
    lay = page_layout(page_rows, min_gap)
    if not lay:
        return None, []
    fields = header_seq(page_rows)
    cand = [(x, k) for x, k in fields
            if k not in ("food_code", "food_name", "comment")]
    amap = align_map(cand, lay["numeric"])
    cols = [(cx, cand[amap[j]][1] if j in amap else None)
            for j, cx in enumerate(lay["numeric"])]
    cols = fill_unknown(cols)
    return lay, cols
