"""附录表抽取:氨基酸 / 脂肪酸 / 样品描述。

三类表的表头特征(实测):
1. 氨基酸表(mg/100g 可食部)
   食物编码 | 食物名称 | 水分 | 蛋白质 | 异亮氨酸 Ile | 亮氨酸 Leu | 赖氨酸 Lys |
   含硫氨基酸SAA(蛋氨酸Met + 胱氨酸Cys) | 芳香族氨基酸AAA(苯丙氨酸Phe + 酪氨酸Tyr) |
   苏氨酸 Thr | 色氨酸 Trp | 缬氨酸 Val ...
2. 脂肪酸表(g/100g 可食部)
   食物编码 | 食物名称 | 脂肪 | 总脂肪酸Total | SFA(饱和) | MUFA(单不饱和) |
   PUFA(多不饱和) | Unk | 4:0 | 6:0 | 8:0 | 10:0 | 12:0 | 14:0 | 16:0 | 18:0 ...
3. 样品描述表
   食物编码 | 食物名称 | 食物描述 | 样品处理 | 数据来源 | 采样日期 | 采样地点 | 产地

策略:复用主流程的「列位置检测 + 表头锚定」,但换成各表专属的字段词表。
"""
import re
from collections import Counter
import statistics

# ——————————————————————— 字段词表 ———————————————————————
# OCR 常见误识修正(表头专用,先替换再匹配)
ZH_OCR_FIX = [
    ("充氨酸", "亮氨酸"), ("亮氨酸", "亮氨酸"),
    ("合硫氨基酸", "含硫氨基酸"), ("胱氮酸", "胱氨酸"),
    ("苯丙氮酸", "苯丙氨酸"), ("酷氨酸", "酪氨酸"),
    ("苏氮酸", "苏氨酸"), ("色氨酸", "色氨酸"),
    ("缴氨酸", "缬氨酸"), ("组氮酸", "组氨酸"),
    ("精氮酸", "精氨酸"), ("天冬氮酸", "天冬氨酸"),
    ("谷氮酸", "谷氨酸"), ("甘氮酸", "甘氨酸"),
    ("腑氨酸", "脯氨酸"), ("丝氮酸", "丝氨酸"),
    ("内氨酸", "丙氨酸"),
]

AA_FIELDS = [
    ("water_g",   r"水分",            r"water"),
    ("protein_g", r"蛋白质",          r"protein"),
    ("ile_mg",    r"异亮氨酸",        r"\bile\b|isoleucine"),
    ("leu_mg",    r"亮氨酸",          r"\bleu\b|leucine"),
    ("lys_mg",    r"赖氨酸",          r"\bly[sz]\b|lysine"),
    ("met_mg",    r"蛋氨酸|甲硫氨酸", r"\bmet\b|methionine"),
    ("cys_mg",    r"胱氨酸",          r"\bcys\b|cystine"),
    ("saa_mg",    r"含硫氨基酸",      r"saa"),
    ("phe_mg",    r"苯丙氨酸",        r"\bphe\b|phenylalanine"),
    ("tyr_mg",    r"酪氨酸",          r"\btyr\b|tyrosine"),
    ("aaa_mg",    r"芳香族氨基酸",    r"aaa"),
    ("thr_mg",    r"苏氨酸",          r"\bthr\b|threonine"),
    ("trp_mg",    r"色氨酸",          r"\btr[yp]\b|tryptophan"),
    ("val_mg",    r"缬氨酸",          r"\bval\b|valine"),
    ("his_mg",    r"组氨酸",          r"\bhis\b|histidine"),
    ("arg_mg",    r"精氨酸",          r"\barg\b|arginine"),
    ("ala_mg",    r"丙氨酸",          r"\bala\b|alanine"),
    ("asp_mg",    r"天冬氨酸",        r"\basp\b|aspartic"),
    ("glu_mg",    r"谷氨酸",          r"\bglu\b|glutamic"),
    ("gly_mg",    r"甘氨酸",          r"\bgly\b|glycine"),
    ("pro_mg",    r"脯氨酸",          r"\bpro\b|proline"),
    ("ser_mg",    r"丝氨酸",          r"\bser\b|serine"),
    ("total_aa_mg", r"氨基酸总量",    r"total"),
]

