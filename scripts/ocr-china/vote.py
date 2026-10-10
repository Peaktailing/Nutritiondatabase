"""多页表头投票 —— 用跨页一致性消除单页 OCR 抖动。

思路:
同一 book's 同一分类内,连续页面的表头文本几乎相同。
单页 OCR 可能漏检某个表头词,但几十页投票后,真实表头会稳定出现。

做法:
1. 对每一页,提取「表头 token → 字段」的候选(不依赖 x 对齐,只看 token 命中)
2. 统计每个字段在多少比例的页面里出现过 → 得到该区段的「可靠字段集」
3. 再对每页,把可靠字段集按该页的 token x 顺序排列,与数据列做序列对齐

这样单页缺失不影响最终命名,鲁棒性大幅提升。
"""
from collections import Counter, defaultdict
from anchor3 import hits_in
from anchor6 import en_hits
from anchor13 import UNIT_RE, X_LO, X_HI, OIDX, is_data_row


def page_tokens(page_rows, header_scan=14):
    """该页表头区所有 (x, [字段]) 候选。"""
    out = []
    for row in page_rows[:header_scan]:
        if is_data_row(row):
            break
        for it in row:
            if not (X_LO <= it["x"] <= X_HI):
                continue
            t = it["t"].strip()
            if not t or UNIT_RE.match(t):
                continue
            en = en_hits(t)
            ks = [k for k, _ in en] if en else [k for k, _ in hits_in(t)]
            if ks:
                out.append((it["x"], sorted(ks, key=lambda k: OIDX.get(k, 999))))
    return out


def vote_fields(all_page_tokens, min_ratio=0.55):
    """跨页投票 → 可靠字段集(返回 set)。"""
    if not all_page_tokens:
        return set()
    total = len(all_page_tokens)
    cnt = Counter()
    for toks in all_page_tokens:
        seen = set()
        for _, ks in toks:
            for k in ks:
                seen.add(k)
        cnt.update(seen)
    # 阈值:出现在 >= min_ratio 比例页面的字段才算可靠
    thr = max(2, int(total * min_ratio))
    return {k for k, c in cnt.items() if c >= thr}, cnt, total


def template_for_group(group_pages_tokens):
    """一组页面(同区段)的列序模板。

    返回:字段按 x 顺序的众数序列。
    做法:对每页生成 (字段序列),取「按位置对齐的众数」。
    """
    rel, cnt, total = vote_fields(group_pages_tokens)
    if not rel:
        return None
    # 收集每页中「属于可靠集」的字段序列
    seqs = []
    for toks in group_pages_tokens:
        seq = []
        for x, ks in sorted(toks, key=lambda t: t[0]):
            for k in ks:
                if k in rel and k not in seq:
                    seq.append(k)
        if seq:
            seqs.append(seq)
    if not seqs:
        return None
    # 位置众数
    maxlen = max(len(s) for s in seqs)
    template = []
    for pos in range(maxlen):
        c = Counter(s[pos] for s in seqs if len(s) > pos)
        if not c:
            break
        # 该位置上,若众数占比 >= 40% 则采纳
        field, n = c.most_common(1)[0]
        if n >= len(seqs) * 0.4:
            template.append(field)
    return template


def group_by_signature(page_rows_list, min_gap_hint=True):
    """把页面按「粗略字段集」分组(区段划分)。"""
    sigs = []
    for rows in page_rows_list:
        toks = page_tokens(rows)
        fields = set()
        for _, ks in toks:
            fields.update(ks)
        sigs.append(frozenset(fields))
    return sigs
