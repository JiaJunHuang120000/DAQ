#!/usr/bin/env bash

# ------------------ CONFIG ------------------

INTERVAL=60           # seconds between samples
ROTATE_COUNT=60      # samples per file (360 = 1 hour @10s)
BASE="data/sensor_log"

# Arduino nodes (IP PORT ID)
NODES=(
  "192.168.50.50 5001 A"
  "192.168.50.51 5001 B"
  "192.168.50.52 5001 C"
)

# --------------------------------------------

FILE_INDEX=1
SAMPLE_COUNT=0

make_files() {
  for node in "${NODES[@]}"; do
    set -- $node
    echo "Logging start $(date -u)" > "${BASE}_${3}_${FILE_INDEX}.txt"
  done
}

mkdir data/
make_files

echo "Logging started — interval=${INTERVAL}s, rotate=${ROTATE_COUNT}"

# ------------------ MAIN LOOP ------------------

while true; do
  for node in "${NODES[@]}"; do
    set -- $node
    IP=$1
    PORT=$2
    ID=$3

    printf "\n" | nc -w 3 "$IP" "$PORT" >> "${BASE}_${ID}_${FILE_INDEX}.txt"
  done

  ((SAMPLE_COUNT++))

  if (( SAMPLE_COUNT >= ROTATE_COUNT )); then
    ((FILE_INDEX++))
    SAMPLE_COUNT=0
    make_files
  fi

  sleep "$INTERVAL"
done