FA_FIELDS = [
    ("fat_g",        r"^脂肪$|脂肪",        r"^fat|\bfat\b"),
    ("fa_total_g",   r"总脂肪酸|脂肪酸总量", r"total"),
    ("sfa_g",        r"饱和脂肪",            r"\bsfa\b|saturated"),
    ("mufa_g",       r"单不饱和",            r"\bmufa\b|mono"),
    ("pufa_g",       r"多不饱和",            r"\bpufa\b|poly"),
    ("fa_unk_g",     r"未检出|不明",         r"\bunk\b"),
    ("c40_g",        r"4:0|4：0",            r"4:0|4：0"),
    ("c60_g",        r"6:0|6：0",            r"6:0|6：0"),
    ("c80_g",        r"8:0|8：0",            r"8:0|8：0"),
    ("c100_g",       r"10:0|10：0",          r"10:0|10：0"),
    ("c120_g",       r"12:0|12：0",          r"12:0|12：0"),
    ("c140_g",       r"14:0|14：0",          r"14:0|14：0"),
    ("c150_g",       r"15:0|15：0",          r"15:0|15：0"),
    ("c160_g",       r"16:0|16：0",          r"16:0|16：0"),
    ("c170_g",       r"17:0|17：0",          r"17:0|17：0"),
    ("c180_g",       r"18:0|18：0",          r"18:0|18：0"),
    ("c200_g",       r"20:0|20：0",          r"20:0|20：0"),
    ("c220_g",       r"22:0|22：0",          r"22:0|22：0"),
    ("c240_g",       r"24:0|24：0",          r"24:0|24：0"),
    ("c141_g",       r"14:1|14：1",          r"14:1|14：1"),
    ("c161_g",       r"16:1|16：1",          r"16:1|16：1"),
    ("c181_g",       r"18:1|18：1",          r"18:1|18：1"),
    ("c201_g",       r"20:1|20：1",          r"20:1|20：1"),
    ("c221_g",       r"22:1|22：1",          r"22:1|22：1"),
    ("c182_g",       r"18:2|18：2",          r"18:2|18：2"),
    ("c183_g",       r"18:3|18：3",          r"18:3|18：3"),
    ("c204_g",       r"20:4|20：4",          r"20:4|20：4"),
    ("c205_g",       r"20:5|20：5",          r"20:5|20：5"),
    ("c226_g",       r"22:6|22：6",          r"22:6|22：6"),
]

SAMPLE_FIELDS = [
    ("food_desc",      r"食物描述|食物描达|食物品",   r"description"),
    ("sample_process", r"样品处理|品处理",            r"sample\s*process|process"),
    ("data_source",    r"数据来源|致据来源|数据来",   r"data\s*source|source"),
    ("sampling_date",  r"采样日期",                    r"sampling\s*date|date"),
    ("sampling_place", r"采样地点|采祥地点|采样地",   r"sampling\s*place|place"),
    ("origin",         r"产地",                        r"origin|producing"),
]

COMMON = [
    ("food_code", r"食物编码|食物端码|食物代吗|食物端编码", r"food\s*code"),
    ("food_name", r"食物名称",                              r"food\s*name"),
]

TABLES = {
    "amino_acid":  COMMON + AA_FIELDS,
    "fatty_acid":  COMMON + FA_FIELDS,
    "sample_desc": COMMON + SAMPLE_FIELDS,
}

COMPILED = {
    t: [(k, re.compile(z, re.I) if z else None, re.compile(e, re.I))
        for k, z, e in fields]
    for t, fields in TABLES.items()
}

# 单位行(不参与命名)
UNIT_RE = re.compile(r"^(mg|g|%|mg/100g|g/100g|kcal|kj|ug)$", re.I)
CODE_RE = re.compile(r"^\d{6}$")


def detect_table_type(page_rows, header_scan=14):
    """→ ('amino_acid'|'fatty_acid'|'sample_desc'|None)"""
    blob = " ".join(it["t"].strip()
                    for r in page_rows[:header_scan] for it in r)
    if re.search(r"氨基酸", blob):
        return "amino_acid"
    if re.search(r"脂肪酸", blob):
        return "fatty_acid"
    if re.search(r"样品处理|采样日期|食物描述", blob):
        return "sample_desc"
    return None


def _hits(text, table):
    t = text
    if table == "amino_acid":
        for a, b in ZH_OCR_FIX:
            t = t.replace(a, b)
    out = {}
    for k, zc, ec in COMPILED[table]:
        best = None
        for rx, w in ((zc, 1.0), (ec, 1.2)):
            if rx is None:
                continue
            m = rx.search(text)
            if m:
                sc = len(m.group(0)) * w
                if best is None or sc > best[0]:
                    best = (sc, m.start())
        if best:
            out[k] = best[1]
    return sorted(out.items(), key=lambda z: z[1])


