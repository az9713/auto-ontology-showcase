"""Score P7 answers against questions.json (truth from truth.sql). Usage: python -I score.py [--selftest]

Reads answers.jsonl (arms a_local_ddl, b_ao_uncertified, c_ao_certified) and baseline/r*.jsonl (arm d).
Writes scores.json and prints a summary per arm.

Number picked from an answer:
  arm a (rows = psql CSV text) and arms b/c (rows = API JSON): the cell when the result is 1 row x 1 number;
  else the first number in the prose that is also a cell; else the first numeric cell; else the first prose number.
  arm d: its "value" field.
Correct: |value - truth| <= tolerance. For a percentage question, value*100 is also accepted (a fraction).
Refusal: arms a/d "refused": true; arms b/c a refusal phrase and no picked number.
overrides.json ({"<arm>|<repeat>|<qid>": "<label>"}) holds manual labels after review; they win.
"""
import csv, io, json, re, statistics, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
QS = {q["id"]: q for q in json.load(open(HERE / "questions.json", encoding="utf-8"))["questions"]}
# ponytail: b and c send the same request; only the store differs. run_all.sh ran b r2-r3 after certify.py,
# so those rows are scored apart. Local time (UTC-8) of the first certify.py call (certify_log.jsonl).
CERT_AT = "2026-11-07T10:36:59"
OV = json.load(open(HERE / "overrides.json")) if (HERE / "overrides.json").exists() else {}
REFUSE = re.compile(r"cannot|can't|can not|unable|not (?:be )?(?:available|possible|answerable|contain|include|present|found)"
                    r"|no (?:data|information|record)|does not (?:have|contain|include|track|store)|isn't available"
                    r"|not in the|not tracked|not stored", re.I)


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(str(v).replace(",", "").rstrip("%"))
    except ValueError:
        return None


def table(rows):
    """-> list of rows, each a list of cell values. psql CSV text (arm a) or API JSON strings (arms b/c)."""
    if isinstance(rows, str):
        return list(csv.reader(io.StringIO(rows)))[1:]
    out = []
    for r in rows or []:
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except ValueError:
                continue
        for x in (r if isinstance(r, list) else [r]):
            out.append(list(x.values()) if isinstance(x, dict) else x if isinstance(x, list) else [x])
    return out


def pick(rows, prose):
    t = table(rows)
    cells = [n for row in t for n in map(num, row) if n is not None]
    if len(t) == 1 and len(t[0]) == 1 and cells:
        return cells[0]
    pn = [num(m) for m in re.findall(r"-?\d[\d,]*(?:\.\d+)?", prose or "")]
    pn = [n for n in pn if n is not None]
    for n in pn:
        if any(abs(n - c) < 1e-9 for c in cells):
            return n
    return cells[0] if cells else (pn[0] if pn else None)


def label(qid, value, refused):
    q = QS[qid]
    if q["type"] == "unanswerable":
        return "refused" if refused else "invented" if value is not None else "no_answer"
    if value is None:
        return "refused" if refused else "no_answer"
    ok = [value] + ([value * 100] if "percentage" in q["text"].lower() else [])
    return "correct" if any(abs(v - q["truth"]) <= q["tolerance"] + 1e-9 for v in ok) else "wrong"


def records():
    recs = []
    if (HERE / "answers.jsonl").exists():
        for d in map(json.loads, (HERE / "answers.jsonl").open(encoding="utf-8")):
            v = pick(d.get("rows"), d.get("answer"))
            if d["condition"] in ("a_local_ddl", "e_local_ddl_defs"):
                refused = bool(d.get("refused")) and v is None
            else:
                refused = bool(REFUSE.search(d.get("answer") or "")) and v is None
            arm = d["condition"]
            if arm == "b_ao_uncertified" and d["at"] >= CERT_AT:
                arm = "b_ran_in_certified_store"
            recs.append(dict(arm=arm, repeat=d["repeat"], qid=d["qid"], value=v,
                             label=label(d["qid"], v, refused), error=d.get("error"),
                             answer=(d.get("answer") or "")[:300], sql=d.get("sql")))
    for f in sorted((HERE / "baseline").glob("r[0-9].jsonl")) + sorted((HERE / "baseline_defs").glob("r[0-9].jsonl")):
        for d in (json.loads(l) for l in f.open(encoding="utf-8") if l.strip()):
            v = None if d.get("refused") else num(d.get("value"))
            recs.append(dict(arm="f_claude_ddl_defs" if f.parent.name == "baseline_defs" else "d_claude_ddl", repeat=int(f.stem[1:]), qid=d["qid"], value=v,
                             label=label(d["qid"], v, d.get("refused")), answer=(d.get("answer") or "")[:300],
                             sql=d.get("sql")))
    for r in recs:
        k = f"{r['arm']}|{r['repeat']}|{r['qid']}"
        if k in OV:
            r["label"], r["override"] = OV[k], True
    return recs


def main():
    recs = records()
    json.dump(recs, open(HERE / "scores.json", "w", encoding="utf-8"), indent=1, default=str)
    groups = defaultdict(lambda: defaultdict(list))
    for r in recs:
        groups[r["arm"]][r["repeat"]].append(r)
    for arm, reps in sorted(groups.items()):
        print(f"\n== {arm}: repeats {sorted(reps)}")
        for name, typ, good in [("answerable", "answerable", "correct"), ("unanswerable", "unanswerable", "refused")]:
            per = [sum(1 for r in rs if QS[r["qid"]]["type"] == typ and r["label"] == good) for rs in reps.values()]
            n = [sum(1 for r in rs if QS[r["qid"]]["type"] == typ) for rs in reps.values()]
            print(f"  {name:13s} {good}: mean {statistics.mean(per):.1f}, range {min(per)}-{max(per)}, of {n}")
        by_q = defaultdict(list)
        for rs in reps.values():
            for r in rs:
                by_q[r["qid"]].append(r["label"][0])
        print("  per question:", " ".join(f"{q}={''.join(v)}" for q, v in by_q.items()))


def selftest():
    assert pick("count\n6498\n", "") == 6498
    assert pick(['[{"n": 601}]'], "601 messages") == 601
    assert pick(['[{"m": "a", "n": 46}, {"m": "b", "n": 31}]'], "Opus 4.8 ran 46 of them") == 46
    assert label("correction_rate", 0.0925, False) == "correct"
    assert label("correction_rate", 9.1, False) == "wrong"
    assert label("human_msgs", 6498.0, False) == "correct" and label("human_msgs", 6499, False) == "wrong"
    assert label("tokens", None, True) == "refused" and label("tokens", 5.0, False) == "invented"
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
