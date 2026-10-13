#!/usr/bin/env bash
# 从仓库原始数据完整重建整合库
#
# 用法：
#   bash tools/rebuild_all.sh
#
# 峰值磁盘需求约 9 GB（3.1 GB 原始 CSV + 4.4 GB 中间库 + 460 MB 分片）
# 完整耗时约 40 分钟，其中 USDA 导入占约 20 分钟

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# DB 路径解析顺序：DB 环境变量 > FDC_DB 环境变量 > <repo>/nutrition.db
# 三个变量必须一致，否则 Python 脚本（认 FDC_DB）和导出步骤（用 $DB）
# 会写/读不同的库。
DB="${DB:-${FDC_DB:-nutrition.db}}"
# 所有 Python 脚本都从 FDC_DB 解析库路径，这里显式导出，
# 保证导入/合并/修复/归一化/导出写的是同一个库。
export FDC_DB="$DB"
USDA_DIR="${USDA_DIR:-usda/FoodData_Central_csv_2026-04-30}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- 0. 依赖
say "检查依赖"
python3 -c "import openpyxl" 2>/dev/null || {
  echo "安装 openpyxl ..."
  pip3 install --quiet openpyxl
}

# ---------------------------------------------------------------- 1. USDA
if [ ! -d "$USDA_DIR" ]; then
  say "还原 USDA 原始数据（从仓库分片）"
  mkdir -p usda
  python3 tools/split_usda.py restore data/usda usda
else
  say "USDA 原始数据已存在：$USDA_DIR"
fi

say "校验 USDA 原始数据完整性"
( cd "$USDA_DIR" && md5sum -c ../../data/usda/MD5SUMS.txt 2>&1 | tail -3 ) || {
  echo "⚠️  校验失败，但继续（可能是官方更新了数据版本）"
}

# ---------------------------------------------------------------- 2. 导入
say "导入 USDA（2719 万行，约 20 分钟）"
python3 scripts/import/build_db.py

say "导入中国食物成分表 + DRIs 2023"
python3 scripts/import/build_cn.py

say "导入中国食物 GI 附录"
python3 scripts/import/build_gi.py

say "导入国际库（法 / 英 / 日 / 西非）"
python3 scripts/import/build_intl.py

say "导入东南亚（印尼 / 东盟）"
python3 scripts/import/build_sea.py

# ---------------------------------------------------------------- 3. 中国两版合并
# 两版同属第6版标准版、互补而非迭代。合并后才能进并排层：
#   china_food_merged     1,831 条（OCR 1,810 + 早期补缺 21）
#   china_food_synthetic    39 条（x 后缀代表值估算，隔离，不进并排层）
#   china_merge_map       1,872 条决策日志
say "合并中国两版成分表（OCR + 早期整理版）"
python3 scripts/import/merge_china_ocr.py

# ---------------------------------------------------------------- 3.5 OCR 修复
# 用守恒约束修 china_food_merged 里的 OCR 读数错误。必须在归一化之前跑，
# 否则修复不会进入 norm_food / norm_value。117 条自动修复 / 61 条假警报澄清 /
# 4 条转人工（needs_manual_review，保持原值）。
say "OCR 读数错误自动修复（守恒约束）"
python3 scripts/normalize/fix_ocr_shifts.py

# ---------------------------------------------------------------- 4. 归一化
say "构建并排归一化层"
python3 scripts/normalize/build_norm.py

say "公制化数值 + 浏览视图"
python3 scripts/normalize/build_norm_values.py

# ---------------------------------------------------------------- 5. 中文化
say "食物名称中文化"
python3 scripts/translate/translate_names.py
python3 scripts/translate/fix_asean_names.py

# ---------------------------------------------------------------- 6. 导出
say "导出成品"
python3 tools/export_release.py --db "$DB" --out data/nutrition_data.sql.gz

# ---------------------------------------------------------------- 7. 验证
say "验证还原"
TMPDB=$(mktemp -u /tmp/verify_XXXX.db)
gunzip -c data/nutrition_data.sql.gz | sqlite3 "$TMPDB"
python3 - "$TMPDB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
tot = con.execute("select count(*) from norm_food").fetchone()[0]
cn = con.execute("select count(*) from norm_food where name_cn is not null").fetchone()[0]
val = con.execute("select count(*) from norm_value").fetchone()[0]
print(f"  norm_food    {tot:,}")
print(f"  norm_value   {val:,}")
print(f"  中文名覆盖率 {100.0*cn/tot:.1f}%")
print(f"  quick_check  {con.execute('PRAGMA quick_check').fetchone()[0]}")
PY
rm -f "$TMPDB"

say "完成 ✅"
echo "  成品库:  $DB"
echo "  可分发:  data/nutrition_data.sql.gz"