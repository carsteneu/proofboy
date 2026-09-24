#!/usr/bin/env bash
# run_jobs.sh — run independent jobs in parallel (thin bash wrapper, no build).
#
# Usage:  ./run_jobs.sh JOBSFILE [-j N] [--logdir DIR]
# JOBSFILE: one job per line, format   <name>|<command>
#           (blank lines and lines starting with # are skipped)
# Each job writes LOGDIR/<name>.log; a summary of exit codes is printed at the end.
#
# Memory note: heavy Antihydra deep runs need ~2x memory of the previous level
# (depth 34 ~ 25-40 GB). Keep -j small for those, or use the cache ladder
# (--cache-out/--cache-in, 2x faster per level) so single runs stay short.
set -u
JOBSFILE=${1:?usage: run_jobs.sh JOBSFILE [-j N] [--logdir DIR]}
shift
PAR=4
LOGDIR=logs
while [ $# -gt 0 ]; do
  case "$1" in
    -j) PAR=$2; shift 2 ;;
    --logdir) LOGDIR=$2; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$LOGDIR"
STATUS="$LOGDIR/.status.$$"
: > "$STATUS"

start=$(date +%s)
while IFS='|' read -r name cmd; do
  name=${name// /}
  [ -z "$name" ] && continue
  case "$name" in \#*) continue ;; esac
  ( bash -c "$cmd" > "$LOGDIR/$name.log" 2>&1; echo "$name $?" >> "$STATUS" ) &
  while [ "$(jobs -rp | wc -l)" -ge "$PAR" ]; do
    wait -n 2>/dev/null || sleep 0.2
  done
done < "$JOBSFILE"
wait
end=$(date +%s)

echo "=== summary (wall $((end - start))s, -j $PAR) ==="
sort "$STATUS"
rm -f "$STATUS"
