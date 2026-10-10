#!/usr/bin/env python3
"""
USDA 原始 CSV 分片压缩打包。

为什么分片：GitHub 单文件硬限制 100 MB，而 food_nutrient.csv 有 1709 MB。
做法：gzip 压缩后按 90 MB 切片，切片序号编码在文件名里，还原时按序拼接。

用法：
    python3 split_usda.py <源目录> <输出目录> [--level 6]
"""
import gzip
import os
import shutil
import sys

TARGET = 90 * 1024 * 1024   # 每片90 MB，留足余量
LEVEL = 6


def split_one(src, out_dir, level=LEVEL):
    """单文件 gzip -> 分片。返回 (原大小, 压缩后总大小, 片数)"""
    base = os.path.splitext(os.path.basename(src))[0]
    out_dir = os.path.join(out_dir, base)
    os.makedirs(out_dir, exist_ok=True)

    raw = os.path.getsize(src)
    # 先整体 gzip 到临时文件
    gz_tmp = os.path.join(out_dir, base + ".csv.gz")
    t0 = __import__("time").time()
    with open(src, "rb") as fi, gzip.open(gz_tmp, "wb", compresslevel=level) as fo:
        shutil.copyfileobj(fi, fo, length=8 * 1024 * 1024)
    gz_size = os.path.getsize(gz_tmp)

    # 切片
    parts = []
    with open(gz_tmp, "rb") as f:
        idx = 0
        while True:
            chunk = f.read(TARGET)
            if not chunk:
                break
            p = os.path.join(out_dir, f"{base}.gz.part{idx:03d}")
            with open(p, "wb") as fo:
                fo.write(chunk)
            parts.append(os.path.basename(p))
            idx += 1

    os.remove(gz_tmp)
    dt = __import__("time").time() - t0
    print(f"  {base:<36} {raw/1048576:>8.1f}MB -> {gz_size/1048576:>7.1f}MB "
          f"({len(parts)} 片, {dt:.0f}s)")
    return raw, gz_size, len(parts)


def restore(out_dir, target_dir):
    """还原：把所有*.gz.part* 按序拼接后 gunzip"""
    os.makedirs(target_dir, exist_ok=True)
    for base in sorted(os.listdir(out_dir)):
        d = os.path.join(out_dir, base)
        if not os.path.isdir(d):
            continue
        parts = sorted(f for f in os.listdir(d) if ".gz.part" in f)
        if not parts:
            continue
        raw_name = base.replace("_gz", "") + ".csv"
        out = os.path.join(target_dir, raw_name)
        print(f"  还原 {raw_name} ({len(parts)} 片)...", flush=True)
        with open(out, "wb") as fo:
            tmp = out + ".tmp.gz"
            with open(tmp, "wb") as ft:
                for p in parts:
                    with open(os.path.join(d, p), "rb") as fi:
                        shutil.copyfileobj(fi, ft, length=8 * 1024 * 1024)
            with gzip.open(tmp, "rb") as fi, open(out, "wb") as fo2:
                shutil.copyfileobj(fi, fo2, length=8 * 1024 * 1024)
            os.remove(tmp)
        print(f"    -> {os.path.getsize(out)/1048576:.1f}MB")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "restore":
        restore(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "./usda")
        sys.exit(0)

    src_dir, out_dir = sys.argv[1], sys.argv[2]
    level = LEVEL
    if "--level" in sys.argv:
        level = int(sys.argv[sys.argv.index("--level") + 1])

    os.makedirs(out_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".csv"))
    print(f"待处理 {len(files)} 个 CSV -> {out_dir} (压缩级别 {level})\n")

    tot_raw = tot_gz = tot_part = 0
    for f in files:
        r, g, p = split_one(os.path.join(src_dir, f), out_dir, level)
        tot_raw += r; tot_gz += g; tot_part += p

    print(f"\n合计: 原始 {tot_raw/1073741824:.2f} GB -> 分片 {tot_gz/1048576:.1f} MB "
          f"({tot_part} 片, 压缩率 {100-tot_gz/tot_raw*100:.1f}%)")