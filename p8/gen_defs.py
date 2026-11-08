"""P8: generate the definition pool from templates over the cchist schema, compute each truth by running its SQL, freeze.

  python -I gen_defs.py        # writes pool.json (all definitions with truth > 0, deduplicated by SQL) and pool.sha256

Each definition = id, name, description, sql, table (the table its FROM starts at), family, origin, truth.
The 9 P7 certified SQL attributes are members with origin "p7" (same name, description and SQL as p7/certify.py).
No question exists when this runs; questions are written after the freeze.
"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
T = "cchist.public."
TYPED = "NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0"
QUESTION = "h.chars < 400 AND (h.ends_with_q OR h.question_start) AND NOT h.imperative"
EDIT_TOOLS = "('Edit', 'Write', 'NotebookEdit', 'MultiEdit')"

MODELS = [(None, ""), ("claude-opus-4-8", "Opus 4.8"), ("claude-fable-5", "Fable 5"), ("claude-opus-5", "Opus 5"),
          ("claude-sonnet-5", "Sonnet 5"), ("claude-sonnet-4-6", "Sonnet 4.6"),
          ("claude-haiku-4-5-20251001", "Haiku 4.5"), ("claude-opus-4-7", "Opus 4.7")]

# (sql condition on alias c, name, description phrase)
TOOLS = [(None, "Tool Calls", "tool calls of every tool"),
         ("c.tool_name = 'Read'", "Read Calls", "Read tool calls"),
         ("c.tool_name = 'Bash'", "Bash Calls", "Bash tool calls"),
         ("c.tool_name = 'Edit'", "Edit Calls", "Edit tool calls"),
         ("c.tool_name = 'Write'", "Write Calls", "Write tool calls"),
         ("c.tool_name = 'Grep'", "Grep Calls", "Grep tool calls"),
         ("c.tool_name = 'Glob'", "Glob Calls", "Glob tool calls"),
         ("c.tool_name = 'WebFetch'", "Web Fetch Calls", "WebFetch tool calls"),
         ("c.tool_name = 'WebSearch'", "Web Search Calls", "WebSearch tool calls"),
         ("c.tool_name = 'PowerShell'", "PowerShell Calls", "PowerShell tool calls"),
         ("c.tool_name = 'Agent'", "Subagent Launches", "Agent tool calls (each starts a subagent)"),
         ("c.tool_name = 'Skill'", "Skill Calls", "Skill tool calls"),
         ("c.tool_name = 'ToolSearch'", "Tool Search Calls", "ToolSearch tool calls"),
         (f"c.tool_name IN {EDIT_TOOLS}", "File-Changing Calls", "file-changing tool calls (Edit, Write, NotebookEdit, MultiEdit)"),
         ("c.tool_name LIKE 'mcp\\_\\_%'", "MCP Tool Calls", "MCP tool calls (tool_name starts with mcp__)"),
         ("c.tool_name LIKE 'mcp\\_\\_claude-in-chrome%'", "Chrome Browser Calls", "Claude-in-Chrome browser tool calls")]
SIDE = [(None, "", ""), ("NOT c.is_sidechain", "Main Agent", "main agent only (is_sidechain false)"),
        ("c.is_sidechain", "Subagent", "subagents only (is_sidechain true)")]

CALL_TABLES = [("tool_call", "", "from tool_call (one row per call)", None),
               ("stg_tool_call", "Staging", "from the staging table stg_tool_call (raw loads; some rows were loaded twice)", None),
               ("tool_call_2026h1", "H1 2026", "from tool_call_2026h1 (calls before 2026-07-01)", None),
               ("tool_call_2026h2", "H2 2026", "from tool_call_2026h2 (calls on or after 2026-07-01)", None),
               ("tool_call_opus", "Opus Split", "from tool_call_opus (Opus-family calls only)", "claude-opus"),
               ("tool_call_sonnet", "Sonnet Split", "from tool_call_sonnet (Sonnet-family calls only)", "claude-sonnet"),
               ("tool_call_fable", "Fable Split", "from tool_call_fable (Fable-family calls only)", "claude-fable"),
               ("tool_call_archive", "Archive", "from tool_call_archive (old log format: is_sidechain was not recorded and is false on every row)", None)]
RESULT_TABLES = [("tool_result", "", "from tool_result joined to tool_call on call_id"),
                 ("stg_tool_result", "Staging", "from the staging table stg_tool_result (raw loads; some rows were loaded twice) joined to tool_call on call_id"),
                 ("tool_result_2026h1", "H1 2026", "from tool_result_2026h1 (results before 2026-07-01) joined to tool_call on call_id"),
                 ("tool_result_2026h2", "H2 2026", "from tool_result_2026h2 (results on or after 2026-07-01) joined to tool_call on call_id"),
                 ("tool_result_archive", "Archive", "from tool_result_archive (old log format: denied_mark was not recorded and is false on every row) joined to tool_call on call_id")]
FAILS = [("r.is_error AND NOT r.denied_mark AND NOT r.validation_mark", "Failed", "failed (is_error true, not denied, not a validation error)"),
         ("r.is_error", "Errored", "with an error of any kind (is_error true; denied and validation errors included)"),
         ("r.denied_mark", "Denied", "denied by the user or a permission rule (denied_mark true)"),
         ("r.validation_mark", "Validation-Rejected", "rejected by input validation (validation_mark true)")]
HM_TABLES = [("human_message", "", "from human_message"),
             ("stg_human_message", "Staging", "from the staging table stg_human_message (raw loads; some rows were loaded twice)"),
             ("human_message_2026q2", "Q2 2026", "from human_message_2026q2 (messages before 2026-07-01)"),
             ("human_message_2026q3", "Q3 2026", "from human_message_2026q3 (messages on or after 2026-07-01)"),
             ("human_message_archive", "Archive", "from human_message_archive (old classifier: is_noise was not set and is false on every row)")]
MSG_KINDS = [(TYPED, "Typed User Messages", "typed user messages (not sidechain, not noise, chars > 0)"),
             ("true", "Message Records", "all message records, including subagent prompts and noise"),
             ("h.is_sidechain", "Subagent Prompts", "prompts sent to subagents (is_sidechain true)"),
             ("h.is_noise", "Noise Messages", "system and command text (is_noise true)"),
             (f"{TYPED} AND {QUESTION}", "User Questions", "questions the user asked (typed, chars < 400, ends with ? or starts like a question, not imperative)"),
             (f"{TYPED} AND h.chars >= 400", "Long User Messages", "typed user messages of 400 characters or more"),
             (f"{TYPED} AND h.imperative", "Instruction Messages", "typed user messages classed as imperative"),
             (f"{TYPED} AND h.ends_with_q", "Messages Ending With A Question Mark", "typed user messages that end with a question mark")]
CATS = [(None, "Corrections", "corrections of any category (pattern_id 1-21)"),
        ("p.pattern_id BETWEEN 1 AND 2", "Blunt-No Corrections", "'blunt no' corrections (pattern_id 1-2)"),
        ("p.pattern_id BETWEEN 3 AND 5", "Misread Corrections", "'misread' corrections (pattern_id 3-5)"),
        ("p.pattern_id BETWEEN 6 AND 8", "Unsolicited-Edit Corrections", "'unsolicited edit' corrections (pattern_id 6-8)"),
        ("p.pattern_id BETWEEN 9 AND 11", "Over-Building Corrections", "'over-building' corrections (pattern_id 9-11)"),
        ("p.pattern_id BETWEEN 12 AND 15", "Stopped Early Corrections", "'stopped early' corrections (pattern_id 12-15)"),
        ("p.pattern_id BETWEEN 16 AND 17", "No-Verification Corrections", "'no verification' corrections (pattern_id 16-17)"),
        ("p.pattern_id BETWEEN 18 AND 19", "Regression Corrections", "'regression' corrections (pattern_id 18-19)"),
        ("p.pattern_id BETWEEN 20 AND 21", "Tool-Misuse Corrections", "'tool misuse' corrections (pattern_id 20-21)")]
HIT_TABLES = [("message_pattern_hit", "", "message_pattern_hit"),
              ("stg_message_pattern_hit", "Staging Hits", "the staging table stg_message_pattern_hit (raw loads; some hits were loaded twice)")]
DANGERS = [(None, "Risky Shell Commands", "risky shell command hits of any danger pattern"),
           ("d.pattern_id IN (1, 2)", "Kill-By-Pattern Commands", "kill-by-pattern commands (danger pattern_id 1-2: pkill, taskkill)"),
           ("d.pattern_id IN (3, 4)", "Kill-By-PID Commands", "kill-by-PID commands (danger pattern_id 3-4)"),
           ("d.pattern_id IN (5, 6)", "Recursive Delete Commands", "rm -rf commands (danger pattern_id 5-6)"),
           ("d.pattern_id = 7", "Hard Reset Commands", "git reset --hard commands (danger pattern_id 7)"),
           ("d.pattern_id = 8", "Force Push Commands", "git push --force commands (danger pattern_id 8)"),
           ("d.pattern_id = 9", "Git Clean Commands", "git clean commands (danger pattern_id 9)"),
           ("d.pattern_id = 10", "Checkout-Discard Commands", "git checkout -- commands (danger pattern_id 10)")]
DANGER_TABLES = [("call_danger_hit", "", "call_danger_hit"),
                 ("call_danger_hit_v1", "V1 Taxonomy", "call_danger_hit_v1 (older taxonomy: pattern_id 2 was folded into 1 and 4 into 3)")]
DANGER_CALLS = [("tool_call", "", "tool_call"), ("tool_call_2026h1", "H1 2026", "tool_call_2026h1 (calls before 2026-07-01)"),
                ("tool_call_2026h2", "H2 2026", "tool_call_2026h2 (calls on or after 2026-07-01)"),
                ("stg_tool_call", "Staging", "the staging table stg_tool_call (some rows loaded twice)")]


def name_of(base: str, quals: list[str]) -> str:
    quals = [q for q in quals if q]
    return base + (" (" + ", ".join(quals) + ")" if quals else "")


def where(*conds) -> str:
    conds = [c for c in conds if c]
    return " WHERE " + " AND ".join(conds) if conds else ""


def model_phrase(label: str) -> str:
    return f", model {label}" if label else ", all models"


def p7_defs() -> list[dict]:
    sys.path.insert(0, str(HERE.parent / "p7"))
    import certify  # noqa: E402  the P7 definitions, unchanged
    tables = {"Typed User Messages": "human_message", "User Questions": "human_message",
              "Questions Followed By An Edit": "human_message", "Correction Messages": "human_message",
              "Stopped Early Corrections": "human_message", "Over-Building Corrections": "human_message",
              "Read Calls": "tool_call", "Kill-By-Pattern Commands": "call_danger_hit", "Failed Read Calls": "tool_result"}
    return [dict(name=n, description=d, sql=s, table=tables[n], family="p7", origin="p7") for _, n, d, s in certify.ATTRS]


def generate() -> list[dict]:
    out = []

    def add(name, desc, sql, table, family):
        if sql.startswith("SELECT count(*) AS n FROM") and sql[-2:] in (" c", " h"):  # store rejects SQL with no column reference
            sql = sql.replace("count(*)", "count(c.call_id)" if sql.endswith(" c") else "count(h.msg_id)")
        out.append(dict(name=name, description=desc, sql=sql, table=table, family=family, origin="template"))

    # F1 tool-call counts
    for tab, tq, tdesc, fam in CALL_TABLES:
        for mod, ml in MODELS:
            if fam and mod and not mod.startswith(fam):
                continue
            for tc, tn, td in TOOLS:
                for sc, sn, sd in SIDE:
                    add(name_of(tn, [ml, sn, tq]), f"Count of {td}{', ' + sd if sd else ''}{model_phrase(ml)}, {tdesc}.",
                        f"SELECT count(*) AS n FROM {T}{tab} c" + where(tc, sc, mod and f"c.model = '{mod}'"), tab, "calls")
    # F2 failed / errored / denied results
    for tab, tq, tdesc in RESULT_TABLES:
        for fc, fn, fd in FAILS:
            for mod, ml in MODELS:
                for tc, tn, td in TOOLS[:11] + TOOLS[13:15]:
                    for sc, sn, sd in SIDE[:2]:
                        add(name_of(f"{fn} {tn}", [ml, sn, tq]),
                            f"Count of {td} {fd}{', ' + sd if sd else ''}{model_phrase(ml)}, {tdesc}.",
                            f"SELECT count(*) AS n FROM {T}{tab} r JOIN {T}tool_call c ON c.call_id = r.call_id"
                            + where(tc, fc, sc, mod and f"c.model = '{mod}'"), tab, "results")
    # F3 message counts
    for tab, tq, tdesc in HM_TABLES:
        for kc, kn, kd in MSG_KINDS:
            for mod, ml in MODELS:
                add(name_of(kn, [ml, tq]), f"Count of {kd}{model_phrase(ml)}, {tdesc}.",
                    f"SELECT count(*) AS n FROM {T}{tab} h" + where(kc if kc != "true" else None, mod and f"h.model = '{mod}'"),
                    tab, "messages")
    # F3b questions followed by a tool call
    follow = [(f"t.tool_name IN {EDIT_TOOLS} AND NOT t.is_sidechain", "Questions Followed By An Edit", "an edit by the main agent (Edit, Write, NotebookEdit, MultiEdit; is_sidechain false)"),
              (f"t.tool_name IN {EDIT_TOOLS}", "Questions Followed By An Edit Incl. Subagents", "an edit by the main agent or a subagent"),
              ("NOT t.is_sidechain", "Questions Followed By A Tool Call", "any tool call by the main agent"),
              ("t.tool_name = 'Bash' AND NOT t.is_sidechain", "Questions Followed By A Bash Call", "a Bash call by the main agent")]
    for tab, tq, tdesc in HM_TABLES:
        for fc, fn, fd in follow:
            add(name_of(fn, [tq]), f"Count of user questions followed by {fd} before the next typed user message of the same file, {tdesc}.",
                f"WITH c AS (SELECT h.file_id, h.line_no, {QUESTION} AS is_q, lead(h.line_no) OVER (PARTITION BY h.file_id ORDER BY h.line_no) AS next_line "
                f"FROM {T}{tab} h WHERE {TYPED}) SELECT count(*) AS n FROM c WHERE c.is_q AND EXISTS (SELECT 1 FROM {T}tool_call t "
                f"WHERE t.file_id = c.file_id AND t.line_no > c.line_no AND (c.next_line IS NULL OR t.line_no < c.next_line) AND {fc})",
                tab, "follow")
    # F4 corrections
    for htab, hq, hdesc in HIT_TABLES:
        for tab, tq, tdesc in HM_TABLES:
            for cc, cn, cd in CATS:
                for mod, ml in MODELS:
                    for measure in ("hits", "messages"):
                        base = cn if measure == "hits" else cn.replace("Corrections", "Correction Messages")
                        what = (f"Count of {cd} as hits (rows)" if measure == "hits"
                                else f"Count of typed user messages with at least 1 of the {cd} (distinct msg_id)")
                        sel = "count(*)" if measure == "hits" else "count(DISTINCT h.msg_id)"
                        add(name_of(base, [ml, tq, hq]), f"{what} on typed user messages{model_phrase(ml)}, hits from {hdesc}, messages {tdesc}.",
                            f"SELECT {sel} AS n FROM {T}{tab} h JOIN {T}{htab} p ON p.msg_id = h.msg_id"
                            + where(TYPED, cc, mod and f"h.model = '{mod}'"), htab, "corrections")
    # F5 risky shell commands
    for dtab, dq, ddesc in DANGER_TABLES:
        for ctab, cq, cdesc in DANGER_CALLS:
            for dc, dn, dd in DANGERS:
                for mod, ml in MODELS:
                    add(name_of(dn, [ml, cq, dq]), f"Count of {dd} as hits{model_phrase(ml)}, hits from {ddesc} joined to {cdesc} on call_id, attributed to tool_call.model.",
                        f"SELECT count(*) AS n FROM {T}{dtab} d JOIN {T}{ctab} c ON c.call_id = d.call_id"
                        + where(dc, mod and f"c.model = '{mod}'"), dtab, "danger")
    # F6 rollups
    for mod, ml in MODELS:
        for tc, tn, td in TOOLS:
            for sc, sn, sd in SIDE:
                add(name_of(tn, [ml, sn, "Daily Rollup"]), f"Sum of n_calls over {td}{', ' + sd if sd else ''}{model_phrase(ml)}, from the daily rollup tool_call_daily.",
                    f"SELECT sum(c.n_calls) AS n FROM {T}tool_call_daily c" + where(tc, sc, mod and f"c.model = '{mod}'"), "tool_call_daily", "rollup")
        for col, cn, cd in (("typed_messages", "Typed User Messages", "typed user messages"),
                            ("sidechain_prompts", "Subagent Prompts", "subagent prompts"), ("noise_messages", "Noise Messages", "noise messages")):
            add(name_of(cn, [ml, "Daily Rollup"]), f"Sum of {col} ({cd}){model_phrase(ml)}, from the daily rollup human_message_daily.",
                f"SELECT sum(h.{col}) AS n FROM {T}human_message_daily h" + where(mod and f"h.model = '{mod}'"), "human_message_daily", "rollup")
    # F7 rates on the base tables
    for mod, ml in MODELS:
        mc = mod and f"c.model = '{mod}'"
        for tc, tn, td in TOOLS[:11] + TOOLS[13:15]:
            add(name_of(f"{tn} Failure Rate", [ml]),
                f"Percent of {td} that failed (is_error true, not denied, not a validation error){model_phrase(ml)}: 100 x failed results / calls, from tool_call and tool_result.",
                f"SELECT 100.0 * (SELECT count(*) FROM {T}tool_result r JOIN {T}tool_call c ON c.call_id = r.call_id"
                + where(tc, "r.is_error AND NOT r.denied_mark AND NOT r.validation_mark", mc)
                + f") / NULLIF((SELECT count(*) FROM {T}tool_call c" + where(tc, mc) + "), 0) AS pct", "tool_result", "rates")
        hm = mod and f"h.model = '{mod}'"
        add(name_of("Correction Rate", [ml]), f"Percent of typed user messages with at least 1 correction{model_phrase(ml)}: 100 x correction messages / typed user messages.",
            f"SELECT 100.0 * (SELECT count(DISTINCT h.msg_id) FROM {T}human_message h JOIN {T}message_pattern_hit p ON p.msg_id = h.msg_id"
            + where(TYPED, hm) + f") / NULLIF((SELECT count(*) FROM {T}human_message h" + where(TYPED, hm) + "), 0) AS pct", "human_message", "rates")
        add(name_of("Question Rate", [ml]), f"Percent of typed user messages that are questions{model_phrase(ml)}.",
            f"SELECT 100.0 * count(*) FILTER (WHERE {QUESTION}) / NULLIF(count(*), 0) AS pct FROM {T}human_message h" + where(TYPED, hm),
            "human_message", "rates")
    return out


def truths(defs: list[dict]) -> list:
    """Run every SQL in 1 psql session; return the first value of each."""
    script = "\n".join(f"\\echo @@{i}\n{d['sql']};" for i, d in enumerate(defs))
    res = subprocess.run(["docker", "exec", "-i", "postgres", "psql", "-U", "postgres", "-d", "cchist", "-A", "-t", "-q",
                          "-v", "ON_ERROR_STOP=1"], input=script, capture_output=True, text=True, encoding="utf-8")
    if res.returncode:
        sys.exit("psql failed: " + res.stderr[:2000])
    vals, cur = {}, None
    for line in res.stdout.splitlines():
        if line.startswith("@@"):
            cur = int(line[2:])
        elif line.strip() and cur is not None and cur not in vals:
            vals[cur] = line.strip()
    return [None if vals.get(i, "") == "" else float(vals[i]) for i in range(len(defs))]


if __name__ == "__main__":
    cands = p7_defs() + generate()
    seen_sql, seen_name, uniq = set(), set(), []
    for d in cands:
        key = re.sub(r"\s+", " ", d["sql"]).strip()
        if key in seen_sql or d["name"] in seen_name:
            continue
        seen_sql.add(key); seen_name.add(d["name"]); uniq.append(d)
    vals = truths(uniq)
    pool = []
    for d, v in zip(uniq, vals):
        if d["origin"] == "p7" or (v is not None and v > 0):
            d["truth"] = round(v, 4) if v is not None else None
            pool.append(d)
    for i, d in enumerate(pool):
        d["id"] = f"d{i:05d}"
    text = json.dumps(pool, indent=0, ensure_ascii=False)
    (HERE / "pool.json").write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    (HERE / "pool.sha256").write_text(sha + "  pool.json\n")
    fams = {}
    for d in pool:
        fams[d["family"]] = fams.get(d["family"], 0) + 1
    print(f"candidates {len(cands)}, unique {len(uniq)}, pool (truth > 0) {len(pool)}; by family {fams}; sha256 {sha}")
