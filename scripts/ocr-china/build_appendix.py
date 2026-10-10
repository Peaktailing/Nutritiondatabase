"""全量抽取附录表:氨基酸 / 脂肪酸 / 样品描述 → CSV。"""
import csv, json, os, pickle, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from appendix import detect_table_type, extract      # noqa: E402
from anchor13 import is_data_row                      # noqa: E402

# 各表输出列(中文表头)
OUT_COLS = {
    "amino_acid": [
        ("food_code", "食物编码", ""), ("food_name", "食物名称", ""),
        ("water_g", "水分", "g"), ("protein_g", "蛋白质", "g"),
        ("ile_mg", "异亮氨酸", "mg"), ("leu_mg", "亮氨酸", "mg"),
        ("lys_mg", "赖氨酸", "mg"), ("met_mg", "蛋氨酸", "mg"),
        ("cys_mg", "胱氨酸", "mg"), ("saa_mg", "含硫氨基酸SAA", "mg"),
        ("phe_mg", "苯丙氨酸", "mg"), ("tyr_mg", "酪氨酸", "mg"),
        ("aaa_mg", "芳香族氨基酸AAA", "mg"), ("thr_mg", "苏氨酸", "mg"),
        ("trp_mg", "色氨酸", "mg"), ("val_mg", "缬氨酸", "mg"),
        ("his_mg", "组氨酸", "mg"), ("arg_mg", "精氨酸", "mg"),
        ("ala_mg", "丙氨酸", "mg"), ("asp_mg", "天冬氨酸", "mg"),
        ("glu_mg", "谷氨酸", "mg"), ("gly_mg", "甘氨酸", "mg"),
        ("pro_mg", "脯氨酸", "mg"), ("ser_mg", "丝氨酸", "mg"),
    ],
    "fatty_acid": [
        ("food_code", "食物编码", ""), ("food_name", "食物名称", ""),
        ("fat_g", "脂肪", "g"), ("fa_total_g", "总脂肪酸", "g"),
        ("sfa_g", "饱和脂肪酸SFA", "g"), ("mufa_g", "单不饱和脂肪酸MUFA", "g"),
        ("pufa_g", "多不饱和脂肪酸PUFA", "g"), ("fa_unk_g", "未明确脂肪酸", "g"),
        ("c40_g", "丁酸4:0", "g"), ("c60_g", "己酸6:0", "g"),
        ("c80_g", "辛酸8:0", "g"), ("c100_g", "癸酸10:0", "g"),
        ("c120_g", "月桂酸12:0", "g"), ("c140_g", "肉豆蔻酸14:0", "g"),
        ("c150_g", "十五碳酸15:0", "g"), ("c160_g", "棕榈酸16:0", "g"),
        ("c170_g", "十七碳酸17:0", "g"), ("c180_g", "硬脂酸18:0", "g"),
        ("c200_g", "花生酸20:0", "g"), ("c220_g", "山嵛酸22:0", "g"),
        ("c240_g", "木焦油酸24:0", "g"),
        ("c141_g", "肉豆蔻油酸14:1", "g"), ("c161_g", "棕榈油酸16:1", "g"),
        ("c181_g", "油酸18:1", "g"), ("c201_g", "二十碳烯酸20:1", "g"),
        ("c221_g", "芥酸22:1", "g"),
        ("c182_g", "亚油酸18:2", "g"), ("c183_g", "亚麻酸18:3", "g"),
        ("c204_g", "花生四烯酸20:4", "g"),
        ("c205_g", "EPA 20:5", "g"), ("c226_g", "DHA 22:6", "g"),
    ],
    "sample_desc": [
        ("food_code", "食物编码", ""), ("food_name", "食物名称", ""),
        ("food_desc", "食物描述", ""), ("sample_process", "样品处理", ""),
        ("data_source", "数据来源", ""), ("sampling_date", "采样日期", ""),
        ("sampling_place", "采样地点", ""), ("origin", "产地", ""),
    ],
}

FILE_NAME = {
    "amino_acid": "附录_食物氨基酸含量.csv",
    "fatty_acid": "附录_食物脂肪酸含量.csv",
    "sample_desc": "附录_食物样品描述.csv",
}


def main():
    with open(os.path.join(BASE, "grid_cache.pkl"), "rb") as f:
        cache = pickle.load(f)

    merged = {t: {} for t in OUT_COLS}
    stats = Counter()
    for k in sorted(cache, key=lambda z: (z.split(":")[0], int(z.split(":")[1]))):
        rows = cache[k]["rows"]
        if not any(is_data_row(r) for r in rows):
            continue
        t = detect_table_type(rows)
        if t is None:
            continue
        recs = extract(rows, t)
        if not recs:
            stats[f"{t}_empty"] += 1
            continue
        stats[f"{t}_pages"] += 1
        for r in recs:
            code = r["food_code"]
            tgt = merged[t].setdefault(code, {"food_code": code, "food_name": ""})
            if len(r.get("food_name") or "") > len(tgt["food_name"]):
                tgt["food_name"] = r["food_name"]
            for kk, vv in r.items():
                if kk in ("food_code", "food_name") or vv is None:
                    continue
                if kk not in tgt or tgt[kk] is None:
                    tgt[kk] = vv

    print("统计:", dict(stats))
    for t, recs in merged.items():
        rows = sorted(recs.values(), key=lambda z: z["food_code"])
        cols_def = OUT_COLS[t]
        cols = [zh + (f"({u})" if u else "") for _, zh, u in cols_def]
        out = os.path.join(BASE, FILE_NAME[t])
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                row = {}
                for key, zh, u in cols_def:
                    row[zh + (f"({u})" if u else "")] = r.get(key)
                w.writerow(row)
        nf = sum(1 for r in rows
                 if sum(1 for kk, vv in r.items() if kk not in ("food_code", "food_name") and vv is not None) >= 3)
        print(f"{t}: {len(rows)} 条 -> {out}  (有效>=3字段: {nf})")


if __name__ == "__main__":
    main()
