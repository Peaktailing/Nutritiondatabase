"""主流程 v3 —— 局部模板 + 列映射 + 抽取 + 校验修复 + 跨页合并。"""
import os, pickle, sys
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from anchor13 import is_data_row, page_layout, align_map          # noqa: E402
from anchor14 import fill_unknown                                 # noqa: E402
from templates import build_all_templates, group_pages            # noqa: E402
from vote import page_tokens                                      # noqa: E402
from extract2 import extract_records_v2                          # noqa: E402
from postfix4 import fix_page as fix_num, macro_sum              # noqa: E402
from misalign import try_swap, _avg_score                        # noqa: E402
from validate import score_record, RANGES                         # noqa: E402
from fixups import fix_edible, fix_underflow, page_median_guard   # noqa: E402
from colprec import fix_page_by_column                          # noqa: E402
from tabletype import should_process                            # noqa: E402

EXCLUDE = {"food_code", "food_name", "comment"}


def collect_infos(cache):
    """按页序收集 (vol, page, rows) —— 只含主营养表的数据页。

    必须过滤附录表(氨基酸/脂肪酸/样品描述),否则:
      1. 模板被污染
      2. 氨基酸数值(如异亮氨酸 900)被误当营养字段
    """
    from tabletype import should_process
    infos = []
    keys = sorted(cache, key=lambda z: (z.split(":")[0], int(z.split(":")[1])))
    for k in keys:
        vol, pg = k.split(":")
        rows = cache[k]["rows"]
        if not any(is_data_row(r) for r in rows):
            continue
        ok, _ = should_process(rows)
        if not ok:
            continue
        infos.append((vol, int(pg), rows))
    return infos


def columns_for_page(rows, template):
    """模板字段 + 本页 token x → 列映射。"""
    lay = page_layout(rows)
    if not lay:
        return None, []
    toks = page_tokens(rows)
    present = []
    for x, ks in sorted(toks, key=lambda z: z[0]):
        for f in ks:
            if f in template and f not in EXCLUDE and f not in [p[1] for p in present]:
                present.append((x, f))
    if not present:
        return lay, []
    tidx = {f: i for i, f in enumerate(template)}
    present.sort(key=lambda t: tidx.get(t[1], 999))
    amap = align_map(present, lay["numeric"])
    cols = [(cx, present[amap[j]][1] if j in amap else None)
            for j, cx in enumerate(lay["numeric"])]
    cols = fill_unknown(cols)
    return lay, cols


def run(cache, gap=20, use_swap=True):
    infos = collect_infos(cache)
    tpls = build_all_templates(infos, gap=gap)

    merged = {}
    stats = Counter()
    stats["swaps"] = 0
    for vol, page, rows in infos:
        # 0) 表类型判定:排除氨基酸/脂肪酸/样品描述等附录表
        #    否则附录表的数值会被误当营养字段(如异亮氨酸 900 → 某营养值)
        ok_type, why = should_process(rows)
        if not ok_type:
            stats["skip_non_main"] += 1
            continue
        tpl = tpls.get((vol, page)) or []
        if len(tpl) < 3:
            stats["skip_no_template"] += 1
            continue
        lay, cols = columns_for_page(rows, tpl)
        if not lay or not cols:
            stats["skip_no_layout"] += 1
            continue
        named = sum(1 for _, k in cols if k)
        if named < max(3, len(cols) * 0.45):
            stats["skip_few_named"] += 1
            continue

        recs, masks = extract_records_v2(rows, lay, cols)
        if not recs:
            continue

        # 0) 列级精度修复:用整页同列分布识别丢小数点(先于逐条修复,信息更充分)
        recs, ncol, _colinfo = fix_page_by_column(recs)

        # 1) 数值修复(丢小数点)
        recs, nfix = fix_num(recs)
        nfix += ncol
        # 1b) 页级中位数护栏(修正过度)
        recs, nmed = page_median_guard(recs)
        # 1c) 专项纠错(食部%、字段下界)
        out2 = []
        for r in recs:
            r, _n1 = fix_edible(r)
            r, _n2 = fix_underflow(r)
            out2.append(r)
        recs = out2
        nfix += nmed

        # 1d) 再次守恒校验(专项纠错后可能达标)
        recs, nfix2 = fix_num(recs)
        nfix += nfix2

        # 2) 列错位检测与交换
        if use_swap:
            def _ef(c, _rows=rows, _lay=lay):
                rr, _ = extract_records_v2(_rows, _lay, c)
                return fix_num(rr)[0]
            bc, brecs, bscore, nsw = try_swap(rows, lay, cols, _ef)
            if nsw:
                cols, recs = bc, fix_num(brecs)[0]
                stats["swaps"] += nsw

        stats["pages"] += 1
        stats["fixes"] += nfix

        for r in recs:
            _, sc = score_record(r, strict=False)
            code = r["food_code"]
            tgt = merged.setdefault(code, {"food_code": code, "food_name": "",
                                           "_pages": [], "_scores": []})
            tgt["_pages"].append(f"{vol}:{page}")
            nm = r.get("food_name") or ""
            if len(nm) > len(tgt["food_name"]):
                tgt["food_name"] = nm
            for kk, vv in r.items():
                if kk.startswith("_") or kk in ("food_code", "food_name"):
                    continue
                if vv is None:
                    continue
                rng = RANGES.get(kk)
                if rng and isinstance(vv, (int, float)) and vv > rng[1] * 1.05:
                    stats["out_of_range"] += 1
                    continue
                tgt[kk] = vv
            tgt["_scores"].append(sc)

    out = []
    for code, r in merged.items():
        scs = r.pop("_scores", [0])
        r["_pages"] = sorted(set(r["_pages"]))
        r["_n_pages"] = len(r["_pages"])
        r["_quality_score"] = round(sum(scs) / max(1, len(scs)), 1)
        r, _ = fix_edible(r)
        r, _ = fix_underflow(r)
        filled = sum(1 for kk, vv in r.items()
                     if not kk.startswith("_") and kk not in ("food_code", "food_name")
                     and vv is not None)
        r["_n_fields"] = filled
        r["_macro_sum"] = round(macro_sum(r), 1)
        out.append(r)
    return out, stats


def main():
    with open(os.path.join(BASE, "grid_cache.pkl"), "rb") as f:
        cache = pickle.load(f)
    recs, stats = run(cache)
    print("stats:", dict(stats))
    print("records:", len(recs))
    d = Counter()
    for r in recs:
        d[min(10, r["_n_fields"] // 5)] += 1
    print("字段数分布:", sorted(d.items()))
    outp = os.path.join(BASE, "merged_v3.json")
    import json
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    print("saved", outp)


if __name__ == "__main__":
    main()
