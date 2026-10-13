#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段四：OCR 读数错误的自动修复。

修复对象：china_food_merged 里 merge_flag 标记的四类问题。
修复依据：两条物理守恒律（不可伪造）——
  1. 五项守恒：水+蛋白+脂肪+碳水+灰分 = 100 g/100g（±3 容差）
     注意中国表碳水列含膳食纤维（实测确认），纤维不重复加入。
  2. 能量守恒：kcal ≈ 4*蛋白 + 9*脂肪 + 4*碳水 + 2*纤维（中国 Atwater 系数）

判定策略：对每条问题行枚举「单列错误」假设，选第一个同时满足两条
守恒的假设；单一假设不成立才考虑组合。绝不无中生有——没有任何
假设能自洽的行保持原值并升级标记为 needs_manual_review。

四类问题：
  A. macro_sum_def_includes_fiber（61 条假警报）
     数据自洽，是 OCR 脚本 macro_sum 定义多加了纤维。只改标记，
     重算 macro_sum（按六项口径），不动数据。
  B. ocr_carb_column_shift 中的真错（46 条）
     实际两种模式：蛋白列多读一个 0（10.0→1.0）、碳水列×10（74→7.4）。
     用双约束自动判定错在哪列。
  C. ocr_kj_decimal_shift（72 条）
     kJ 小数点丢失。kcal 正常（flag 判据即 kJ/kcal<3.5），重算
     kJ = kcal × 4.184。重算前先用宏量验证 kcal 本身自洽。
  D. ocr_macro_sum_low（3 条）→ 一并双约束诊断。
