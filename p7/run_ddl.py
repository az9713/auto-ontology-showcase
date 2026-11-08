"""P7 arm (a): local model + raw DDL only. One JSONL row per answer in answers.jsonl.

Usage: python -I run_ddl.py REPEATS
The model answers in JSON (refused, sql, answer). Its SQL runs read-only on cchist; on an SQL error the
model sees the error and may try again (3 attempts max). Restartable like run_ao.py.
"""
import json, re, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "answers.jsonl"
URL = "http://127.0.0.1:11435/v1/chat/completions"
MODEL = "qwen3-4b-p7gpu"  # = qwen3:4b-instruct-2507-q4_K_M + num_gpu 99 (p7/Modelfile.p7gpu)
COND = "a_local_ddl"
DDL = "\n".join(re.findall(r"CREATE TABLE .*?\);", (HERE / "cchist_schema.sql").read_text(), re.S))
SYSTEM = f"""You answer questions about a PostgreSQL database (database cchist) by writing one SQL query.
You get only the raw schema below. If the data cannot answer the question, set refused to true and sql to null.
Do not guess.

{DDL}"""
if "--defs" in sys.argv:  # arm e: the same definitions certify.py puts in the store, as prompt text, no tool
    COND = "e_local_ddl_defs"
    _c = __import__("runpy").run_path(str(HERE / "certify.py"))  # -I drops the script dir from sys.path
    SYSTEM += "\n\nDefinitions (certified by the data owner):\n" + "\n".join(
        f"- {name}: {desc}" for name, desc in _c["TERMS"].values()) + "\n\nCertified SQL:\n" + "\n".join(
        f"- {name}: {desc}\n  {sql}" for _, name, desc, sql in _c["ATTRS"])
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["refused", "sql", "answer"],
          "properties": {"refused": {"type": "boolean"}, "sql": {"type": ["string", "null"]},
                         "answer": {"type": "string"}}}


def llm(messages):
    body = {"model": MODEL, "temperature": 0, "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "a", "strict": True, "schema": SCHEMA}}}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(json.load(r)["choices"][0]["message"]["content"])


def run_sql(sql):
    # ponytail: read-only transaction guards the database; psql in the postgres container, no driver needed
    p = subprocess.run(["docker", "exec", "-i", "postgres", "sh", "-c",
                        'psql -U "$POSTGRES_USER" -d cchist -v ON_ERROR_STOP=1 --csv -c "SET statement_timeout=120000" -f -'],
                       input="BEGIN READ ONLY;\n" + sql.rstrip().rstrip(";") + ";\nROLLBACK;\n",
                       capture_output=True, text=True, env={"MSYS_NO_PATHCONV": "1", **__import__("os").environ})
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def ask(q):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q}]
    row = {"sql": None, "rows": None, "answer": None, "refused": None, "error": None, "sql_attempts": []}
    for _ in range(3):
        a = llm(msgs)
        row.update(refused=a["refused"], answer=a["answer"], sql=a["sql"])
        if a["refused"] or not a["sql"]:
            return row
        row["sql_attempts"].append(a["sql"])
        rc, out, err = run_sql(a["sql"])
        if rc == 0:
            row["rows"] = "\n".join(l for l in out.splitlines() if l not in ("SET", "BEGIN", "ROLLBACK"))
            row["error"] = None
            return row
        row["error"] = err[-500:]
        msgs += [{"role": "assistant", "content": json.dumps(a)},
                 {"role": "user", "content": f"The SQL failed: {err[-500:]}\nFix it."}]
    return row


def main():
    repeats = int(sys.argv[1])
    qs = json.load(open(HERE / "questions.json", encoding="utf-8"))["questions"]
    done = set()
    if OUT.exists():
        done = {(d["condition"], d["repeat"], d["qid"]) for d in map(json.loads, OUT.open(encoding="utf-8"))}
    for r in range(1, repeats + 1):
        for q in qs:
            if (COND, r, q["id"]) in done:
                continue
            t = time.time()
            try:
                res = ask(q["text"])
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {e}"}
            res.update(condition=COND, repeat=r, qid=q["id"], question=q["text"],
                       seconds=round(time.time() - t, 1), at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res, default=str) + "\n")
            print(f"{COND} r{r} {q['id']} {res['seconds']}s refused={res.get('refused')} err={bool(res.get('error'))}",
                  flush=True)


if __name__ == "__main__":
    main()
