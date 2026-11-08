#!/bin/sh
# P7 runs in priority order (one local model slot, so sequential). Restartable: each runner skips done rows.
cd "$(dirname "$0")"
python -I run_ddl.py 3
python -I run_ao.py b_ao_uncertified 1
[ -f certify_log.jsonl ] || python -I certify.py
python -I run_ao.py c_ao_certified 1
python -I run_ao.py b_ao_uncertified 3
python -I run_ao.py c_ao_certified 3
echo ALL_DONE
