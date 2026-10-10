#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把东南亚食物成分数据导入 nutrition.db。

数据源：
  1. 印尼 TKPI 2017        -> 表 id_tkpi_food        （1146 条，HF 镜像 CSV）
  2. ASEAN FCD 2014        -> 表 asean_fcd_2014      （565 条，Mahidol PDF 解析）
     （马来西亚/菲律宾/泰国/越南/印尼/新加坡 六国汇总）
"""
import os
import os as _os
import sys as _sys

# 仓库根目录（本文件位于 <root>/scripts/import/build_sea.py）
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))))
import sqlite3, os, re
import pandas as pd

DB = _os.environ.get("FDC_DB", _os.path.join(ROOT, "nutrition.db"))
SEA = os.path.join(ROOT, "intl_sea")

# ASEAN FCD 的 INFOODS 列 → 规范化名
ASEAN_COLS = ["DEN", "ENERC", "WATER", "PROCNT", "FAT", "CHOAVLDF", "FIBTG", "ASH",
              "CA", "P", "NA", "K", "FE", "CU", "ZN",
              "RETOL", "CARTB", "VITA_RAE", "THIA", "RIBF", "NIA", "VITC"]


def import_tkpi():
    """印尼 TKPI 2017：列名已是英文，直接入库并补统一列。"""
    path = os.path.join(SEA, "id_tkpi_2017.csv")
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    # 统一常见列名，便于跨库查询
    ren = {"KODE": "food_code", "Energy": "energy_kcal", "Protein": "protein_g",
           "Fat": "fat_g", "Carbohydrate": "carbohydrate_g", "Fiber": "fiber_g",
           "Calcium": "calcium_mg", "Phosphorus": "phosphorus_mg", "Iron": "iron_mg",
           "Sodium": "sodium_mg", "Potassium": "potassium_mg", "Copper": "copper_mg",
           "Zinc": "zinc_mg", "Retinol": "retinol_ug", "Beta_Carotene": "beta_carotene_ug",
           "Total_Carotenoids": "total_carotenoids_ug", "Thiamine": "thiamine_mg",
           "Riboflavin": "riboflavin_mg", "Niacin": "niacin_mg", "Vitamin_C": "vitamin_c_mg"}
    df = df.rename(columns=ren)
    with sqlite3.connect(DB) as conn:
        df.to_sql("id_tkpi_food", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tkpi_code ON id_tkpi_food(food_code)")
    return len(df)


def import_asean():
    path = os.path.join(SEA, "asean_fcd_2014_clean.csv")
    df = pd.read_csv(path)
    # 数值列强制转数值
    for c in ASEAN_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    keep = ["asean_id", "food_name_en", "desc", "group"] + \
           [c for c in ASEAN_COLS if c in df.columns]
    df = df[[c for c in keep if c in df.columns]]
    df = df.rename(columns={"asean_id": "food_code",
                            "food_name_en": "food_name",
                            "ENERC": "energy_kcal"})
    with sqlite3.connect(DB) as conn:
        df.to_sql("asean_fcd_2014", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_asean_code ON asean_fcd_2014(food_code)")
    return len(df)


def main():
    n1 = import_tkpi()
    print(f"  id_tkpi_food (印尼 2017): {n1} 条")
    n2 = import_asean()
    print(f"  asean_fcd_2014 (东盟六国): {n2} 条")
    print("DONE ->", DB)


if __name__ == "__main__":
    main()
