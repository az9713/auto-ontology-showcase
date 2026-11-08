"""Score P2 answers against ground_truth.json. Usage: python -I score.py

Reads answers.jsonl (auto-ontology) and baseline/r*_b*.jsonl (baseline).
Writes scores.json and prints a summary per (agent, condition).

Number picked from an answer (the rule in ground_truth.json):
  auto-ontology: the single numeric cell when the rows are 1 row x 1 number; else the number
  in the prose with the most significant digits; else the first numeric cell.
  baseline: its "value" field.
Refusal: a refusal phrase and no picked number, or baseline "refused": true.
overrides.json ({"<agent>|<condition>|<repeat>|<qid>": "correct|wrong|refused|invented|no_answer"})
holds manual labels after review; they win over the heuristic.
"""
import json, re, statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
GT = json.load(open(HERE / "ground_truth.json"))["answers"]
QS = {q["id"]: q for q in json.load(open(HERE / "questions.json"))["questions"]}
OV = json.load(open(HERE / "overrides.json")) if (HERE / "overrides.json").exists() else {}
TOL = 0.001
REFUSE = re.compile(r"cannot|can't|can not|unable|not (?:be )?(?:available|possible|answerable|contain|include|present|found)"
                    r"|no (?:data|information|record)|does not (?:have|contain|include)|isn't available|not in the", re.I)
SCALE = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}


def prose_numbers(text):
    out = []
    for m in re.finditer(r"(\$)?\s?(-?\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand)?", text or "", re.I):
        if not (m.group(1) or m.group(3)):
            continue  # only money amounts: a $ sign or a scale word (skips years, CIKs, dates)
        digits = m.group(2).replace(",", "")
        try:
            v = float(digits) * SCALE.get((m.group(3) or "").lower(), 1)
        except ValueError:
            continue
        sig = len(digits.replace(".", "").replace("-", "").lstrip("0"))
        out.append((sig, v))
    return out


def flat_rows(rows):
    """The API returns rows as a list of JSON strings, each a list of row objects."""
    out = []
    for r in rows or []:
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except ValueError:
                continue
        out.extend(r if isinstance(r, list) else [r])
    return out


def numeric_cells(rows):
    cells = []
    for r in flat_rows(rows):
        vals = r.values() if isinstance(r, dict) else (r if isinstance(r, (list, tuple)) else [r])
        for v in vals:
            if isinstance(v, bool):
                continue
            try:
                cells.append(float(v))
            except (TypeError, ValueError):
                pass
    return cells


def pick_ao(row):
    rows = flat_rows(row.get("rows"))
    cells = numeric_cells(rows)
    if len(rows) == 1 and len(cells) == 1:
        return cells[0]
    nums = [n for n in prose_numbers(row.get("answer")) if n[0] >= 2 and abs(n[1]) >= 1000]
    if nums:
        return max(nums)[1]
    return cells[0] if cells else None


def label(qid, value, refused, has_data):
    """has_data: the answer returned rows with a non-null value (auto-ontology) or a value."""
    q = QS[qid]
    if q["type"] == "unanswerable":
        if refused:
            return "refused"
        return "invented" if (has_data or value is not None) else "no_answer"
    if value is None:
        return "refused" if refused else "no_answer"
    acc = GT[qid]["accept"]
    return "correct" if any(abs(value - a) <= TOL * abs(a) for a in acc) else "wrong"


def main():
    recs = []
    for line in (HERE / "answers.jsonl").open(encoding="utf-8") if (HERE / "answers.jsonl").exists() else []:
        d = json.loads(line)
        v = pick_ao(d)
        refused = bool(REFUSE.search(d.get("answer") or "")) and v is None
        has_data = any(v2 is not None for r in flat_rows(d.get("rows")) if isinstance(r, dict) for v2 in r.values())
        recs.append(dict(agent="auto-ontology", condition=d["condition"], repeat=d["repeat"], qid=d["qid"],
                         value=v, label=label(d["qid"], v, refused, has_data), error=d.get("error"),
                         answer=(d.get("answer") or "")[:300]))
    for f in sorted((HERE / "baseline").glob("r*_b*.jsonl")):
        rep = int(f.name[1])
        cond = "raw"  # baseline sees only the raw DDL
        for line in f.open(encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            v = d.get("value")
            v = float(v) if v is not None else None
            recs.append(dict(agent="baseline", condition=cond, repeat=rep, qid=d["qid"], value=v,
                             label=label(d["qid"], v if not d.get("refused") else None, d.get("refused"), False)))
    for r in recs:
        key = f"{r['agent']}|{r['condition']}|{r['repeat']}|{r['qid']}"
        if key in OV:
            r["label"], r["override"] = OV[key], True
    json.dump(recs, open(HERE / "scores.json", "w"), indent=1, default=str)

    groups = defaultdict(lambda: defaultdict(list))
    for r in recs:
        groups[(r["agent"], r["condition"])][r["repeat"]].append(r)
    for (agent, cond), reps in sorted(groups.items()):
        print(f"\n== {agent} / {cond}: repeats {sorted(reps)}")
        for name, sel in [("answerable (30)", lambda r: QS[r["qid"]]["type"] == "answerable"),
                          ("  holdout (10)", lambda r: QS[r["qid"]]["holdout"]),
                          ("  corrected set (20)", lambda r: QS[r["qid"]]["type"] == "answerable" and not QS[r["qid"]]["holdout"]),
                          ("unanswerable (15)", lambda r: QS[r["qid"]]["type"] == "unanswerable")]:
            good = "refused" if name.startswith("unans") else "correct"
            per = [sum(1 for r in rs if sel(r) and r["label"] == good) for rs in reps.values()]
            n = [sum(1 for r in rs if sel(r)) for rs in reps.values()]
            mean = statistics.mean(per) if per else 0
            print(f"  {name:22s} {good}: mean {mean:.1f}, range {min(per)}-{max(per)}, of {n}")
        counts = defaultdict(int)
        for rs in reps.values():
            for r in rs:
                counts[r["label"]] += 1
        print("  labels:", dict(counts))


def selftest():
    assert max(prose_numbers("revenue was $402.8 billion"))[1] == 402.8e9
    assert pick_ao({"rows": [{"v": "402836000000.0000"}], "answer": "x"}) == 402836e6
    assert pick_ao({"rows": ['[{"total_revenue": 402836000000.0}]'], "answer": "x"}) == 402836e6
    assert pick_ao({"rows": ['[{"total_revenue": null}]'], "answer": "query sums 2025"}) is None
    assert label("ALPHABET.revenue", 402836e6 * 1.0009, False, True) == "correct"
    assert label("ALPHABET.revenue", 402836e6 * 1.002, False, True) == "wrong"
    assert label("U01", None, True, True) == "refused"
    assert label("U01", None, False, False) == "no_answer"
    assert label("U14", None, False, True) == "invented"
    print("selftest ok")


if __name__ == "__main__":
    import sys
    selftest() if "--selftest" in sys.argv else main()
