#!/bin/bash
# 干净的全量 N 片并行下载器（从零开始，不续传旧文件，避免污染）
# 用法：N=16 bash pdl_full.sh
set -u

URL="https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_csv_2026-04-30.zip"
OUT="/workspace/fdc/FoodData_Central_csv_2026-04-30.zip"
TOTAL=481517495
N="${N:-16}"
PARTDIR="/workspace/fdc/parts_full"
LOG="/workspace/fdc/download_full.log"

log(){ echo "$(date) [pdl_full] $*" | tee -a "$LOG"; }

rm -rf "$PARTDIR" "$OUT" "$OUT.partial"
mkdir -p "$PARTDIR"
CHUNK=$(( (TOTAL + N - 1) / N ))
log "fresh parallel download: TOTAL=$TOTAL N=$N chunk=$CHUNK"

download_part(){
  local i=$1
  local start=$(( i*CHUNK ))
  local end=$(( start + CHUNK - 1 ))
  [ "$end" -ge "$TOTAL" ] && end=$((TOTAL-1))
  local expect=$(( end - start + 1 ))
  local f="$PARTDIR/part_$(printf '%03d' $i).bin"
  local tries=0
  while :; do
    local cur=$(stat -c %s "$f" 2>/dev/null || echo 0)
    [ "$cur" -ge "$expect" ] && { log "part $i OK ($cur bytes)"; return 0; }
    tries=$((tries+1))
    local from=$(( start + cur ))
    curl -sf -r ${from}-${end} -A "Mozilla/5.0" "$URL" -o - \
         --speed-limit 2048 --speed-time 30 --connect-timeout 30 >> "$f" 2>/dev/null
    # 防御：万一超写（不应发生），截断回期望长度
    cur=$(stat -c %s "$f" 2>/dev/null || echo 0)
    if [ "$cur" -gt "$expect" ]; then
      truncate -s "$expect" "$f"
      log "part $i truncated to $expect"
    fi
    [ $((tries % 30)) -eq 0 ] && log "part $i retry #$tries: $cur/$expect"
  done
}

pids=()
for i in $(seq 0 $((N-1))); do
  download_part "$i" &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid"; done

# 校验
tot=0; ok=1
for i in $(seq 0 $((N-1))); do
  start=$(( i*CHUNK )); end=$(( start + CHUNK - 1 )); [ "$end" -ge "$TOTAL" ] && end=$((TOTAL-1))
  expect=$(( end - start + 1 ))
  s=$(stat -c %s "$PARTDIR/part_$(printf '%03d' $i).bin" 2>/dev/null || echo 0)
  tot=$((tot+s))
  [ "$s" -ne "$expect" ] && { log "MISMATCH part $i: $s != $expect"; ok=0; }
done
log "parts total: $tot / $TOTAL"
[ "$tot" -ne "$TOTAL" ] && { echo "DOWNLOAD_INCOMPLETE"; exit 1; }

# 合并
log "concatenating..."
cat "$PARTDIR"/part_*.bin > "$OUT.partial"
fsz=$(stat -c %s "$OUT.partial")
if [ "$fsz" -ne "$TOTAL" ]; then log "final mismatch: $fsz"; echo "DOWNLOAD_INCOMPLETE"; exit 1; fi
mv -f "$OUT.partial" "$OUT"
rm -rf "$PARTDIR"
log "COMPLETE $(stat -c %s "$OUT") bytes"
echo "DOWNLOAD_DONE"
