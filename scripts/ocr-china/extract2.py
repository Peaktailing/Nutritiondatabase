"""记录抽取 v2 —— 额外记录「原始 token 是否为整数」,供保守修复使用。"""
import re
from anchor13 import (CODE_RE, NAME_LO, NAME_HI, SYMBOLS, is_data_row)  # noqa: F401


def clean_value_marked(t):
    """→ (value|None, symbol|None, was_plain_int)

    was_plain_int: 原始 token 是纯整数(如 "14"),不含小数点。
    扫描件 OCR 常丢小数点(1.4 → 14),故标记出来供保守修复使用。
    含小数点的 token("13.1")一律视为可信,永不修改。
    """
    if t is None:
        return None, None, False
    s = t.strip().replace(" ", "").replace("\u00a0", "")
    for ch in ["—", "–", "－"]:
        s = s.replace(ch, "")
    if s == "":
        return None, None, False
    if s in SYMBOLS:
        return None, s, False
    if re.match(r"^\d{6}$", s):
        return s, None, False

    # 情况 1:带比较符或小数点 —— 可信
    m = re.match(r"^([<>~]?)(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(2)), (m.group(1) or None), False

    # 情况 2:纯整数 —— 可疑(可能丢了小数点)
    if re.match(r"^\d+$", s):
        return float(s), None, True

    # 情况 3:含 OCR 形近误识字符,先纠正再判断
    t2 = s
    for a, b in [("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("|", "1"),
                 ("S", "5"), ("B", "8"), ("Z", "2"), ("g", "9"), ("D", "0")]:
        t2 = t2.replace(a, b)
    m = re.match(r"^(\d+(?:\.\d+)?)$", t2)
    if m:
        return float(m.group(1)), (None if t2 == s else "ocr_fixed"), False
    m = re.match(r"^(\d+(?:\.\d+)?)x$", s)
    if m:
        return float(m.group(1)), "ocr_fixed", False
    return None, "unparsed", False


def extract_records_v2(page_rows, lay, cols):
    """返回 (records, int_masks)。int_masks[i] 为第 i 条记录中整数 token 字段集合。"""
    out, masks = [], []
    for row in page_rows:
        if not is_data_row(row):
            continue
        code = None
        for it in row:
            m = CODE_RE.match(it["t"].strip())
            if m:
                code = m.group(0)
                break
        if code is None:
            continue
        rec = {"food_code": code}
        intset = set()
        name_parts = []
        for it in row:
            t = it["t"].strip()
            if not t or CODE_RE.match(t):
                continue
            x = it["x"]
            if lay["name_x"] is not None and abs(x - lay["name_x"]) <= 190:
                if not re.match(r"^[\d.]+$", t) and t not in SYMBOLS:
                    name_parts.append(t)
                continue
            best, bd = None, 1e9
            for cx, key in cols:
                d = abs(cx - x)
                if d < bd:
                    bd, best = d, key
            if best and bd <= 60:
                v, sym, was_int = clean_value_marked(t)
                if rec.get(best) is None:
                    rec[best] = v
                    if sym:
                        rec[best + "_sym"] = sym
                    if was_int and v is not None:
                        intset.add(best)
                elif rec.get(best) is not None and sym:
                    rec[best + "_sym2"] = sym
        rec["food_name"] = "".join(name_parts).strip()
        out.append(rec)
        masks.append(intset)
    return out, masks
