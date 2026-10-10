"""最终构建:从 OCR 缓存生成结构化营养数据库。

输出:
  1. food_nutrition.json  —— 完整记录(带质量标记)
  2. food_nutrition.csv   —— 扁平表格,便于导入数据库/Excel
  3. quality_report.txt   —— 质量统计报告
"""
import csv, json, os, pickle, sys
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from pipeline2 import build_templates, process, segment_of      # noqa: E402
from schema import NUTRIENT_FIELDS, SYMBOL_MEANING               # noqa: E402
from validate import score_record, RANGES                        # noqa: E402

CACHE = os.path.join(BASE, "grid_cache.pkl")

CSV_COLS = (
    ["food_code", "food_name", "volume", "source", "edible_pct"]
    + [k for k, *_ in NUTRIENT_FIELDS]
    + ["_n_fields", "_n_segments", "_quality_score"]
)


def symbol_columns(rec):
    """收集该记录里出现的特殊符号标记。"""
    out = []
    for k, v in rec.items():
        if k.endswith("_sym") or k.endswith("_sym2"):
            field = k.rsplit("_sym", 1)[0]
            if v and not v.startswith("unparsed"):
                out.append(f"{field}:{v}")
    return out


def classify(rec):
    """按食物编码前两位推断大类。

    映射依据本次实测(第一册 844 条记录的编码段与实际食品核对):
      01 谷薯类      02 薯类及淀粉制品   03 豆类及豆制品
      04 蔬菜类      05 菌藻类          06 水果类
      07 坚果、种子类 08 调味品           09 油脂类
      19 油脂类(第二册前的油脂段)
    未知前缀统一归「其他」。
    """
    code = rec.get("food_code") or ""
    if len(code) < 2:
        return "未知"
    pre2 = code[:2]
    # 第一册(植物性食物)
    if pre2 == "01":
        return "谷薯类"
    if pre2 == "02":
        return "薯类及淀粉制品"
    if pre2 == "03":
        return "豆类及豆制品"
    if pre2 == "04":
        return "蔬菜类"
    if pre2 == "05":
        return "菌藻类"
    if pre2 == "06":
        return "水果类"
    if pre2 == "07":
        return "坚果、种子类"
    # 第二册(动物性食物)—— 编码段与植物性完全不同
    if pre2 in ("08", "09", "10"):
        return "畜禽肉及制品"
    if pre2 == "11":
        return "蛋类及制品"
    if pre2 == "12":
        return "鱼虾蟹贝类"
    if pre2 == "13":
        return "乳类及制品"
    if pre2 == "19":
        return "油脂类"
    if pre2 == "21":
        return "其他(药食两用等)"
    return "其他"


def main():
    with open(CACHE, "rb") as f:
        cache = pickle.load(f)
    keys = sorted(cache)
    print(f"cache pages: {len(keys)}")

    templates = build_templates(cache, keys)
    print("\n区段模板:")
    for s, t in templates.items():
        print(f"  {s} ({len(t)}): {t}")

    recs, stats = process(cache, keys, templates)
    print(f"\n数据页={stats['pages']} 修复={stats['fixes']} 记录={len(recs)}")

    # 补充分类与符号
    for r in recs:
        r["category"] = classify(r)
        syms = symbol_columns(r)
        r["_symbols"] = ";".join(syms)

    # 质量统计
    q = Counter()
    for r in recs:
        nf = r["_n_fields"]
        if nf >= 25:
            q["优(≥25字段)"] += 1
        elif nf >= 18:
            q["良(18-24)"] += 1
        elif nf >= 12:
            q["中(12-17)"] += 1
        else:
            q["差(<12)"] += 1

    # 保存
    jf = os.path.join(BASE, "food_nutrition.json")
    with open(jf, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)

    cf = os.path.join(BASE, "food_nutrition.csv")
    with open(cf, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(recs, key=lambda z: z["food_code"]):
            row = {k: r.get(k) for k in CSV_COLS}
            row["source"] = "中国食物成分表 标准版 第6版"
            row["volume"] = "每100g可食部"
            w.writerow(row)

    rf = os.path.join(BASE, "quality_report.txt")
    with open(rf, "w", encoding="utf-8") as f:
        f.write("《中国食物成分表 标准版 第6版》营养数据库 构建报告\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"总记录数: {len(recs)}\n")
        f.write(f"数据页数: {stats['pages']}\n")
        f.write(f"数值修正次数: {stats['fixes']}\n\n")
        f.write("字段完整度分布:\n")
        for k in ["优(≥25字段)", "良(18-24)", "中(12-17)", "差(<12)"]:
            f.write(f"  {k}: {q.get(k,0)} ({q.get(k,0)*100//max(1,len(recs))}%)\n")
        f.write("\n分类分布:\n")
        for k, v in Counter(r["category"] for r in recs).most_common():
            f.write(f"  {k}: {v}\n")
        f.write("\n数据符号说明:\n")
        for k, v in SYMBOL_MEANING.items():
            f.write(f"  {k}: {v}\n")

    print("\n字段完整度:")
    for k in ["优(≥25字段)", "良(18-24)", "中(12-17)", "差(<12)"]:
        print(f"  {k}: {q.get(k,0)}")
    print("\n分类:")
    for k, v in Counter(r["category"] for r in recs).most_common():
        print(f"  {k}: {v}")
    print(f"\nsaved:\n  {jf}\n  {cf}\n  {rf}")

    # 抽样展示
    print("\n抽样:")
    for r in sorted(recs, key=lambda z: z["food_code"])[:5]:
        print(f"  {r['food_code']} {r['food_name'][:14]:16s} "
              f"能量={r.get('energy_kcal')} 蛋白={r.get('protein_g')} "
              f"脂肪={r.get('fat_g')} 碳水={r.get('carb_g')} "
              f"钙={r.get('calcium_mg')} 字段={r['_n_fields']}")


if __name__ == "__main__":
    main()