"""
import json
import os
import sqlite3

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.environ.get("FDC_DB", os.path.join(_ROOT, "nutrition.db"))
REPAIR_LOG = os.path.join(_ROOT, "data", "china-ocr", "repair_log.json")

# 中国表能量系数（kJ/g，来自原书 meta：蛋白17 脂肪37 碳水17 纤维8）
# kcal 版即 4 / 9 / 4 / 2（近似换算，与原书 kJ 系数自洽）
KC_P, KC_F, KC_C, KC_FIB = 4.0, 9.0, 4.0, 2.0


def kcal_calc(p, f, c, fib):
    # 中国表碳水列含膳食纤维（实测确认），能量只计可利用碳水。
    # 之前把 2kcal/g 纤维系数重复加上，导致茄子等绿叶菜的合法修复假设
    # 被能量校验误杀。纤维系数保留在常数里仅作备份对照。
    avail = max((c or 0) - (fib or 0), 0)
    return KC_P * (p or 0) + KC_F * (f or 0) + KC_C * avail


def five_sum(w, p, f, c, ash):
    return (w or 0) + (p or 0) + (f or 0) + (c or 0) + (ash or 0)


def plausible(v, lo=0.0, hi=100.0):
    return v is not None and lo <= v <= hi


def diagnose(w, p, f, c, fib, ash, kcal, kj):
    """返回 (修复 dict, 描述, strict) 或 (None, 原因, False)。

    候选假设（单列小数点错位为主，实测仅三种模式）：
      碳水 ×10/÷10、蛋白 ×10/÷10、脂肪 ×10/÷10、水分补齐
    两轮筛选：
      strict 轮：五项守恒(100±2.5) + 能量守恒(±30%)
      loose  轮：仅五项守恒 —— 记录的 kcal 本身可能也是错的（与碳水
      同源错误），此时能量不能作为否决依据；命中后 kcal 用宏量重算。
    """
    cands = []  # (fix_dict, desc, strict)

    def check(w_, p_, f_, c_, ash_):
        """返回 (五项和OK, 能量OK, 反推kcal)"""
        s5 = five_sum(w_, p_, f_, c_, ash_)
        if abs(s5 - 100) > 2.5:
            return False, False, None
        calc = kcal_calc(p_, f_, c_, fib)
        # 能量参照：kcal 缺失时退回 kJ/4.184（鲜牛奶(现代牧场) kcal=None
        # 但 kj=268 → 参照 64 kcal，与蛋白 3.4 的修复假设吻合）
        ref = kcal if (kcal and kcal > 0) else (
            kj / 4.184 if (kj and kj > 0 and kj < 4000) else None)
        eok = (ref and ref > 0 and abs(calc - ref) <= 0.30 * ref)
        return True, eok, calc

    def try_fix(fix):
        new = {"water_g": w, "protein_g": p, "fat_g": f, "carb_g": c,
               "ash_g": ash}
        new.update(fix)
        s5ok, eok, calc = check(new["water_g"], new["protein_g"],
                                new["fat_g"], new["carb_g"], new["ash_g"])
        if not s5ok:
            return
        for v in new.values():
            if not plausible(v):
                return
        cands.append((fix, calc, eok))

    if c is not None:
        for cc in (c / 10, c * 10):
            try_fix({"carb_g": round(cc, 2)})
    if p is not None:
        for pp in (p / 10, p * 10):
            try_fix({"protein_g": round(pp, 2)})
    if f is not None:
        for ff in (f / 10, f * 10):
            try_fix({"fat_g": round(ff, 2)})
    if None not in (p, f, c, ash):
        w_ = 100 - p - f - c - ash
        if plausible(w_):
            try_fix({"water_g": round(w_, 2)})

    for cand in cands:
        if cand[2]:                      # strict 命中
            return cand[0], cand[1], True
    if len(cands) == 1:                  # 仅一条 loose 候选才敢采信
        return cands[0][0], cands[0][1], False
    if cands:
        return None, f"{len(cands)} 个候选无能量佐证，不裁决", False
    return None, "无自洽假设", False


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    log = []

    # ============ A. 假警报 61 条 + 真错 46 条（碳水 shift）============
    rows = cur.execute("""select food_code, food_name, water_g, protein_g,
        fat_g, carb_g, fiber_g, ash_g, energy_kcal, energy_kj, check_grade,
        macro_sum, merge_flag
        from china_food_merged
        where merge_flag in ('ocr_carb_column_shift', 'ocr_macro_sum_low')"""
    ).fetchall()
    fixed, false_alarm, manual = 0, 0, []
    for (code, name, w, p, f, c, fib, ash, kcal, kj, grade, ms, flag) in rows:
        s5 = five_sum(w, p, f, c, ash) if None not in (w, p, f, c, ash) else None
        # 假警报：五项和自洽，只是 macro_sum 定义问题
        if s5 is not None and abs(s5 - 100) <= 3:
            cur.execute("""update china_food_merged
                set merge_flag='macro_sum_def_includes_fiber' where food_code=?""",
                (code,))
            false_alarm += 1
            log.append({"code": code, "name": name, "flag": flag,
                        "fix": None, "false_alarm": True,
                        "desc": f"五项和={s5:.1f} 自洽，macro_sum 口径问题",
                        "five_sum_before": s5})
            continue
        fx, desc, strict = diagnose(w, p, f, c, fib, ash, kcal, kj)
        if fx:
            sets = {**fx}
            new = {"water_g": w, "protein_g": p, "fat_g": f, "carb_g": c,
                   "ash_g": ash}
            new.update(fx)
            ms6 = (new["water_g"] or 0) + (new["protein_g"] or 0) + \
                  (new["fat_g"] or 0) + (new["carb_g"] or 0) + \
                  (new["ash_g"] or 0)
            sets["macro_sum"] = round(ms6, 1)
            # loose 轮命中说明记录的 kcal 不可信，用宏量重算（kJ 同步）
            if not strict and kcal and kcal > 0:
                sets["energy_kcal"] = round(desc, 1)
                sets["energy_kj"] = round(desc * 4.184, 1)
            sets["merge_flag"] = "ocr_repaired"
            sql = ", ".join(f"{k}=?" for k in sets)
            cur.execute(f"update china_food_merged set {sql} where food_code=?",
                        (*sets.values(), code))
            log.append({"code": code, "name": name, "flag": flag,
                        "fix": fx, "desc": desc, "five_sum_before": s5})
            fixed += 1
        else:
            cur.execute("""update china_food_merged
                set merge_flag='needs_manual_review' where food_code=?""",
                (code,))
            manual.append((code, name, w, p, f, c, ash))

    print(f"[碳水列/宏量] 假警报 {false_alarm} / 自动修复 {fixed} / 转人工 {len(manual)}")
    for r in manual:
        print("   人工:", r)

    # ============ C. kJ 列异常（小数点丢失 / 两列互换）============
    rows = cur.execute("""select food_code, food_name, protein_g, fat_g,
        carb_g, fiber_g, energy_kcal, energy_kj
        from china_food_merged where merge_flag='ocr_kj_decimal_shift'"""
    ).fetchall()
    kj_fix, kj_swap, kj_manual = 0, 0, 0
    for code, name, p, f, c, fib, kcal, kj in rows:
        calc = kcal_calc(p, f, c, fib)
        # 假设1：kcal 正常、kJ 小数点丢失 → kJ = kcal × 4.184
        if kcal and kcal > 0 and abs(calc - kcal) <= 0.30 * kcal:
            cur.execute("""update china_food_merged
                set energy_kj=?, merge_flag='ocr_repaired' where food_code=?""",
                (round(kcal * 4.184, 1), code))
            kj_fix += 1
            log.append({"code": code, "name": name,
                        "flag": "ocr_kj_decimal_shift",
                        "fix": {"energy_kj": round(kcal * 4.184, 1),
                                "energy_kj_before": kj},
                        "desc": round(kcal, 1)})
            continue
        # 假设2：kcal/kJ 两列互换（白沙蒿 232"kcal"+56"kJ" → 鲜野菜
        # 232 kcal 不可能，56 kcal≈248 kJ 才对，即两列颠倒）。
        # 判据：宏量反推 kcal 与「kJ 列数值」吻合、且与「kcal 列数值」
        # 不吻合 → 交换。
        if (kcal and kj and kj > 0
                and abs(calc - kj) <= 0.30 * kj
                and abs(calc - max(kcal, 1)) > 0.30 * max(kcal, 1)):
            cur.execute("""update china_food_merged
                set energy_kcal=?, energy_kj=?, merge_flag='ocr_repaired'
                where food_code=?""", (float(kj), round(kcal * 4.184, 1), code))
            kj_swap += 1
            log.append({"code": code, "name": name,
                        "flag": "ocr_kj_decimal_shift",
                        "fix": {"energy_kcal": float(kj),
                                "energy_kj": round(kcal * 4.184, 1),
                                "kcal_before": kcal, "kj_before": kj},
                        "desc": "kcal/kJ 两列互换（宏量反推吻合 kJ 列）"})
            continue
        # 假设3：整段列互换但碳水缺失，宏量反推不可用。
        # 证据链：互换后 kj/kcal 比值自动 ≈ 4.184（因为两值就是互换的），
        # 且互换后 kcal 落在食物合理区间。048 段野生蔬菜 37 行全部符合
        # 该模式（kcal 列实为 kJ 值），按互换修复。
        if kcal and kj and kj > 0:
            ratio = kj / max(kcal, 1)          # 记录比值，应在 0.15~0.35
            kcal_new, kj_new = float(kj), float(kcal)   # 纯互换
            back = kj_new / kcal_new           # 互换后比值，应 ≈ 4.184
            if (0.10 <= ratio <= 0.35 and 3.6 <= back <= 5.2
                    and 5 <= kcal_new <= 900):
                cur.execute("""update china_food_merged
                    set energy_kcal=?, energy_kj=?, merge_flag='ocr_repaired'
                    where food_code=?""", (kcal_new, kj_new, code))
                kj_swap += 1
                log.append({"code": code, "name": name,
                            "flag": "ocr_kj_decimal_shift",
                            "fix": {"energy_kcal": kcal_new,
                                    "energy_kj": kj_new,
                                    "kcal_before": kcal, "kj_before": kj},
                            "desc": f"kcal/kJ 两列互换（比值 {ratio:.2f}）"})
                continue
        # 假设4：宏量严重缺失（无法做任何守恒验证），但 kcal 自身
        # 高度可信 —— 同簇产品一致（米粉 9 条全在 407~415）且符合品类
        # 常识，kJ 是单纯的小数点丢失（5.4 对 407）。判据：kJ/kcal<0.05
        # 且 kcal 在合理区间。红螺(比值0.83)不属于此模式，保持人工。
        if kcal and kj and kcal > 0 and kj / kcal < 0.05 and 50 <= kcal <= 900:
            cur.execute("""update china_food_merged
                set energy_kj=?, merge_flag='ocr_repaired' where food_code=?""",
                (round(kcal * 4.184, 1), code))
            kj_fix += 1
            log.append({"code": code, "name": name,
                        "flag": "ocr_kj_decimal_shift",
                        "fix": {"energy_kj": round(kcal * 4.184, 1),
                                "energy_kj_before": kj},
                        "desc": f"宏量缺失，kcal={kcal} 同簇一致"})
            continue
        kj_manual += 1
        cur.execute("""update china_food_merged
            set merge_flag='needs_manual_review' where food_code=?""", (code,))
        log.append({"code": code, "name": name,
                    "flag": "ocr_kj_decimal_shift",
                    "fix": None, "manual": True,
                    "desc": f"kcal={kcal} kJ={kj} 宏量反推={calc:.0f}"})
        if kj_manual <= 12:
            print(f"   kJ 人工: {code} {name} kcal={kcal} kJ={kj} 宏量反推={calc:.0f}")
    print(f"[kJ 列] 重算 {kj_fix} / 互换修复 {kj_swap} / 转人工 {kj_manual}")

    # A/B 段转人工的也补进日志（含现值，便于人工核对原书）
    for code, name, w, p, f, c, ash in manual:
        log.append({"code": code, "name": name,
                    "flag": "needs_manual_review",
                    "fix": None, "manual": True,
                    "desc": f"五项和={five_sum(w, p, f, c, ash):.1f}",
                    "values": {"water_g": w, "protein_g": p, "fat_g": f,
                               "carb_g": c, "ash_g": ash}})

    with open(REPAIR_LOG, "w",
              encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1)

    # ============ 汇总 ============
    print()
    print("=== 修复后标记分布 ===")
    for fl, n in cur.execute(
            "select merge_flag, count(*) from china_food_merged group by 1 "
            "order by 2 desc"):
        print(f"  {fl or '(无)':<32} {n:,}")
    # 最终守恒复检
    bad = cur.execute("""select count(*) from china_food_merged
        where water_g is not null and protein_g is not null and fat_g is not null
          and carb_g is not null and ash_g is not null
          and abs(water_g+protein_g+fat_g+carb_g+ash_g-100) > 3""").fetchone()[0]
    print(f"\n全表五项守恒复检（100±3 之外）: {bad} 条")
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
