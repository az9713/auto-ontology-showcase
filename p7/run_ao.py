"""P7 copy of p2/run_ao.py: sends target_db=cchist, 1 worker by default (one local model slot).

Ask the P7 questions (database cchist) through auto-ontology's chat API; one JSONL row per answer.

Usage: python -I run_ao.py CONDITION REPEATS [WORKERS] [QID_PREFIX...]
Restartable: a (condition, repeat, qid) already in answers.jsonl is skipped.
"""
import json, sys, time, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "answers.jsonl"
URL = "http://localhost:3001/api/chat/completions"
TIMEOUT_S = 1500
lock = threading.Lock()


def ask(question: str) -> dict:
    req = urllib.request.Request(URL, json.dumps({"question": question, "target_db": "cchist"}).encode(),
                                 {"Content-Type": "application/json"})
    row = {"sql": None, "rows": None, "answer": None, "error": None, "sql_attempts": []}
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                ev = json.loads(payload)
                if ev.get("type") == "sql":
                    row["sql_attempts"].append(ev.get("sql") or ev.get("content"))
                elif ev.get("type") == "result":
                    a = ev.get("answer") or {}
                    row.update(answer=a.get("response"), sql=a.get("sql_code"),
                               rows=a.get("sql_response_from_db"))
                elif ev.get("type") == "error":
                    row["error"] = ev.get("message")
    except Exception as e:  # timeout or connection error: recorded, not retried
        row["error"] = f"{type(e).__name__}: {e}"
    return row


def main() -> None:
    cond, repeats = sys.argv[1], int(sys.argv[2])
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    prefixes = tuple(sys.argv[4:])
    qs = json.load(open(HERE / "questions.json"))["questions"]
    if prefixes:
        qs = [q for q in qs if q["id"].startswith(prefixes)]
    done = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            d = json.loads(line)
            done.add((d["condition"], d["repeat"], d["qid"]))
    jobs = [(r, q) for r in range(1, repeats + 1) for q in qs if (cond, r, q["id"]) not in done]
    print(f"{len(jobs)} jobs, {workers} workers", flush=True)

    def run(job):
        r, q = job
        t = time.time()
        res = ask(q["text"])
        res.update(condition=cond, repeat=r, qid=q["id"], question=q["text"],
                   seconds=round(time.time() - t, 1), at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        with lock:
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res, default=str) + "\n")
        print(f"{cond} r{r} {q['id']} {res['seconds']}s err={bool(res['error'])}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(run, jobs))


if __name__ == "__main__":
    main()
