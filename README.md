# Nutrition Database · 食品营养数据整合库

整合 **9 个来源**的食品营养数据，覆盖 10 个国家/地区：

| 来源 | 数据量 | 说明 |
|------|-------:|------|
| **USDA FoodData Central**（美） | 2,101,279 食品 / 2,719 万条营养素 | 2026-04-30 完整包，全球最全 |
| **中国食物成分表 标准版 第6版** | 1,810 食物 | OCR 抽取 + USDA 兼容版 + 质量分级 |
| **英国 CoFID 2021** | 2,886 食物 | McCance & Widdowson's 第7版 |
| **法国 CIQUAL 2025** | 3,484 食物 | ANSES 官方 |
| **日本 MEXT 八订** | 2,478 食物 + 1,954 氨基酸 | 食品標準成分表 2020 |
| **印尼 TKPI 2017** | 1,146 食物 | Kemenkes 官方 |
| **FAO/INFOODS 西非** | 1,055 食物 | WAFCT 2019 |
| **东盟 FCD 2014** | 565 食物 | 印尼/马来/菲/泰/越/文莱 |
| **中国居民膳食营养素参考摄入量 2023版** | 277 行 | EAR/RNI/AI/UL/AMDR |

---

## 快速开始

```bash
# 1. 还原整合成品库（58 MB）
gunzip -c data/nutrition_data.sql.gz | sqlite3 nutrition.db

# 2. 查询（支持中文）
python3 scripts/query/query.py browse --name 三文鱼      # 中文检索
python3 scripts/query/query.py side 牛肉# 跨来源并排对照
python3 scripts/query/query.py bycat                     # 分类 × 来源矩阵
python3 scripts/query/query.py tables                    # 列出所有表
```

> `query.py` 默认读 `./nutrition.db`，可用 `--db` 指定路径。
>
> 想直接用 OCR 成果库（无需还原）：
> ```bash
> python3 scripts/query/query.py --db data/china-ocr/中国食物成分表.db tables
> ```

---

## 仓库结构

```
├── data/                ★ 全部原始数据（可追溯、可重算）
│   ├── usda/                          USDA 2026-04-30，34 个 CSV（37 个 gzip 分片）
│   │   ├── <表名>/<表名>.csv.gz.partNNN
│   │   └── MD5SUMS.txt34 条 MD5 校验
│   ├── international/                 法/英/日/西非/印尼/东盟 原始文件
│   ├── china/                         中国食物成分表 + DRIs 2023 + GI 附录
│   ├── china-ocr/                  ★ 中国第6版 OCR 抽取成果
│   │   ├── 中国食物成分表.db
│   │   ├── 中国食物成分表_USDA兼容版.db
│   │   ├── csv_tables/                5 张可直接导入的 CSV
│   │   ├── validation_report/         校验报告 + 抽取中间数据
│   │   ├── OCR_README.md              OCR 抽取管线详细文档
│   │   └── ocr_pipeline.zipOCR 处理管线归档
│   ├── nutrition_data.sql.gz        ★ 整合成品库（8 来源并排层）
│   └── RAW_DATA.md                   原始数据说明与还原方式
│
├── scripts/
│   ├── import/                        各来源原始层导入（7 个）
│   ├── normalize/                     并排归一化层构建（2 个）
│   ├── translate/                     名称中文化（词典 + 引擎，4 个）
│   ├── ocr-china/                  中国第6版 OCR 处理管线（26 个）
│   └── query/                         命令行查询
│
├── tools/
│   ├── split_usda.py                  USDA 分片打包 / 还原
│   ├── export_release.py              整合层导出
│   ├── rebuild_all.sh                 一键重建
│   ├── pdl_full.sh                    USDA 16 路并发下载器
│   └── dl_intl.sh                     国际库下载器
│
└── docs/
    ├── TECHNICAL.md完整技术文档
    ├── REBUILD.md                     重新整合流程
    └── CROSS_DB_PLAN.md               跨库比对实测与决策记录
```

---

## 整合成品库

| 表 | 行数 | 说明 |
|----|-----:|------|
| `norm_food` | 26,958 | **并排食物索引**，8 来源各一条独立记录，含中文名 |
| `norm_value` | 493,941 | 公制化数值（质量类一律 g，显示层转 mg/μg） |
| `norm_nutrient` | 29 | 统一营养素字典 |
| `norm_canon_cat` | 15 | 统一分类分段 |
| `china_food_composition` | 1,677 | 中国食物成分表第6版 |
| `china_dri_2023` | 277 | 中国 DRIs 2023版 |
| `china_food_gi` | 259 | 中国食物 GI |
| `uk_cofid_food` | 34,644 | 英国 CoFID |
| `ciqual_food` | 3,484 | 法国 CIQUAL |
| `jp_mext_food` | 2,478 | 日本 MEXT |
| `id_tkpi_food` | 1,146 | 印尼 TKPI |
| `asean_fcd_2014` | 565 | 东盟 FCD |
| `fao_wafct_food` | 1,055 | FAO 西非 |

还原后约 58 MB，含 28 张表。

---

## 三个核心设计

### 1. 不做跨库合并（并排而非混合）

各库食物名**精确匹配率实测 0%**，模糊匹配召回 35% 但存在系统性误配：

| 查询 | USDA | 实际匹配到 | 错误类型 |
|------|------|-----------|---------|
| 黄油 | butter | 可可脂 | 相似词 |
| 奶油 | cream | 豆奶油 | 相似词 |
| 全脂奶粉 | whole milk powder | 奶昔 | 相似词 |

因此**不合并**：每条记录的来源、原始名称、原始分类全部保留，判断权交给使用者。

### 2. 数值统一公制

