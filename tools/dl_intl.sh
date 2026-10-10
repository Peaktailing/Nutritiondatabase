#!/bin/bash
# 各国食物成分数据库下载器：断点续传 + 重试
set -u
OUTDIR="/workspace/fdc/intl"
mkdir -p "$OUTDIR"
LOG="/workspace/fdc/intl_download.log"
log(){ echo "$(date) [intl] $*" | tee -a "$LOG"; }

# 名称|URL
ITEMS=(
"uk_cofid_2021|https://assets.publishing.service.gov.uk/media/60538b91e90e07527df82ae4/McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021..xlsx"
"fr_ciqual_2025|https://ciqual.anses.fr/cms/sites/default/files/inline-files/Table%20Ciqual%202025_ENG_2025_11_03.xlsx"
"jp_mext_2020_ch2|https://www.mext.go.jp/content/20201225-mxt_kagsei-mext_01110_012.xlsx"
"jp_mext_2020_amino1|https://www.mext.go.jp/content/20201225-mxt_kagsei-mext_01110_022.xlsx"
"fao_wafct_2019|https://www.fao.org/fileadmin/user_upload/faoweb/2020/WAFCT_2019.xlsx"
"fao_kenya_2018|"
)

dl(){
  local name="$1" url="$2"
  [ -z "$url" ] && { log "skip $name (no url)"; return 0; }
  local f="$OUTDIR/$name.xlsx"
  local tries=0
  while :; do
    tries=$((tries+1))
    curl -sL -C - -A "Mozilla/5.0" "$url" -o "$f" \
         --retry 3 --retry-delay 3 --connect-timeout 20 --max-time 600 \
         --speed-limit 512 --speed-time 60 >/dev/null 2>&1
    local sz=$(stat -c %s "$f" 2>/dev/null || echo 0)
    # xlsx 是 zip：校验魔数 PK\x03\x04，且大小 > 1KB
    if [ "$sz" -gt 1024 ] && head -c 2 "$f" | grep -q "PK"; then
      log "$name OK ($sz bytes)"; return 0
    fi
    [ "$tries" -ge 6 ] && { log "$name FAILED after $tries tries (size=$sz)"; return 1; }
    log "$name retry $tries (size=$sz)"
    sleep 3
  done
}

pids=()
for item in "${ITEMS[@]}"; do
  name="${item%%|*}"; url="${item#*|}"
  dl "$name" "$url" &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done

log "=== results ==="
ls -lh "$OUTDIR"