def page_layout(page_rows, min_gap=42, name_hi=700):
    """数据行 x 聚类(复用主流程逻辑)。"""
    from anchor13 import is_data_row
    drows = [r for r in page_rows if is_data_row(r)]
    if not drows:
        return None
    xs = [it["x"] for r in drows for it in r if it["t"].strip()]
    if not xs:
        return None
    s = sorted(xs)
    groups = [[s[0]]]
    for v in s[1:]:
        if v - groups[-1][-1] <= min_gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    cents = [statistics.median(g) for g in groups]
    code_x = cents[0]
    name_cols = [c for c in cents[1:] if 320 < c < 780]
    numeric = [c for c in cents if c >= 780]
    name_x = (min(name_cols) + max(name_cols)) / 2 if name_cols else None
    return dict(code_x=code_x, name_x=name_x, numeric=numeric)


def build_columns(page_rows, table, header_scan=14):
    lay = page_layout(page_rows)
    if not lay:
        return None, []
    # 表头 token → 字段
    cand = {}
    for r in page_rows[:header_scan]:
        for it in r:
            t = it["t"].strip()
            if not t or UNIT_RE.match(t):
                continue
            if not (150 <= it["x"] <= 3120):
                continue
            hs = _hits(t, table)
            if hs:
                x = it["x"]
                ks = [k for k, _ in hs]
                if x not in cand or len(ks) > len(cand[x]):
                    cand[x] = ks
    # 按 x 排序展开
    fields, seen = [], set()
    for x in sorted(cand):
        for k in cand[x]:
            if k in seen:
                continue
            seen.add(k)
            fields.append((x, k))
    # 用 FIELD 顺序约束 + 位置对齐
    order = [k for k, *_ in TABLES[table]]
    oidx = {k: i for i, k in enumerate(order)}
    fields.sort(key=lambda t: oidx.get(t[1], 999))

    cols = []
    numeric = lay["numeric"]

    # 附录表列序固定 → 直接用「本页识别到的字段序列」按位置顺序对齐数值列。
    # 只要识别出的字段数 >= 数值列数,就顺序配对(多余字段截断)。
    seq = [k for _, k in fields if k not in ("food_code", "food_name")]
    if len(seq) >= len(numeric):
        for i, cx in enumerate(numeric):
            cols.append((cx, seq[i]))
        return lay, cols

    # 字段不足:退化到 x 就近匹配
    for cx in numeric:
        best, bd = None, 1e9
        for fx, k in fields:
            d = abs(fx - cx)
            if d < bd and d <= 140:
                bd, best = d, k
        cols.append((cx, best))
    return lay, cols


def extract(page_rows, table):
    """抽取该页附录表记录。"""
    lay, cols = build_columns(page_rows, table)
    if not lay or not cols:
        return []
    from anchor13 import is_data_row
    out = []
    for row in page_rows:
        if not is_data_row(row):
            continue
        code = None
        for it in row:
            m = CODE_RE.match(it["t"].strip())
            if m:
                code = m.group(0)
                break
        if not code:
            continue
        rec = {"food_code": code}
        name_parts = []
        for it in row:
            t = it["t"].strip()
            if not t or CODE_RE.match(t):
                continue
            x = it["x"]
            # 名称列
            if lay["name_x"] and abs(x - lay["name_x"]) <= 200:
                if not re.match(r"^[\d.]+$", t):
                    name_parts.append(t)
                continue
            # 归属列
            best, bd = None, 1e9
            for cx, key in cols:
                d = abs(cx - x)
                if d < bd:
                    bd, best = d, key
            if best and bd <= 60:
                # 样品描述表的文本列:直接存字符串
                if table == "sample_desc" and best in (
                        "food_desc", "sample_process", "data_source",
                        "sampling_date", "sampling_place", "origin"):
                    if rec.get(best):
                        rec[best] += " " + t
                    else:
                        rec[best] = t
                    continue
                v = _num(t)
                if v is not None and rec.get(best) is None:
                    rec[best] = v
            elif best is None and table == "sample_desc" and bd <= 200:
                # 描述表:未命名列可能是产地等文本
                pass
        rec["food_name"] = "".join(name_parts).strip()
        out.append(rec)
    return out


def _num(s):
    s = s.strip().replace(" ", "")
    for ch in ["—", "–", "－"]:
        s = s.replace(ch, "")
    if s in ("Tr", "tr", "TR", "un", "*", ""):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(1))
    return None
