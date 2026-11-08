"""P8 scoring. Reads runs/<arm>_<level>_r<rep>_b<k>.jsonl + .run.json, writes scores.json, prints the table.

  python -I score.py

Answerable (40): correct if |value - truth| <= tolerance (m02 also accepts its alt truth). Unanswerable (5): correct if
refused; "invented" if not refused and a value was given. Near-variant: "trap" if the value equals the trap's truth.
A missing answer (no line, batch failed or timed out) counts as wrong and is listed.
"""
import json, re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
qs = {q["id"]: q for q in json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]}
CLASSES = ["copy", "compose", "near-variant", "unanswerable"]


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "")) if v is not None else None
    except ValueError:
        return None


runs = defaultdict(dict)
for f in sorted((HERE / "runs").glob("*_r[0-9]_b[0-9].run.json")):
    arm, level, rep, b = re.match(r"(\w)_(L\d)_r(\d)_b(\d)\.run\.json", f.name).groups()
    key = (arm, level, int(rep))
    r = runs[key].setdefault("meta", {"cost": 0.0, "secs": 0.0, "in_tokens": 0, "batches": 0, "errors": []})
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        u = d.get("usage", {})
        r["cost"] += d.get("total_cost_usd") or 0
        r["secs"] += (d.get("duration_ms") or 0) / 1000
        r["in_tokens"] += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        if d.get("is_error"):
            r["errors"].append(f"b{b}: {d.get('terminal_reason')} {str(d.get('result'))[:120]}")
    except (json.JSONDecodeError, OSError):
        r["errors"].append(f"b{b}: no run json")
    r["batches"] += 1
    ans = Path(str(f).replace(".run.json", ".jsonl"))
    if ans.exists():
        for line in ans.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    a = json.loads(line)
                    runs[key][a["qid"]] = a
                except (json.JSONDecodeError, KeyError):
                    pass

out = []
for (arm, level, rep), r in sorted(runs.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
    row = {"arm": arm, "level": level, "rep": rep, **{c: 0 for c in CLASSES}, "answerable_correct": 0, "invented": 0,
           "trap": 0, "missing": [], **{k: r["meta"][k] for k in ("cost", "secs", "in_tokens", "batches", "errors")}}
    for qid, q in qs.items():
        a = r.get(qid)
        if a is None:
            row["missing"].append(qid)
            continue
        v = num(a.get("value"))
        if q["class"] == "unanswerable":
            if a.get("refused"):
                row["unanswerable"] += 1
            elif v is not None:
                row["invented"] += 1
            continue
        truths = [q["truth"]] + ([q["alt_truth"]] if "alt_truth" in q else [])
        if not a.get("refused") and v is not None and any(abs(v - t) <= q["tolerance"] + 1e-9 for t in truths):
            row[q["class"]] += 1
            row["answerable_correct"] += 1
        elif "trap_truth" in q and v is not None and abs(v - q["trap_truth"]) <= q["tolerance"] + 1e-9:
            row["trap"] += 1
    row["cost"] = round(row["cost"], 2)
    row["secs"] = round(row["secs"])
    out.append(row)

(HERE / "scores.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("level arm rep | answerable/40 copy/15 compose/10 near/15 trap | refused/5 invented | USD  min  Mtok | missing errors")
for r in out:
    print(f"{r['level']} {r['arm']} r{r['rep']} | {r['answerable_correct']:2d} {r['copy']:2d} {r['compose']:2d} {r['near-variant']:2d} "
          f"{r['trap']:2d} | {r['unanswerable']} {r['invented']} | {r['cost']:5.2f} {r['secs'] / 60:4.0f} {r['in_tokens'] / 1e6:5.2f} | "
          f"{len(r['missing'])} {r['errors'] if r['errors'] else ''}")
