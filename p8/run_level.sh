#!/bin/sh
# P8: run arms P, R, O at one level, 3 repeats. Per repeat the 3 arms run in parallel; repeats run one after another.
# Usage: sh run_level.sh L1 [arms]   (the store must already hold the level: python -I load_store.py L1)
cd "$(dirname "$0")"
LEVEL=$1
ARMS=${2:-"P R O"}
for rep in 1 2 3; do
  for arm in $ARMS; do
    python -I run_p8.py "$arm" "$LEVEL" "$rep" &
  done
  wait
done
python -I score.py
echo "LEVEL_DONE $LEVEL"
