"""全量 OCR 任务(后台):两册逐页识别,结果缓存到 grid_cache.pkl。

用法:
  python ocr_all.py vol1.epub
  python ocr_all.py vol2.epub
断点续跑:已识别的页会跳过。
"""
import os, pickle, sys, zipfile, time
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from pipeline import prep, ocr_items, group_rows   # noqa: E402

CACHE_PATH = os.path.join(BASE, "grid_cache.pkl")


def load():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}


def save(c):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(c, f, protocol=4)
    os.replace(tmp, CACHE_PATH)


def main():
    vol = sys.argv[1] if len(sys.argv) > 1 else "vol1.epub"
    z = zipfile.ZipFile(os.path.join(BASE, vol))
    pages = sorted(int(n.split("-")[1].split("_")[0]) for n in z.namelist()
                   if n.endswith(".jpg") and n.startswith("index-"))
    cache = load()
    todo = [p for p in pages if f"{vol}:{p}" not in cache]
    print(f"[{vol}] total={len(pages)} cached={len(pages)-len(todo)} todo={len(todo)}",
          flush=True)
    if not todo:
        print("nothing to do")
        return

    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()

    t0 = time.time()
    ok = fail = 0
    for i, p in enumerate(todo, 1):
        key = f"{vol}:{p}"
        try:
            im = prep(z.read(f"index-{p}_1.jpg"))
            items = ocr_items(eng, np.array(im))
            if items is None:
                items = []
            rows = group_rows(items)
            cache[key] = dict(w=im.width, h=im.height,
                              rows=[[dict(d) for d in r] for r in rows])
            ok += 1
        except Exception as e:
            print(f"  !! p{p}: {type(e).__name__}: {e}", flush=True)
            fail += 1
            continue
        if i % 10 == 0:
            save(cache)
            el = time.time() - t0
            eta = el / i * (len(todo) - i)
            print(f"  {i}/{len(todo)} ok={ok} fail={fail} "
                  f"{el/i:.1f}s/pg eta={eta/60:.0f}min", flush=True)
    save(cache)
    print(f"[done] {vol} ok={ok} fail={fail} "
          f"elapsed={(time.time()-t0)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