质量类一律以 g 存储，显示层按营养素习惯转 mg/μg。

**不做伪换算**：IU（维生素 A/D/E）、`UMOL_TE`(ORAC)、`MG_GAE`(总酚)、`SP_GR`(比重)、pH —— 换算系数依赖食物类别，强行换算会引入错误，故保留原值并标注。

### 3. 食物名称中文化（覆盖率 99.1%）

自建受控词典替代机器翻译。实测外部 MT 接口会把 `cheddar cheese` 译成粤语「車打芝士」、把 `whole-wheat` 切成「整个小麦」、把 `fat-free` 切成「脂肪+免费」。

- **词典**：`scripts/translate/glossary_en.py`，1,574 主料词条 / 12 个语义类别
- **机制**：全部词条拼成单个正则 alternation，对整条名称一次 `finditer` —— Python `re` 取最左成功分支，天然「最长短语优先」
- **语序**：`{状态:1, 烹饪:2, 加工:3, 宣称:4, 颜色:5, 国别:6, 形态:7, 取料:8}`
- **印尼语独立通路**：语序与英语相反（主料在前、修饰在后），需单独组装
- **日语本地化**：约 500 条假名→汉字表

| 来源 | 覆盖率 |
|------|-------:|
| 中国 / 法国 / 英国 | 100% |
| USDA / 日本 / 西非 | 99.8% |
| 印尼 | 92.9% |
| 东盟 | 76.1% |
| **合计** | **99.1%**（26,711 / 26,958） |

---

## 中国数据：两个来源互补

仓库里有两份中国成分表，**互补而非重复**：

| 来源 | 条数 | 位置 | 说明 |
|------|-----:|------|------|
| 早期整理版 | 1,677 | `data/china/` | 含部分 `x` 后缀变体 |
| **OCR 抽取版** | **1,810** | `data/china-ocr/` | 质量分级 A/B/C + USDA 兼容版 |

**编码重合度 89.2%**（交集 1,615 条）：

- OCR 版独有 **195 条** —— OCR 补全的条目
- 早期版独有 **62 条** —— 含 `x` 后缀的变体（如 `011201x`）

> **合并后可得不重复 1,872 条中国食物**，比任一来源都全。

### OCR 抽取版质量

来源：《中国食物成分表 标准版 第6版》两册扫描版（387 + 454 = 841 页）

| 等级 | 条数 | 占比 | 说明 |
|------|-----:|-----:|------|
| A 可信 | 1,534 | 85% | 无越界、守恒关系成立 |
| B 基本可信 | 222 | 12% | 轻微问题（如个别字段缺失） |
| C 需核对 | 54 | 3% | 存在越界或守恒失守 |
| D 可疑 | 0 | 0% | — |

零重复编码。主表带 `macro_sum`（六大宏量合计）与 `check_grade` 字段 —— `macro_sum` 在 94~106 → 数据可信。

处理管线：RapidOCR 逐页识别 → 表类型判定 → 表头模板对齐 → 列映射 → 物理约束校验与修正 → 跨页合并。源码 `scripts/ocr-china/`，详细文档 `data/china-ocr/OCR_README.md`。

### ⚠️ 合并中国数据时必读

USDA 的 `Carbohydrate, by difference` 是**减差法**计算值，与中国食物成分表的碳水化合物定义不同，两者不可直接比较。此外原始数值带符号标记需注意：`Tr`(未检出)、`*`(参考值)、`—`(未检测)、`un`(不能计算)。

---

## 重新整合

```bash
bash tools/rebuild_all.sh    # 约 40 分钟，峰值磁盘 9 GB
```

详见 [`docs/REBUILD.md`](docs/REBUILD.md)。

**还原 USDA 分片**：

```bash
python3 tools/split_usda.py restore data/usda ./usda
cd usda/FoodData_Central_csv_2026-04-30 && md5sum -c ../../data/usda/MD5SUMS.txt
```

> USDA 原始 CSV 3.1 GB，最大单文件 `food_nutrient.csv` 有 1709 MB，超过 GitHub 100 MB 限制，故 gzip 后按 90 MB 分片（压缩率 85.2%）。**还原后 MD5 与官方文件 34/34 完全一致。**

---

## 数据来源

| 数据集 | 发布方 | 授权 |
|--------|--------|------|
| USDA FoodData Central | 美国农业部 | 公共领域 |
| 中国食物成分表 第6版 | 中国疾控中心 | 公开出版物 |
| 中国 DRIs 2023版 | 中国营养学会 | 公开出版物 |
| CIQUAL 2025 | 法国 ANSES | 公开 |
| CoFID 2021 | 英国 SACN / McCance & Widdowson's | 公开 |
| 食品標準成分表八訂 | 日本文部科学省 | 公开 |
| TKPI 2017 | 印尼卫生部 Kemenkes | 公开 |
| WAFCT 2019 | FAO / WHO | 公开 |
| ASEAN FCD 2014 | 东盟 | 公开 |

各数据集版权归原发布机构所有。本仓库仅做结构化整理，**数值未作修改**。

---

## 免责声明

本项目为个人性质的数据整理成果。原始数据的准确性、完整性以各发布机构为准。中国 DRIs 部分数值受获取渠道限制未经原书逐项核验（`verified` 字段已标明）。OCR 抽取数据可能残留个别识别误差，已用质量守恒、能量守恒、kJ/kcal 一致性三重约束修正，但仍建议关键数据交叉核对原书。

**请勿将本数据用于临床或医疗决策。**

---

## LICENSE

MIT License，版权归 Peaktailing 所有。见 [`LICENSE`](LICENSE)。数据本身遵循各自来源机构的授权条款。