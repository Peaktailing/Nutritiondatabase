# 重新整合流程

从本仓库的原始数据出发，在本地重建出成品库。**不需要 4.4 GB 的完整 SQLite**，整合层直接读原始文件。

## 前置

```bash
git clone git@github.com:peaktailing/Nutritiondatabase.git
cd Nutritiondatabase
pip install openpyxl        # 读 xlsx 需要
```

## 一、还原 USDA 原始数据

```bash
# 方式A：从仓库分片还原
python3 tools/split_usda.py restore data/usda ./usda

# 方式B：直接从 USDA 官网下载（更快，推荐）
mkdir -p usda && cd usda
curl -O https://fdc.nal.usda.gov/download-datasets/FoodData_Central_csv_2026-04-30.zip
unzip FoodData_Central_csv_2026-04-30.zip
cd ..
```

校验完整性：

```bash
cd usda/FoodData_Central_csv_2026-04-30 && md5sum -c ../../data/usda/MD5SUMS.txt
```

## 二、逐来源导入原始层

```bash
python3 scripts/build_db.py         # USDA      -> food / food_nutrient / ... （约 20 分钟，2719万行）
python3 scripts/build_cn.py         # 中国       -> china_food_composition / china_dri_2023 / ...
python3 scripts/build_gi.py         # GI 附录    -> china_food_gi
python3 scripts/build_intl.py       # 法英日西非 -> ciqual_food / uk_cofid_food / jp_mext_food / fao_wafct_food
python3 scripts/build_sea.py        # 印尼东盟   -> id_tkpi_food / asean_fcd_2014
```

> 各脚本默认读 `./usda/`、`./data/international/`、`./data/china/`。若路径不同，用命令行参数指定（见各脚本 `--help`）。

## 三、构建并排归一化层

```bash
python3 scripts/build_norm.py         # 8 来源 -> norm_food（分类 + 状态 + 中文化）
python3 scripts/build_norm_values.py  # 公制化数值 -> norm_value + 浏览视图
```

`build_norm.py` 做的事：

1. **分类归一** —— 各库原始分类映射到 15 个统一分段
2. **状态判定** —— 从名称与含水量推断 `raw/cooked/processed/dried_or_concentrated/unknown`，并记录判定依据到 `state_basis`
3. **公制化** —— 质量类一律 g 存储，非公制单位（IU/ORAC/pH）保留原值不伪换算
4. **名称中文化** —— 见第四步

## 四、名称中文化

```bash
python3 scripts/translate_names.py
```

- 英语词表 `scripts/glossary_en.py`（1,574 主料词条，12 个语义类别）
- 印尼语独立词表 `scripts/glossary_id.py`（结构与英语相反，需单独组装）
- 日语假名→汉字本地化 `JP_KANJI` 表
- 结果写入 `norm_food.name_cn`，未收录词记入 `translate_unknown`

当前覆盖率 **99.1%**。

**补词流程**：查 `translate_unknown` 找高频未收录词 → 加进对应词表 → 重跑本脚本。

```sql
SELECT translate_unknown, count(*) c FROM norm_food
WHERE translate_status='partial' GROUP BY translate_unknown ORDER BY c DESC LIMIT 30;
```

## 五、导出成品

```bash
# 导出整合层（不含 USDA 原始镜像，约 103MB 明文）
python3 tools/export_release.py

# 还原验证
gunzip -c data/nutrition_data.sql.gz | sqlite3 nutrition.db
python3 scripts/query.py tables
```

## 完整复现（从零）

```bash
git clone git@github.com:peaktailing/Nutritiondatabase.git
cd Nutritiondatabase
bash tools/rebuild_all.sh
```

## 各步骤耗时参考

| 步骤 | 耗时 | 产出 |
|------|-----:|------|
| USDA 下载 | ~10 分钟 | 3.1 GB CSV |
| USDA 导入 | ~20 分钟 | 2719 万行 `food_nutrient` |
| 其他 7 来源导入 | ~2 分钟 | 各源库表 |
| 归一化层构建 | ~3 分钟 | `norm_food` 26,958 行 |
| 数值公制化 | ~4 分钟 | `norm_value` 493,941 行 |
| 名称中文化 | ~10 秒 | 99.1% 覆盖 |
| 导出 | ~5 秒 | 7.6 MB |

完整重建约 **40 分钟**。

## 磁盘需求

| 用途 | 空间 |
|------|-----:|
| USDA 原始 CSV | 3.1 GB |
| 中间 SQLite | 4.4 GB |
| 仓库分片 | 460 MB |
| **峰值合计** | **约 9 GB** |

## 常见问题

**Q：状态判定为什么中国库 92.7% 是 `raw`？**
中国食物成分表除明确标注烹饪动作的（如烤鸭）外，绝大多数是新鲜分割或清洗状态。判定链条：名称括号显式状态 > 烹饪动作词 > 加工保藏词 > 含水量兜底。`state_basis` 字段记录每条的判定依据，可审计。

**Q：为什么不合并跨库的相同食物？**
实测各库食物名精确匹配率 0%，模糊匹配召回 35% 但存在系统性误配（黄油→可可脂、奶油→豆奶油、全脂奶粉→奶昔）。不合并就没有误配。

**Q：ASEAN 数据为什么覆盖率只有 76%？**
原始 `food_name` 被泰/越/马来语混排打乱，部分只剩语言码残片（如 `TH) AAC`）。已从 `desc` 列抢救回英文名（`tools/../scripts/fix_asean_names.py`），剩余部分属数据源本身的名称缺失，无法靠词典补全。