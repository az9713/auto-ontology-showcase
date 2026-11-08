# HANDOFF — resume point for the auto-ontology showcase

**Read this first each new session.** Then open `auto-ontology-showcase-projects.html`: it is the
project document (plan, decisions, progress, results, log). There is no project `CLAUDE.md`;
`auto-ontology/CLAUDE.md` is NVIDIA's file for their maintainers, not for this project.

## Current state (verified 2026-11-07 21:10 UTC)

### Done before P7 (unchanged)
- **P2** done with reduced scope (P1, P5 inside it). Results: project document `#p2results`. Baseline 30/30; A and B 0/30;
  correction rounds R1 0/6, R2 3/6, R3 4/6. `sec-ontology-map.html` = picture of the SEC data and its ontology.

### P7 (runs DONE; project document updated: `#p7results`, Progress, 8 Decisions rows, Log, Status)
- Truth: DB `cchist` (5 tables, pattern ids only), `p7/truth.sql` -> 7 of 7 equal. Questions `p7/questions.json` (11 + 5).
- All runs done (`p7/run_all.log` ends `ALL_DONE`, 0 errors). Scores: `python -I p7/score.py` -> `p7/scores.json`. No overrides.
  | Store state | Repeats | Correct of 11 | Refused of 5 |
  |---|---|---|---|
  | a local 4B + raw DDL | 3 | 0,0,0 (refused all 16) | 5,5,5 |
  | b uncertified (b r1 only) | 1 | 0 | 2 |
  | certified store (b r2, b r3, c r1-r3) | 5 | 2 each (kill_by_pattern, kill_by_pattern_opus48) | 2 each |
  | d Claude + raw DDL | 3 | 1,1,3 | 5,5,5 |
  | e local 4B + raw DDL + definitions as prompt text, no tool (`run_ddl.py 3 --defs`) | 3 | 8,8,8 | 5,5,5 |
  | f Claude + raw DDL + definitions as prompt text (`p7/baseline_defs/run.sh`) | 3 | 11,11,11 | 5,5,5 |
- **Defect:** `run_all.sh` ran b r2-r3 after `certify.py`; b and c send the same request, so b r2-r3 are certified-store runs.
  `p7/score.py` `CERT_AT` scores them as `b_ran_in_certified_store`. Old term descriptions are not kept in the store, so the
  uncertified state cannot be restored exactly (a recompile = a new ontology, hours on the 4B model).
- Finding: 7 of 8 questions with a certified SQL attribute ended in "metadata reasoning step failed" (35 of 35 tries);
  the 3 with no attribute got SQL 15 of 15. The 4B model fails the information agent schema.
- Told the owner (in chat): the generated ontology shows no benefit; certified definitions gave a small one (kill-by-pattern only);
  no test yet shows the ontology beats the same definitions as prompt text.

### Live state
- `auto-ontology/.env` **restored** from `p7/env_hosted.bak` (hosted nemotron, CONNECTION_STRINGS = sec only); services
  auto-ontology + ingestion-service recreated, `/api/health/live` ok. P7 config saved as `p7/env_p7.bak` (secrets).
- Clone `auto-ontology/` on `main` at `c4495670`; ` M auto_ontology/utils/llm_invoke.py`: patches 1-3 (hosted NIM) + patch 4
  (acts only on a local URL; kept). Do not commit in the clone.
- My Ollama server (port 11435, PID 34364) **stopped** by PID. Request logs in `%TEMP%/ollama-request-logs-*` kept
  (prompt bodies: schema, questions, definitions; no transcript text); delete only if the owner agrees.
