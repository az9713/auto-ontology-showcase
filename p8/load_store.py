"""P8 arm O: make the certified SQL attributes of the cchist store equal to one level's definition set.

  python -I load_store.py L1   # deletes cchist attributes not in L1, creates + certifies the missing ones; logs to load_log.jsonl

Each definition becomes 1 SQL attribute (name, description, SQL) under the term of its main table, then PATCH certified=true
(create does not take `certified`). The 4 certified P7 term descriptions are not changed.
"""
import json, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
API = "http://localhost:3001"
HDR = {"Content-Type": "application/json", "x-auto-ontology-user-id": "216bca1f-6796-4841-aebf-fc7846fe31f2"}
TERM = {  # table -> term id (store DB, 2026-11-08 after compile); base tables -> the certified P7 terms
    "human_message": "566b8f9f-4bc9-4cd6-a407-a037d86ae312", "message_pattern_hit": "52323668-78d9-46d0-80cb-7ba44a9b711b",
    "tool_call": "4c3fe7d2-e61a-455d-a7cb-947700a68d28", "tool_result": "a44387fa-da47-41fc-9497-cac4f615b04f",
    "call_danger_hit": "4c3fe7d2-e61a-455d-a7cb-947700a68d28",  # as in P7: kill-by-pattern under Tool Call
    "call_danger_hit_v1": "4a70b599-fc74-4cb5-ae7c-2b7cad8782dd", "human_message_2026q2": "9a0a6180-1e60-4b6e-b75a-8c1ee767b599",
    "human_message_2026q3": "0bd4e356-5750-439f-9af9-d9380783429f", "human_message_archive": "3e8f1587-2cf3-4992-ba99-b38216720191",
    "human_message_daily": "832e0d59-d70c-4dfd-bccc-2d302b8e9811", "stg_human_message": "bd25008b-ce42-476e-9603-ba9091446bb1",
    "stg_message_pattern_hit": "a9015b0d-011a-4b0b-933d-714915f72b04", "stg_tool_call": "6cfd7117-d534-484a-90cc-844c84552c89",
    "stg_tool_result": "eda583de-59a8-43e4-97e9-70a43f9f1edd", "tool_call_2026h1": "5c232369-63df-49a0-b7ab-20e51a3d252f",
    "tool_call_2026h2": "8b7ff02a-5043-43ae-a5b4-23622816dd88", "tool_call_archive": "039369d0-c192-4d99-b470-e57fa694c7f0",
    "tool_call_daily": "333aef49-de1f-4995-9c38-c93bf430427b", "tool_call_fable": "b721aa18-2d9b-4b80-a778-12f7539436eb",
    "tool_call_opus": "46847e4b-f182-4131-8af1-cc681a7be704", "tool_call_sonnet": "a0d192af-e1be-4316-aea2-eb9cb65ad4c2",
    "tool_result_2026h1": "e7eb8e1e-f3f9-41d2-88c0-0a77cd7072b7", "tool_result_2026h2": "c741481b-6d0d-44bd-b143-ed46070556e8",
    "tool_result_archive": "54a7fda4-a7e6-49a9-a060-a4553aeb7fc4"}
LOG = HERE / "load_log.jsonl"


def call(method, path, body=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, HDR, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                status, text = r.status, r.read().decode()
            break
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode()
            if status < 500:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            status, text = 0, str(e)
        time.sleep(3 * (attempt + 1))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "method": method, "path": path,
                            "name": (body or {}).get("name"), "status": status, "response": text[:200] if status >= 300 else ""}) + "\n")
    return status, text


def one(d):
    s, t = call("POST", "/api/sql-attributes", {"name": d["name"], "description": d["description"], "expression": d["sql"],
                                                 "term_id": TERM[d["table"]]})
    if s >= 300:
        return f"create {d['id']} {d['name']!r}: {s} {t[:200]}"
    aid = json.loads(t)["data"]["id"]
    s, t = call("PATCH", f"/api/sql-attributes/{aid}", {"certified": True})
    return None if s < 300 else f"certify {d['id']}: {s} {t[:200]}"


if __name__ == "__main__":
    level = sys.argv[1]
    pool = {d["id"]: d for d in json.loads((HERE / "pool.json").read_text(encoding="utf-8"))}
    want = {pool[i]["name"]: pool[i] for i in json.loads((HERE / "levels.json").read_text(encoding="utf-8"))[level]}
    terms = set(TERM.values())
    t0 = time.time()
    s, t = call("GET", "/api/sql-attributes")
    have = [a for a in json.loads(t)["data"] if a["term_id"] in terms]
    stale = [a for a in have if a["name"] not in want or not a.get("certified")]
    keep = {a["name"] for a in have} - {a["name"] for a in stale}
    with ThreadPoolExecutor(4) as ex:
        errs = [e for e in ex.map(lambda a: None if call("DELETE", f"/api/sql-attributes/{a['id']}")[0] < 300
                                  else f"delete {a['name']}", stale) if e]
        t1 = time.time()
        todo = [d for n, d in want.items() if n not in keep]
        errs += [e for e in ex.map(one, todo) if e]
    s, t = call("GET", "/api/sql-attributes")
    now = [a for a in json.loads(t)["data"] if a["term_id"] in terms]
    ok = sorted(a["name"] for a in now if a.get("certified")) == sorted(want)
    print(f"{level}: deleted {len(stale)} in {t1 - t0:.0f} s, created+certified {len(todo)} in {time.time() - t1:.0f} s; "
          f"store now {len(now)} cchist attributes, {sum(bool(a.get('certified')) for a in now)} certified, "
          f"database_name {sorted({str(a.get('database_name')) for a in now})}; equals level set: {ok}; errors {len(errs)}")
    for e in errs[:20]:
        print(" ", e)
    sys.exit(0 if ok and not errs else 1)
