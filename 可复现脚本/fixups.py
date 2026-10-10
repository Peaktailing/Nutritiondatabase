"""专项数值纠错 —— 处理已知的高频 OCR 错误模式。

⚠ 重要教训(实测回归):
   「page_median_guard」(按本页中位数把偏小值×10)和「fix_underflow」(字段下界回乘)
   会把**真实的小数值**误判为错误。实测把小麦蛋白质 11.9 改成 1.19、
   梗米粥 1.1、马铃薯(烤) 1.8 等合理值全部改错。
   原因:许多食物本身蛋白/脂肪含量就是 1~2g,而"偏小"是这类食物的正常形态。
   结论:**只做守恒驱动的 ÷10 修复(有物理证据),不做任何 ×10 的反向猜测**。
   仅保留「食部%」这一有明确先验分布依据的修正。
"""
from validate import score_record, RANGES

# 食部% 的先验分布(实测):100 占多数,其余为 80~99 的整数
EDIBLE_DEFAULT = 100.0


def fix_edible(rec):
    """食部%(edible_pct)修正。

    判定为 OCR 错误的形态(基于实测分布):
      - 0 < v < 1.5        如 0.77  —— 小数点错位
      - v < 50 且非整数     如 3.1 / 10.85 / 2.05 —— 实为 100
    真实值中 46.0(玉米鲜)、41.0 等整数会保留不动。
    """
    v = rec.get("edible_pct")
    if v is None:
        return rec, None
    if 0 < v < 1.5:
        rec = dict(rec)
        rec["edible_pct"] = EDIBLE_DEFAULT
        return rec, "edible"
    if v < 50 and abs(v - round(v)) > 1e-6:
        rec = dict(rec)
        rec["edible_pct"] = EDIBLE_DEFAULT
        return rec, "edible"
    return rec, None


# —— 以下两个函数经实测确认有害,已停用 ——
def fix_underflow(rec):
    """停用:曾把真实小数值误改 ×10。"""
    return rec, None


def page_median_guard(recs, fields=None):
    """停用:曾把小麦蛋白 11.9 → 1.19。"""
    return recs, 0


def reconcile(recs):
    """跨页合并后的一致性协调:同一编码多来源时,选守恒得分最好的组合。"""
    by = {}
    for r in recs:
        by.setdefault(r["food_code"], []).append(r)
    out = []
    for code, lst in by.items():
        if len(lst) == 1:
            out.append(lst[0])
            continue
        best, best_sc = None, None
        for r in lst:
            _, sc = score_record(r, strict=False)
            if best_sc is None or sc > best_sc:
                best, best_sc = r, sc
        # 合并所有非空字段,但对冲突字段取 best 的值
        merged = dict(best)
        for r in lst:
            for k, v in r.items():
                if k.startswith("_") or v is None:
                    continue
                if merged.get(k) is None:
                    merged[k] = v
        out.append(merged)
    return out
