"""统计多页 OCR 框的 x 位置,推导稳定的全局列网格(列中心 + 边界)。

思路:
1. OCR 每页 → 文本框
2. 找出「数据行」:含 6 位食物编码的行
3. 收集该行所有框的 x 中心,做 1D 聚类(按间隙)
4. 跨页累积聚类,取高频列中心作为全局列网格
"""
import io, os, sys, json, zipfile, argparse, pickle
import numpy as np
from PIL import Image, ImageOps, ImageEnhance

BASE = os.path.dirname(os.path.abspath(__file__))


def prep(raw, rot=-90):
    im = Image.open(io.BytesIO(raw)).convert("L")
    im = im.rotate(rot, expand=True)
    w, h = im.size
    im = im.crop((int(w * 0.015), int(h * 0.012), int(w * 0.996), int(h * 0.988)))
    im = ImageOps.autocontrast(im, cutoff=1)
    im = ImageEnhance.Contrast(im).enhance(1.6)
    return im


def ocr_items(eng, arr):
    res, _ = eng(arr)
    items = []
    if not res:
        return items
    for entry in res:
        try:
            box, txt, conf = entry
            xs = [p[0] for p in box]; ys = [p[1] for p in box]
            t = txt.strip()
            if not t:
                continue
            items.append(dict(t=t, c=float(conf),
                              x=float(sum(xs) / 4), y=float(sum(ys) / 4),
                              x0=float(min(xs)), x1=float(max(xs)),
                              y0=float(min(ys)), y1=float(max(ys))))
        except Exception:
            continue
    return items


def group_rows(items, tol_frac=0.5):
    if not items:
        return []
    items = sorted(items, key=lambda d: d["y"])
    med_h = float(np.median([d["y1"] - d["y0"] for d in items]))
    tol = max(med_h * tol_frac, 6)
    rows, cur = [], [items[0]]
    for d in items[1:]:
        if abs(d["y"] - cur[-1]["y"]) <= tol:
            cur.append(d)
        else:
            rows.append(cur); cur = [d]
    rows.append(cur)
    return [sorted(r, key=lambda d: d["x"]) for r in rows]


def is_data_row(row):
    """数据行判据:含 6 位食物编码。"""
    for d in row:
        s = d["t"].replace(" ", "")
        if len(s) == 6 and s.isdigit():
            return True
    return False


def collect(vol, pages, cache):
    from rapidocr_onnxruntime import RapidOCR
    z = zipfile.ZipFile(os.path.join(BASE, vol))
    eng = RapidOCR()
    out = {}
    for i, p in enumerate(pages, 1):
        key = f"{vol}:{p}"
        if key in cache:
            out[p] = cache[key]; continue
        im = prep(z.read(f"index-{p}_1.jpg"))
        items = ocr_items(eng, np.array(im))
        rows = group_rows(items)
        out[p] = dict(w=im.width, h=im.height,
                      rows=[[dict(d) for d in r] for r in rows])
        cache[key] = out[p]
        print(f"  {vol} {i}/{len(pages)} p{p}: {len(items)} items, {len(rows)} rows", flush=True)
    return out


def cluster_x(all_x, gap=25):
    """按间隙把 x 位置聚成列簇。"""
    xs = sorted(all_x)
    clusters = []
    cur = [xs[0]]
    for v in xs[1:]:
        if v - cur[-1] <= gap:
            cur.append(v)
        else:
            clusters.append(cur); cur = [v]
    clusters.append(cur)
    return [(float(np.median(c)), len(c)) for c in clusters]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vol", default="vol1.epub")
    ap.add_argument("--pages", nargs="+", type=int, required=True)
    ap.add_argument("--gap", type=int, default=25)
    ap.add_argument("--out", default="grid_cache.pkl")
    a = ap.parse_args()

    cache = {}
    if os.path.exists(os.path.join(BASE, a.out)):
        with open(os.path.join(BASE, a.out), "rb") as f:
            cache = pickle.load(f)

    data = collect(a.vol, a.pages, cache)
    with open(os.path.join(BASE, a.out), "wb") as f:
        pickle.dump(cache, f)

    # 统计数据行里的 x 位置
    xs_all = []
    for p, d in data.items():
        for r in d["rows"]:
            if is_data_row(r):
                for it in r:
                    xs_all.append(it["x"])
    print("data-row box count:", len(xs_all))
    cl = cluster_x(xs_all, a.gap)
    cl = [c for c in cl if c[1] >= 5]
    print("column clusters:", len(cl))
    for c, n in cl:
        print(f"   x={c:8.1f}  n={n}")


if __name__ == "__main__":
    main()
