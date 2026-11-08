"""P7 arm c: certify the audit definitions in auto-ontology (term descriptions + SQL attributes from truth.sql).

Usage: python -I certify.py
No custom analysis carries a question text. Each call is logged to certify_log.jsonl.
3 of the 11 answerable questions have no SQL attribute of their own (2 rates, kill-by-pattern for one model).
"""
import json, time, urllib.request
from pathlib import Path

HERE = Path(__file__).parent
API = "http://localhost:3001"
HDR = {"Content-Type": "application/json", "x-auto-ontology-user-id": "216bca1f-6796-4841-aebf-fc7846fe31f2"}
LOG = HERE / "certify_log.jsonl"
MESSAGE, PATTERN, CALL, RESULT = ("566b8f9f-4bc9-4cd6-a407-a037d86ae312", "52323668-78d9-46d0-80cb-7ba44a9b711b",
                                  "4c3fe7d2-e61a-455d-a7cb-947700a68d28", "a44387fa-da47-41fc-9497-cac4f615b04f")
T = "cchist.public."
TYPED = "NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0"


def call(method, path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, HDR, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            status, text = r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode()[:300]
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "method": method, "path": path, "body": body,
                            "status": status, "response": text}) + "\n")
    print(status, method, path, text[:120] if status >= 300 else "")
    return status


TERMS = {
    MESSAGE: ("User Message",
              "One record of text sent to an agent (table human_message). A typed user message = is_sidechain false AND "
              "is_noise false AND chars > 0; rows with is_sidechain true (subagent prompts) or is_noise true (system and "
              "command text) are not user messages. A question = a typed user message with chars < 400 AND (ends_with_q OR "
              "question_start) AND NOT imperative. A question is followed by an edit when a tool_call in the same file_id, "
              "with line_no after the question and before the next typed user message of that file, has tool_name in "
              "('Edit','Write','NotebookEdit','MultiEdit') and is_sidechain false; count each question once."),
    PATTERN: ("Correction Pattern Hit",
              "One correction-pattern match on a message (table message_pattern_hit). pattern_id: 1-2 blunt no, 3-5 misread, "
              "6-8 unsolicited edit, 9-11 over-building, 12-15 stopped early, 16-17 no verification, 18-19 regression, "
              "20-21 tool misuse. A correction message = a typed user message with at least 1 hit (count distinct msg_id). "
              "The number of corrections of one category counts hits (rows), not messages."),
    CALL: ("Tool Call",
           "One tool call by an agent (table tool_call), sidechain calls included; model is the agent model "
           "(for example claude-opus-4-8 = Opus 4.8). Read calls = rows with tool_name = 'Read'. Risky shell commands are "
           "rows of call_danger_hit; its pattern_id: 1-2 kill by pattern (pkill, taskkill), 3-4 kill by PID, 5-6 rm -rf, "
           "7 git reset --hard, 8 git push --force, 9 git clean, 10 git checkout --. Kill-by-pattern commands = hits with "
           "pattern_id 1 or 2 (count hits), attributed to tool_call.model."),
    RESULT: ("Tool Result",
             "One tool result (table tool_result). A failed call = is_error true AND denied_mark false AND validation_mark "
             "false (denied and validation errors are not failures). Failed Read calls = tool_result joined to tool_call on "
             "call_id with tool_name = 'Read' and the failure condition."),
}

ATTRS = [
    (MESSAGE, "Typed User Messages", "Count of typed user messages.",
     f"SELECT count(*) AS typed_user_messages FROM {T}human_message h WHERE {TYPED}"),
    (MESSAGE, "User Questions", "Count of questions the user asked.",
     f"SELECT count(*) AS questions FROM {T}human_message h WHERE {TYPED} AND h.chars < 400 "
     "AND (h.ends_with_q OR h.question_start) AND NOT h.imperative"),
    (MESSAGE, "Questions Followed By An Edit", "Count of user questions followed by an edit before the next typed user message.",
     f"WITH c AS (SELECT h.file_id, h.line_no, h.chars < 400 AND (h.ends_with_q OR h.question_start) AND NOT h.imperative AS is_q, "
     f"lead(h.line_no) OVER (PARTITION BY h.file_id ORDER BY h.line_no) AS next_line FROM {T}human_message h WHERE {TYPED}) "
     f"SELECT count(*) AS questions_followed_by_edit FROM c WHERE c.is_q AND EXISTS (SELECT 1 FROM {T}tool_call t "
     "WHERE t.file_id = c.file_id AND t.line_no > c.line_no AND (c.next_line IS NULL OR t.line_no < c.next_line) "
     "AND t.tool_name IN ('Edit', 'Write', 'NotebookEdit', 'MultiEdit') AND NOT t.is_sidechain)"),
    (PATTERN, "Correction Messages", "Count of typed user messages with at least 1 correction.",
     f"SELECT count(DISTINCT h.msg_id) AS correction_messages FROM {T}human_message h JOIN {T}message_pattern_hit p "
     f"ON p.msg_id = h.msg_id WHERE {TYPED}"),
    (PATTERN, "Stopped Early Corrections", "Count of 'stopped early' corrections (hits of pattern_id 12-15).",
     f"SELECT count(*) AS stopped_early_corrections FROM {T}human_message h JOIN {T}message_pattern_hit p "
     f"ON p.msg_id = h.msg_id WHERE {TYPED} AND p.pattern_id BETWEEN 12 AND 15"),
    (PATTERN, "Over-Building Corrections", "Count of 'over-building' corrections (hits of pattern_id 9-11).",
     f"SELECT count(*) AS overbuilding_corrections FROM {T}human_message h JOIN {T}message_pattern_hit p "
     f"ON p.msg_id = h.msg_id WHERE {TYPED} AND p.pattern_id BETWEEN 9 AND 11"),
    (CALL, "Read Calls", "Count of all Read tool calls.",
     f"SELECT count(*) AS read_calls FROM {T}tool_call c WHERE c.tool_name = 'Read'"),
    (CALL, "Kill-By-Pattern Commands", "Count of kill-by-pattern commands (danger pattern_id 1-2 hits), all models.",
     f"SELECT count(*) AS kill_by_pattern_commands FROM {T}call_danger_hit d JOIN {T}tool_call c ON c.call_id = d.call_id "
     "WHERE d.pattern_id IN (1, 2)"),
    (RESULT, "Failed Read Calls", "Count of failed Read calls.",
     f"SELECT count(*) AS failed_read_calls FROM {T}tool_result r JOIN {T}tool_call c ON c.call_id = r.call_id "
     "WHERE c.tool_name = 'Read' AND r.is_error AND NOT r.denied_mark AND NOT r.validation_mark"),
]

def certify_attrs():
    """PATCH certified=true on the SQL attributes above (as P2 R2 did after create)."""
    req = urllib.request.Request(API + "/api/sql-attributes", headers=HDR)
    names = {a[1] for a in ATTRS}
    for a in json.load(urllib.request.urlopen(req, timeout=60))["data"]:
        if a["name"] in names and not a.get("certified"):
            call("PATCH", f"/api/sql-attributes/{a['id']}", {"certified": True})


if __name__ == "__main__" and "--certify-attrs" in __import__("sys").argv:
    certify_attrs()
elif __name__ == "__main__":
    for tid, (name, desc) in TERMS.items():
        call("PATCH", f"/api/terms/{tid}", {"name": name, "description": desc, "name_certified": True,
                                            "description_certified": True})
    for tid, name, desc, sql in ATTRS:
        call("POST", "/api/sql-attributes", {"name": name, "description": desc, "expression": sql, "term_id": tid})
    certify_attrs()
