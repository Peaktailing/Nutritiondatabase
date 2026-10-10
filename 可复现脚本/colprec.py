"""列级精度检测 —— 用整页同列的数值形态识别丢小数点。

核心观察:
原书营养表数值几乎都带一位小数。OCR 丢小数点后,同一列会呈现
「绝大多数 <10 的小数值」+「少数 ≥10 的整数」的混合分布。
若某列 70% 以上值 <10 而存在 ≥10 的异常值,则该异常值必是丢点(应 ÷10)。

这比逐条记录猜更可靠,因为它利用了整页几十行的一致性。
"""
from validate import score_record
from postfix4 import macro_sum

MACRO = ["protein_g", "fat_g", "carb_g", "fiber_g", "ash_g", "water_g"]

# 这些列天然是大值列(谷薯类蛋白可达 20g+,纤维常 10g+),
# 不能仅凭「有 ≥10 的值」判定丢点,必须更严格。
STRICT_COLS = {"fat_g", "ash_g"}
REQUIRED_SMALL_RATIO = 0.70


def analyze_column(recs, field):
    """返回 (median, small_ratio, big_count, has_decimal_ratio)。"""
    vals = [r[field] for r in recs if r.get(field) is not None]
    if len(vals) < 6:
        return None
    s = sorted(vals)
    med = s[len(s) // 2]
    small = [v for v in vals if v < 10]
    big = [v for v in vals if v >= 10]
    dec = [v for v in vals if abs(v - round(v)) > 1e-9]
    return dict(n=len(vals), med=med,
                small_ratio=len(small) / len(vals),
                big_count=len(big), n_dec=len(dec),
                has_decimal_ratio=len(dec) / len(vals),
                big_vals=big, all_vals=vals)


def detect_bad_columns(recs):
    """返回 {field: 判定信息} —— 疑似存在丢点的列。

    判定条件(收紧后):
    1. 该列 70% 以上的值 < 10 —— 说明这列本质是小数值列
    2. 存在 ≥10 的值 —— 这些是可疑的丢点
    3. 该列确实含小数(证明原表这列是小数形态)
    额外:对 protein/carb/fiber/water 这类天然大值列不采用此规则
    """
    out = {}
    for f in MACRO:
        if f not in STRICT_COLS:
            continue
        st = analyze_column(recs, f)
        if not st:
            continue
        if (st["small_ratio"] >= REQUIRED_SMALL_RATIO
                and st["big_count"] >= 1
                and st["has_decimal_ratio"] > 0):
            out[f] = st
    return out


def fix_page_by_column(recs):
    """按列判定统一修复:该列被判为丢点列时,把 ≥10 的值 ÷10。

    兜底护栏:每条记录修复后必须满足质量守恒(94~104)。
    若某条修复后反而失守,则该条回退(不修)。
    这能自动区分「真的丢点」与「本来就该是大值」。
    """
    bad = detect_bad_columns(recs)
    if not bad:
        return recs, 0, {}
    n = 0
    out = []
    for r in recs:
        s0 = macro_sum(r)
        r2 = dict(r)
        touched = []
        for f, st in bad.items():
            v = r2.get(f)
            if v is None or v < 10:
                continue
            nv = round(v / 10.0, 2)
            if nv <= max(9.9, st["med"] * 3):
                r2[f] = nv
                touched.append(f)
        if touched:
            s1 = macro_sum(r2)
            s0 = macro_sum(r)
            # 采纳条件:修复后更接近 100,且物理校验得分不下降
            better = abs(s1 - 100) < abs(s0 - 100)
            sc_ok = score_record(r2, strict=False)[1] >= score_record(r, strict=False)[1]
            if better and sc_ok:
                out.append(r2)
                n += 1
            else:
                out.append(r)
        else:
            out.append(r)
    return out, n, {f: (st["small_ratio"], st["big_count"])
                    for f, st in bad.items()}
