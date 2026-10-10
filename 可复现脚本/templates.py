"""表头模板 —— 局部窗口投票(最终修正版)。

问题诊断:
原书一个「分类」的表头会横跨几十页连续出现,不同分类的表头不同。
全局统计会把不同表头混在一起做位置众数 → 顺序被稀释、字段错位。
(如 MACRO 段里混入了 vit_e_total_mg,因为有些页是别的区段)

正确做法:
1. 把页面按「表头签名」切成**连续区段组**(同一分类的页天然连续)
2. 每组独立做位置众数 → 该组专属模板
3. 每页用其所属组的模板对齐

这样每组只需 3~10 页样本即可得出稳定模板,且不会被其他分类稀释。
"""
from collections import Counter, defaultdict
from vote import page_tokens
from pipeline2 import segment_of

EXCLUDE = {"food_code", "food_name", "comment"}

# 区段内的细分签名:用出现最多的几个字段作为分类依据
def sub_signature(rows, seg):
    toks = page_tokens(rows)
    fs = set()
    for _, ks in toks:
        fs.update(ks)
    if seg == "MACRO":
        # 宏量段再按「是否有饱和脂肪/脂肪酸细分」细分
        if fs & {"fat_sat_g", "fat_mono_g", "fat_poly_g"}:
            return "MACRO_FAT"
        if "vit_a_ug" in fs or "beta_carotene_ug" in fs:
            return "MACRO_VIT"
        return "MACRO_MAIN"
    if seg == "MICRO":
        if "vit_e_gamma_g" in fs or "vit_e_alpha_g" in fs or "vit_e_te_mg" in fs:
            return "MICRO_VE"
        if fs & {"calcium_mg", "phosphorus_mg", "potassium_mg"}:
            return "MICRO_MIN"
        return "MICRO_OTHER"
    return "OTHER"


def page_key(vol, page, rows):
    seg = segment_of(rows)
    return (vol, page, seg, sub_signature(rows, seg))


def group_pages(page_infos, gap=6):
    """把连续同区段的页聚成组。

    注意:传入的 page_infos 应已过滤掉附录表(氨基酸/脂肪酸/样品描述),
    否则附录表的表头会污染模板。
    """
    groups = []
    cur = []
    prev_page = None
    for vol, page, rows in page_infos:
        seg = segment_of(rows)
        # MACRO 段内部按是否有脂肪酸细分再分;MICRO 段统一
        if seg == "MACRO":
            toks = page_tokens(rows)
            fs = set()
            for _, ks in toks:
                fs.update(ks)
            sig = "MACRO_FAT" if (fs & {"fat_sat_g", "fat_mono_g", "fat_poly_g"}) \
                else "MACRO_MAIN"
        else:
            sig = seg
        key = (vol, sig)
        if prev_page is not None and (page - prev_page > gap or key != cur[-1][3]):
            if cur:
                groups.append(cur)
            cur = []
        cur.append((vol, page, rows, key))
        prev_page = page
    if cur:
        groups.append(cur)
    return groups


def template_from_group(group, min_count=1):
    """一组页 → 字段顺序模板(位置众数)。"""
    if len(group) < 1:
        return []
    toks = [page_tokens(r) for (_, _, r, _) in group]
    # 统计每字段出现页数
    cnt = Counter()
    for t in toks:
        seen = set()
        for _, ks in t:
            seen.update(ks)
        cnt.update(seen)
    total = len(toks)
    # 至少出现在 1 页,且出现率 >= 40%(组内样本少,阈值放低)
    rel = {f for f, c in cnt.items() if c >= max(min_count, total * 0.4)}

    seqs = []
    for t in toks:
        seq, seen = [], set()
        for x, ks in sorted(t, key=lambda z: z[0]):
            for f in ks:
                if f in rel and f not in seen and f not in EXCLUDE:
                    seen.add(f)
                    seq.append(f)
        if seq:
            seqs.append(seq)
    if not seqs:
        return []
    maxlen = max(len(s) for s in seqs)
    tpl = []
    for pos in range(maxlen):
        c = Counter(s[pos] for s in seqs if len(s) > pos)
        if not c:
            break
        f, n = c.most_common(1)[0]
        if n >= max(1, len(seqs) * 0.5):
            tpl.append(f)
    # 去重保序
    seen, out = set(), []
    for f in tpl:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def build_all_templates(page_infos, gap=6):
    """→ {(vol,page): template}"""
    result = {}
    for grp in group_pages(page_infos, gap):
        tpl = template_from_group(grp)
        for vol, page, rows, key in grp:
            result[(vol, page)] = tpl
    return result
