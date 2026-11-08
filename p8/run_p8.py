"""P8 runner: one run = 1 arm x 1 level x 1 repeat = 3 claude -p processes of 15 questions each (fixed split: question k
goes to batch k % 3). Same model, flags and prompt frame in every arm; only the definition section differs.

  python -I run_p8.py P L1 1        # arm P|R|O, level L0..L3, repeat number
  python -I run_p8.py P L3 0 --probe  # window probe: the full prompt with no questions, reply OK

Outputs in runs/<arm>_<level>_r<rep>_b<k>.{jsonl,run.json,err}. A batch with a .run.json is skipped (restartable).
The processes run in runs/work (an empty folder), with only Bash (psql, and search.py for R) and Write allowed.
Arm O: the store must hold the level (load_store.py); the MCP token is refreshed before each process.
"""
import json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).parent.resolve()
RUNS = HERE / "runs"
WORK = RUNS / "work"
PY = sys.executable
MODEL = "claude-opus-5-5"
TIMEOUT_S = 50 * 60  # the MCP token lives 3,600 s; a batch must end before it
PSQL = "docker exec postgres psql -U postgres -d cchist"
SEARCH = f"python -I {HERE.as_posix()}/search.py"
O_TOOLS = ["search_terms", "get_term", "get_term_sql_attributes", "get_sql_attribute", "describe_table", "check_answerable"]
O_DENY = ["ask_question", "check_readiness", "get_term_columns"]
P7_DDL = (HERE.parent / "p7" / "cchist_schema.sql").read_text(encoding="utf-8")
BASE_DDL = P7_DDL[P7_DDL.index("CREATE TABLE human_message"): P7_DDL.index("\\copy")].strip()
DDL = BASE_DDL + "\n" + (HERE / "decoy_ddl.txt").read_text(encoding="utf-8").strip()

HEAD = f"""You are an agent in a benchmark. Answer questions about a log of a user's sessions with AI coding agents by
writing SQL against a Postgres database.

Rules:
1. Run SQL only with this command form in the Bash tool:
   {PSQL} -A -F '|' -c "<SQL>"
2. Do not read, list or open any file on disk. Do not use the web. Every number must come from a query result.
3. If the data cannot answer a question, say so (refused = true). Do not guess.
4. Answer each question on its own terms. Give a single number where a number is asked
   (a percentage as a number of percent, for example 12.5).

Schema (database cchist, schema public):
{DDL}
"""

TAIL = """
Output: write one JSON Lines file at the path given below with the Write tool, one line per question:
{"qid": "...", "refused": true|false, "value": <number or null>, "answer": "<one sentence>", "sql": "<the final SQL you used, or null>"}
Then reply with only the word DONE.
"""


def defs_text(level: str) -> str:
    pool = {d["id"]: d for d in json.loads((HERE / "pool.json").read_text(encoding="utf-8"))}
    ids = json.loads((HERE / "levels.json").read_text(encoding="utf-8"))[level]
    sys.path.insert(0, str(HERE.parent / "p7"))
    import certify
    terms = "\n".join(f"- {n}: {d}" for n, d in certify.TERMS.values())
    attrs = "\n".join(f"- {pool[i]['name']}: {pool[i]['description']}\n  SQL: {pool[i]['sql']}" for i in ids)
    return f"\nDefinitions (certified by the data owner):\n{terms}\n\nCertified SQL ({len(ids)} definitions):\n{attrs}\n"


def arm_text(arm: str, level: str) -> str:
    if arm == "P":
        return defs_text(level)
    if arm == "R":
        return f"""
Certified definitions (certified by the data owner) are in a search index. Search it with this command in the Bash tool:
   {SEARCH} {level} "<words>"
It prints the 10 definitions closest to the words (name, description, SQL). You can search as often as you like, with
other words. Use the definitions: they say what each term means in this data.
"""
    return """
Certified definitions (certified by the data owner) are in a semantic layer. Read it with the auto-ontology MCP tools
(search_terms, get_term, get_term_sql_attributes, get_sql_attribute, describe_table, check_answerable). Terms carry
descriptions; SQL attributes are certified SQL definitions under a term. Use the definitions: they say what each term
means in this data. Run SQL yourself with the command in rule 1.
"""


def flags(arm: str) -> list[str]:
    allow = [f"Bash({PSQL}:*)", "Write"]
    f = ["--setting-sources", "local", "--model", MODEL, "--tools", "Bash,Write", "--output-format", "json",
         "--no-session-persistence", "--strict-mcp-config"]
    if arm == "R":
        allow.append(f"Bash({SEARCH}:*)")
    if arm == "O":
        allow += [f"mcp__auto-ontology__{t}" for t in O_TOOLS]
        f += ["--mcp-config", str(HERE / "mcp_auth.json"), "--disallowedTools"] + [f"mcp__auto-ontology__{t}" for t in O_DENY]
    return f + ["--allowedTools"] + allow


def run_batch(arm: str, level: str, rep: int, b: int, questions: list[dict], probe: bool = False) -> None:
    stem = RUNS / (f"probe_{arm}_{level}" if probe else f"{arm}_{level}_r{rep}_b{b}")
    if Path(str(stem) + ".run.json").exists():
        print("skip", stem.name)
        return
    if arm == "O":
        subprocess.run([PY, "-I", str(HERE / "mcp_login.py"), "--refresh"], check=True, capture_output=True)
    out = Path(str(stem) + ".jsonl")
    if probe:
        prompt = HEAD + arm_text(arm, level) + "\nThis is a size probe. Do not run any tool. Reply with only the word OK.\n"
    else:
        qtext = "\n".join(f"- {q['id']}: {q['text']}" for q in questions)
        prompt = HEAD + arm_text(arm, level) + f"\nQuestions:\n{qtext}\n" + TAIL + f"\nOutput file: {out.as_posix()}\n"
    t0 = time.time()
    with open(str(stem) + ".run.json", "wb") as so, open(str(stem) + ".err", "wb") as se:
        p = subprocess.Popen(["claude", "-p"] + flags(arm), stdin=subprocess.PIPE, stdout=so, stderr=se, cwd=WORK)
        try:
            p.communicate(prompt.encode("utf-8"), timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            p.kill()  # the PID this script started; never by name
            p.wait()
            se.write(b"\nP8 TIMEOUT\n")
    print(f"{stem.name}: exit {p.returncode}, {time.time() - t0:.0f} s, prompt {len(prompt)} chars", flush=True)


if __name__ == "__main__":
    arm, level, rep = sys.argv[1], sys.argv[2], int(sys.argv[3])
    WORK.mkdir(parents=True, exist_ok=True)
    if "--probe" in sys.argv:
        run_batch(arm, level, 0, 0, [], probe=True)
        sys.exit()
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))["questions"]
    for b in range(3):
        run_batch(arm, level, rep, b, [q for k, q in enumerate(qs) if k % 3 == b])