- P8 MCP server stopped 2026-11-08 (was PIDs 48812/61734); log `p8/mcp_server.log`. `p8/mcp_token.json`, `p8/mcp_auth.json` = secrets.
- User env vars set: `OLLAMA_CONTEXT_LENGTH=16384`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`.
- DB `cchist` and its certified terms/attributes stay in the store (DB `auto_ontology`). SEC store untouched.
- Git: workspace root = repo `az9713/auto-ontology-showcase` (public since 2026-11-08, branch main). `.gitignore` keeps out secrets, the clone,
  raw SEC data and the personal `cchist` rows. Names and user paths were replaced by "the owner" / `<user>` before the first commit.

## Next task
**P8 DONE 2026-11-08** (project document `#p8results`). Gate fired after L1: P, R, O each 40/40 and 5/5 refused at L0 (50 defs)
and L1 (200 defs), 3 repeats; O most expensive (USD 1.67-2.61 per run). L2/L3 not run -> the size question is open.
L3 (5,000 defs, ~1,014k tokens) does not fit Claude Code's 1M window. Runs USD 27.91.
State: MCP server **stopped** (PIDs 48812, 61734). Store `.env` = cchist only (`p8/env_p8.bak`; hosted = `p7/env_hosted.bak`
has sec only). Store holds the L1 attribute set (200 certified) + 19 decoy tables/terms in cchist. Ollama logs kept (the owner).
Open options for the owner: (1) follow-up outside the P8 gate: L2/L3 for R and O with harder questions; (2) restore `.env` to
sec (`p7/env_hosted.bak`) or keep cchist; (3) P3/P4/P6 todo.
Re-run arm O later: start MCP server (`cd auto-ontology/mcp; AUTO_ONTOLOGY_API_URL=http://localhost:3000 uv run auto-ontology-mcp`),
then `python -I p8/mcp_login.py --refresh` (or full sign-in if the refresh token expired).

## Where to read things
- `auto-ontology-showcase-projects.html` — status, plans, Results, Decisions, Log.
- `p7/` — all P7 files (list above). `p2/` — P2 files (`score.py`, `corrections.py` patterns reused in P7).
- `data/sec/load_sec.sql` — SEC load.

## Workflow provenance
- 2026-11-07 session 2 (after /clear): no skills; advisor 1 time (contamination check and reporting by store state).
- 2026-11-07 session 1: skills used — `handoff-after-clear` (twice, by the owner), none drove the work. Advisor consulted 1 time
  (loader design: keep counters + in-process check; noise as flags; no category names in DB). No subagents (arm d used
  3 `claude -p` processes, not subagents, to keep `~/.claude/CLAUDE.md` out of context; checked with a probe run).
  Hooks active: ponytail, coach. Claude Code killed 2 background watchers under memory pressure (2.5 GB free of 31.7 GB).
- Earlier sessions: see the project document Log. Skills then: `handoff-after-clear`, `asd-ste100` (style).
- Unknowns: cause of audit 583/77 against rerun 585/106; why a certified SQL attribute makes the 4B model fail
  the metadata step (fits the schema failure; not proven).

## Gotchas (new in P7)
- langchain-openai 1.3.4 sends `max_completion_tokens`; Ollama 0.40.15 ignores it -> unbounded output. Send `max_tokens`.
- Compile fan-out uses `SEMANTIC_LLM_MAX_INFLIGHT` (default 6), which overrides `LLM_MAX_INFLIGHT`.
- With >1 connector, API-created SqlAttributes get no `database_name` in `vdb.semantic_layer`.
- Older gotchas: hosted NIM 400/429/thinking (patches 1-3); 2-column FK overlap needs `tag_version_idx`; re-ingest = restart
  ingestion; recompile = `POST :3002/semantic/reset?database_name=X`; writes on :3001 need header
  `x-auto-ontology-user-id: 216bca1f-6796-4841-aebf-fc7846fe31f2`; CRLF breaks Docker build; prefix docker with `MSYS_NO_PATHCONV=1`
  in Git Bash; never print `.env` values (a redaction slip printed the local Postgres password once on 2026-11-07).

## How to work
- Keep every file in this workspace folder (the owner's rule); P7 files in `p7/`.
- Update the project document after each work session: status, progress row, Decisions row, Log row.
- the owner's writing rules: ASD-STE100, precise numbers, plain words.
- Stop the stack with `docker compose stop` in `auto-ontology/`. Data stays in the `postgres_data` volume.
