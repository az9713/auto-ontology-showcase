"""P8: freeze the questions and the level sets.

  python -I freeze.py   # reads pool.json + questions_draft.json, writes questions.json, levels.json, checks.txt (+ sha256)

Truth: copy and near-variant = the target's truth in pool.json; compose = truth_sql run now.
K (in every level) = targets + traps + compose inputs + the 9 P7 definitions. L0 = K.
L1/L2/L3 = K + the first (size - |K|) ids of the other pool ids in a seeded shuffle (seed 8), so the levels are nested.
"""
import hashlib, json, random, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
SIZES = {"L1": 200, "L2": 1000, "L3": 5000}
USES = {"m01": ["Questions Followed By An Edit", "User Questions"], "m02": ["Failed Read Calls"],
        "m03": ["Kill-By-Pattern Commands", "Kill-By-Pattern Commands (Opus 4.8)"],
        "m04": ["Tool Calls", "Typed User Messages"],
        "m05": ["Stopped Early Corrections (Opus 4.8)", "Stopped Early Corrections (Opus 5)", "Stopped Early Corrections (Opus 4.7)"],
        "m06": ["Denied Tool Calls", "Denied Bash Calls"], "m07": ["Failed Read Calls", "Failed Read Calls (Main Agent)"],
        "m08": ["Risky Shell Commands"], "m09": ["Over-Building Correction Messages", "Stopped Early Correction Messages"],
        "m10": ["Bash Calls", "PowerShell Calls"]}


def run_sql(sql: str) -> float:
    r = subprocess.run(["docker", "exec", "postgres", "psql", "-U", "postgres", "-d", "cchist", "-A", "-t", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    return float(r.stdout.strip())


pool = json.loads((HERE / "pool.json").read_text(encoding="utf-8"))
by_name = {d["name"]: d for d in pool}
qs = json.loads((HERE / "questions_draft.json").read_text(encoding="utf-8"))
checks, K = [], {d["id"] for d in pool if d["origin"] == "p7"}
for q in qs["questions"]:
    q.setdefault("tolerance", 0)
    if q["class"] in ("copy", "near-variant"):
        t = by_name[q["target"]]
        q["truth"], q["target_id"] = t["truth"], t["id"]
        K.add(t["id"])
        same = [d["name"] for d in pool if d["id"] != t["id"] and abs(d["truth"] - t["truth"]) <= q["tolerance"]]
        checks.append(f"{q['id']} target {t['name']!r} = {t['truth']}; pool definitions with the same truth: {len(same)} {same[:6]}")
        if "trap" in q:
            tr = by_name[q["trap"]]
            q["trap_id"], q["trap_truth"] = tr["id"], tr["truth"]
            K.add(tr["id"])
            ok = abs(tr["truth"] - t["truth"]) > q["tolerance"]
            checks.append(f"{q['id']} trap {tr['name']!r} = {tr['truth']} -> {'DIFFERENT (ok)' if ok else 'SAME (FAIL)'}")
            if not ok:
                sys.exit("\n".join(checks))
    elif q["class"] == "compose":
        q["truth"] = round(run_sql(q["truth_sql"]), 4)
        if "alt_truth_sql" in q:
            q["alt_truth"] = round(run_sql(q["alt_truth_sql"]), 4)
        q["uses"] = USES[q["id"]]
        for n in q["uses"]:
            K.add(by_name[n]["id"])
        checks.append(f"{q['id']} compose truth {q['truth']} alt {q.get('alt_truth')}")

others = sorted(d["id"] for d in pool if d["id"] not in K)
random.Random(8).shuffle(others)
levels = {"L0": sorted(K)}
for lv, n in SIZES.items():
    levels[lv] = sorted(K) + others[: n - len(K)]
checks.append(f"|K| = {len(K)}; level sizes " + ", ".join(f"{k} {len(v)}" for k, v in levels.items()))
for name, obj in (("questions.json", qs), ("levels.json", levels)):
    text = json.dumps(obj, indent=0, ensure_ascii=False)
    (HERE / name).write_text(text, encoding="utf-8")
    checks.append(f"sha256 {name} {hashlib.sha256(text.encode()).hexdigest()}")
(HERE / "checks.txt").write_text("\n".join(checks) + "\n", encoding="utf-8")
print("\n".join(checks))
