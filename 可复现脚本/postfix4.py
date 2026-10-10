"""数值修复 v4 —— 能量守恒驱动的精确纠错(修正版)。

「丢小数点」错误会同时破坏两个独立约束:
  (1) 质量守恒: 水+蛋白+脂肪+碳水+纤维+灰分 ≈ 100
  (2) 能量守恒: 能量kcal ≈ 蛋白×17 + 脂肪×37 + 碳水×17
若某列被放大 10 倍,(1) 必然超出 108,(2) 也会严重偏离。

枚举所有「哪些列 ÷10」的组合,用三重打分取全局最优。
搜索空间 = 2^4 = 16(仅 4 个可修正列),完全可枚举。

护栏:
- 只在质量守恒超出 [92, 106] 时介入
- 只允许 ÷10(丢点只会让值变大)
- 必须同时让「距 100 更近」且「总得分不降」

⚠ 实测教训:不能仅凭「值 ≥10」就 ÷10。
   小麦蛋白质 11.9、大麦 10.2 都是真实值,若因其他列缺失误判,
   会被错误地 ÷10(实测曾把 11.9 改成 1.19)。
   故追加硬约束:候选列必须**超过该字段的生理上限**
   (单一食物中蛋白质 >40g/100g、脂肪 >65g/100g 极罕见)。
"""
from validate import score_record

MACRO = ["water_g", "protein_g", "fat_g", "carb_g", "fiber_g", "ash_g"]
# 可修正列:排除水分与碳水(它们常是两位数整数,÷10 不合理)
FIXABLE = ["protein_g", "fat_g", "fiber_g", "ash_g"]

# 生理上限(每 100g 可食部)—— 超过则几乎必是丢小数点导致的放大
PHYSIOLOGICAL_MAX = {
    "protein_g": 40.0,
    "fat_g": 65.0,
    "fiber_g": 30.0,
    "ash_g": 8.0,
}


def macro_sum(rec):
    return sum(rec.get(k) or 0 for k in MACRO)


def fix_record(rec):
    s0 = macro_sum(rec)
    if 92 <= s0 <= 106:
        return rec, None
    sc0 = score_record(rec, strict=False)[1]
    d0 = abs(s0 - 100)

    cands = [f for f in FIXABLE
             if (rec.get(f) or 0) > PHYSIOLOGICAL_MAX.get(f, 1e9)]
    if not cands:
        return rec, None

    best_sc = sc0
    best_rec = rec
    best_note = None
    best_d = d0

    for mask in range(1, 1 << len(cands)):
        sel = [cands[i] for i in range(len(cands)) if mask & (1 << i)]
        r2 = dict(rec)
        for f in sel:
            r2[f] = round(r2[f] / 10.0, 2)
        s2 = macro_sum(r2)
        if not (90 <= s2 <= 108):
            continue
        d2 = abs(s2 - 100)
        if d2 >= d0:
            continue
        sc2 = score_record(r2, strict=False)[1]
        if sc2 < sc0:
            continue
        # 优先「得分更高」,其次「总和更接近 100」
        if (sc2, -d2) > (best_sc, -best_d):
            best_sc, best_rec, best_note, best_d = sc2, r2, "+".join(sel), d2

    if best_note:
        return best_rec, best_note
    return rec, None


def fix_page(recs, int_masks=None):
    """整页修复 + 护栏:修正后若总分反而下降,则回退原值。"""
    out, notes = [], 0
    for r in recs:
        r2, note = fix_record(r)
        if note:
            # 护栏:修正后质量得分必须真的提升
            sc0 = score_record(r, strict=False)[1]
            sc1 = score_record(r2, strict=False)[1]
            s1 = macro_sum(r2)
            if sc1 <= sc0 or not (94 <= s1 <= 104):
                out.append(r)          # 回退
                continue
            notes += 1
        out.append(r2)
    return out, notes
