# Testing NVIDIA auto-ontology on real data

This repository holds 3 experiments with [NVIDIA auto-ontology](https://github.com/NVIDIA/auto-ontology) (clone at commit
`c4495670`). Auto-ontology compiles a semantic layer (an "ontology": terms, links, certified SQL definitions) over a
database. An agent then uses that layer to answer questions in plain English with SQL.

The question in every experiment: **does the ontology make an agent's answers more correct?**

**Short answer: no measured benefit from the ontology.** The benefit came from the *definitions* that a person wrote and
certified. The same definitions given as plain text in the prompt, or found by a plain embedding search, did as well as or
better than the ontology tool, at a lower cost. The full reasons are in [Why the ontology gave no benefit](#why-the-ontology-gave-no-benefit).

The project document with every plan, decision, progress row and log entry is
[`auto-ontology-showcase-projects.html`](https://az9713.github.io/auto-ontology-showcase/auto-ontology-showcase-projects.html). A picture of the SEC data and its ontology
is [`sec-ontology-map.html`](https://az9713.github.io/auto-ontology-showcase/sec-ontology-map.html). Both open as web pages on GitHub Pages.

## Contents

- [Set-up](#set-up)
- [P2: "What is revenue?" in SEC data](#p2-what-is-revenue-in-sec-data)
- [P7: definitions the model cannot know](#p7-definitions-the-model-cannot-know)
- [P8: scale test, ontology against plain search against the prompt](#p8-scale-test-ontology-against-plain-search-against-the-prompt)
- [Why the ontology gave no benefit](#why-the-ontology-gave-no-benefit)
- [What these tests do not show](#what-these-tests-do-not-show)
- [Repository layout](#repository-layout)
- [How to run it again](#how-to-run-it-again)

## Set-up

| Item | Value |
|---|---|
| Machine | Windows 11, Docker Desktop (Docker 29.6.2, Compose v5.3.1), Git Bash |
| auto-ontology | Docker Compose stack: frontend :3000, API :3001, ingestion :3002, MCP server :3003, Postgres store |
| Tool model (P2, P8 compile) | hosted `nvidia/nemotron-3.5-lightning-30b-a3b` on `integrate.api.nvidia.com` |
| Tool model (P7) | local `qwen3:4b-instruct-2507-q4_K_M` on Ollama 0.40.15 (RTX 3050 Laptop, 4,096 MiB) |
| Embedding model | hosted `nvidia/nemotron-3-embed-1b` (2,048 dimensions). `nemotron-3.5-embed-1b` returned HTTP 500 on 7 of 12 test calls. |
| Baseline and agent model | Claude Opus 5.5 (`claude-opus-5-5`) through `claude -p` |

The tool did not run against its default hosted model without changes. 4 client patches are in
[`patches/llm_invoke.diff`](patches/llm_invoke.diff) (file `auto_ontology/utils/llm_invoke.py` of the clone):

1. Send calls to `integrate.api.nvidia.com` through `ChatOpenAI`. The hosted model rejects `guided_json` with HTTP 400, so
   every structured call failed in chat and in compilation.
2. Turn thinking off on that endpoint. Thinking used up the 1,024 and 4,096 output-token limits of the term extractor.
3. `max_retries=8` on the hosted endpoint. HTTP 429 (rate limit) made 121 of 135 answers fail in the first P2 condition B run.
4. Send a local base URL (Ollama) through `ChatOpenAI` (P7).

## P2: "What is revenue?" in SEC data

**Goal.** Test the main claim of auto-ontology on real public data: a correct revenue number.

**Data.** SEC Financial Statement Data Sets, 2026 Q1: 4 tables `sub` (6,169 filings), `num` (3,690,955 numbers),
`tag` (91,794 tags), `pre` (733,134 presentation lines). Column names are cryptic. One company can report revenue under
several tags, and a wrong tag gives a wrong number with no error.

**Truth.** 30 numbers (revenue, net income, total assets for 10 companies: Alphabet, Amazon, Berkshire Hathaway,
Caterpillar, Coca-Cola, Exxon Mobil, JPMorgan Chase, Pfizer, Tesla, Walmart), read by hand from each 10-K on www.sec.gov
before any run. Tolerance 0.1%. Plus 15 questions the data cannot answer (stock price, CEO, credit rating, and others).

**Arms.**
- Baseline: Claude with the raw table definitions (DDL) only.
- Auto-ontology A: ontology compiled from the raw tables (4 terms, 0 links).
- Auto-ontology B: the same tables with declared keys (4 terms, 6 links).
- Correction rounds on a 6-question subset: R1 certified descriptions, R2 certified SQL attributes, R3 verified SQL examples.

**Results.**

| Agent | Repeats | Correct of 30 | Wrong number | No number | Unanswerable refused of 15 | Invented |
|---|---|---|---|---|---|---|
| Baseline (Claude, raw DDL) | 3 | 30, 30, 30 | 0 | 0 | 15, 15, 15 | 0 |
| Auto-ontology A | 1 | 0 | 4 | 26 | 2 | 1 |
| Auto-ontology B | 1 | 0 | 3 | 27 | 5 | 0 |

| 6-question subset | A | B | R1 descriptions | R2 SQL attributes | R3 verified SQL |
|---|---|---|---|---|---|
| Correct, corrected set (3) | 0 | 0 | 0 | 2 | 2 |
| Correct, holdout set (3) | 0 | 0 | 0 | 1 | 2 |

- The generated ontology gave 0 of 30. Most failures returned no number ("the metadata reasoning step failed", or an
  empty result). Median latency 130.6 s, maximum 1,128.9 s per question.
- Declared keys fixed the graph (0 to 6 correct links) and raised refusals from 2 to 5 of 15, but made no number correct.
- Certified SQL definitions were the lever that worked: 3 definitions took the subset from 0 of 6 to 3 of 6 (R2).
  Descriptions alone (R1) did not.
- Defects found: a 2-column foreign key is stored as 4 column pairs, 2 of them wrong (`connectors/postgres.py:272-291`);
  the FK overlap check ran more than 19 min on 3.7 million rows until an index on `tag(version)` was added.
- Limit: the baseline model (Claude Opus 5.5) is much stronger than the tool's model, so P2 compares 2 systems, not the
  ontology alone. 1 repeat per tool measurement (rate limit).

## P7: definitions the model cannot know

**Goal.** Remove the model difference of P2, and test questions whose meaning is private: no model can know the rule
from the schema.

**Data.** Database `cchist`, built from the owner's own Claude Code session logs: 5 tables of atomic facts
(`human_message` 10,569 rows, `tool_call` 64,461, `tool_result` 67,967, `message_pattern_hit` 1,660, `call_danger_hit`
413). No message text and no command text, only flags and counts. The raw rows are **not** in this repository (personal
activity data); the schema is in [`p7/cchist_schema.sql`](p7/cchist_schema.sql).

**Questions.** 11 answerable questions with private rules (for example "a typed user message" = not sidechain, not
noise, more than 0 characters; "a failed call" = error, not denied, not a validation error; "kill-by-pattern" = danger
pattern 1 or 2), and 5 unanswerable ones. Truth from SQL that reproduces an earlier audit.

**Results.**

| Arm | Repeats | Correct of 11 | Refused of 5 |
|---|---|---|---|
| a: local 4B + raw DDL | 3 | 0, 0, 0 (it refused all 16) | 5, 5, 5 |
| b: local 4B + generated ontology, uncertified | 1 | 0 | 2 |
| b r2–r3 + c: local 4B + certified ontology store | 5 | 2 each | 2 each |
| d: Claude + raw DDL | 3 | 1, 1, 3 | 5, 5, 5 |
| **e: local 4B + raw DDL + the same definitions as prompt text, no tool** | 3 | **8, 8, 8** | 5, 5, 5 |
| **f: Claude + raw DDL + the same definitions as prompt text** | 3 | **11, 11, 11** | 5, 5, 5 |

- The generated ontology gave 0 of 11: the generator sees only the schema, and the meaning is not in the schema. Two
  answers used filters made up from the question words (`tool_name = 'kill-by-pattern'`).
- The certified ontology gave 2 of 11. 7 of the 8 questions with a certified SQL definition ended in "The metadata
  reasoning step failed" in 35 of 35 tries: the 4B model fails the tool agent's output schema.
- **The same definitions as prompt text gave 8 of 11 on the same 4B model, and 11 of 11 with Claude.** So the benefit is
  in the definitions, not in the ontology.
- Run-order defect: arm b repeats 2 and 3 ran after certification; they are scored as certified-store runs.

## P8: scale test, ontology against plain search against the prompt

**Goal.** P7 left one claim open: when there are too many definitions for one prompt, does the ontology find the right
one better than a plain search? P8 tests retrieval only.

**Data.** `cchist` plus 19 decoy tables with real rows ([`p8/decoys.sql`](p8/decoys.sql)): staging copies with duplicate
rows, half-year and quarter splits, per-model splits, archive copies with 1 column changed, an older danger taxonomy,
2 daily rollups. A template generator ([`p8/gen_defs.py`](p8/gen_defs.py)) made 9,332 unique definitions; 5,380 with a
value above 0 form the frozen pool ([`p8/pool.json`](p8/pool.json), sha256 `af474a75…`). The definitions are near-variants
of each other ("Failed Read Calls (Main Agent, Staging)"), as in a real semantic layer.

**Questions.** 45, written after the pool was frozen ([`p8/questions.json`](p8/questions.json), sha256 `35885cb5…`):
15 copy, 10 compose, 15 near-variant (a more common definition is close, the "trap"), 5 unanswerable.

**Levels.** L0 50 definitions (the targets, traps and inputs), L1 200, L2 1,000, L3 5,000; each level holds the level below.

**Arms** (same model, Claude Opus 5.5, 3 repeats; each run = 3 `claude -p` processes of 15 questions, Bash allowed only for
`psql`):
- **P (prompt):** raw DDL + all definitions of the level in the prompt.
- **R (plain search):** raw DDL + 1 command that returns the top 10 definitions by embedding search, same embedding model
  as auto-ontology ([`p8/search.py`](p8/search.py)).
- **O (ontology):** raw DDL + the auto-ontology MCP server, read tools only (`search_terms`, `get_term`,
  `get_term_sql_attributes`, `get_sql_attribute`, `describe_table`, `check_answerable`), with every definition of the level
  certified in the store. `ask_question` (the tool's own agent) was blocked.

**Pass rule, written before any run.** O shows a benefit at a level only if O ≥ R + 4 and O ≥ P + 4 (of 40). Gate: if
O ≤ R at L0 and at L1, stop and report.

**Results.**

| Level | Arm | Correct of 40 (3 repeats) | Refused of 5 | Trap answers | USD per run |
|---|---|---|---|---|---|
| L0 (50) | P prompt | 40, 40, 40 | 5, 5, 5 | 0 | 0.87–0.90 |
| L0 (50) | R search | 40, 40, 40 | 5, 5, 5 | 0 | 0.98–1.22 |
| L0 (50) | O ontology | 40, 40, 40 | 5, 5, 5 | 0 | 1.67–1.89 |
| L1 (200) | P prompt | 40, 40, 40 | 5, 5, 5 | 0 | 1.70–1.72 |
| L1 (200) | R search | 40, 40, 40 | 5, 5, 5 | 0 | 1.11–1.62 |
| L1 (200) | O ontology | 40, 40, 40 | 5, 5, 5 | 0 | 2.26–2.61 |

- Every arm got every question right at both levels, so the questions did not separate the arms. The gate fired by its
  rule, and L2 and L3 were not run. The stop is by rule on a perfect score, not evidence that the ontology gives no
  benefit at a larger size.
- The agents used the definitions: on the 90 copy and near-variant answers per arm and level, the answer SQL equals the
  certified SQL in O 79 (L0) and 88 (L1), P 51 and 80, R 26 and 43. The other answers were SQL written by the agent that
  gave the same number ([`p8/copy_check.py`](p8/copy_check.py)).
- Window probe: L2 is about 200,000 tokens and fits. **L3 does not fit**: Claude Code refused it ("Prompt is too long —
  the request is ~1013992 tokens (limit 1000000)"). The definitions use about 2.1 characters per token.
- Store load: 0.17 s per certified definition (150 in 26 s). Compile of 19 tables: 1 min 41 s.
- Cost: USD 27.91 for 18 scored runs (54 processes).

## Why the ontology gave no benefit

These are the mechanisms the 3 experiments measured. Each one has its numbers above.

1. **The meaning is not in the schema, so a generated ontology cannot contain it.** The compiler reads table and column
   names and sample values. The rules that decide a correct answer (which revenue tag has priority; what "a failed call"
   or "a question" means) are written nowhere in the database. Result: 0 of 30 (P2 A and B) and 0 of 11 (P7 b). Declared
   keys fixed the links but not one number.
2. **The value is in the certified definitions, and plain text carries them as well.** Every gain came after a person
   wrote and certified definitions (P2 R2: 0 to 3 of 6). The same definitions as prompt text gave 8 of 11 against 2 of 11
   through the tool on the same 4B model (P7 e against c), 11 of 11 with Claude (P7 f), and 40 of 40 in every P8 arm.
   The ontology is a container for the definitions; it did not add correctness on top of them.
3. **The tool's own agent was the weakest part.** With the default or a small model, the multi-step agent failed its own
   output schema ("The metadata reasoning step failed": 35 of 35 tries on certified questions in P7), needed 3 client
   patches to run on the hosted model, hit rate limits, and took a median of 130.6 s per question. A strong model with the
   raw DDL wrote correct SQL itself (P2 baseline 30 of 30).
4. **A strong model does not need the graph to find joins.** The links that the ontology adds (foreign keys, joins) are
   visible in the DDL, and the P2 baseline (Claude, raw DDL only) joined the 4 SEC tables correctly in 30 of 30 answers.
   On schemas of 4 to 24 tables, the ontology's structure had nothing to add.
5. **Retrieval only matters past the prompt size, and there plain search is the competitor.** At 200 definitions the
   prompt still works (P8 P: 40 of 40), and a 1,000,000-token window holds about 1,000 such definitions. The ontology's
   read tools find a definition by an embedding search (`check_answerable`, over the same kind of text) or by listing a
   term's attributes; `search_terms` only matches term names by substring (`dal/terms.py:152`). That is the same
   mechanism as plain search, and no advantage was seen at 50 and 200.
6. **It cost more.** Arm O was the most expensive arm at both P8 levels: USD 1.67–2.61 per run against 0.98–1.62 (R) and
   0.87–1.72 (P), with 0.81–1.97 million input tokens per run against 0.45–0.64 (R).

## What these tests do not show

- **Scale past the window is untested.** The P8 gate stopped before L2 (1,000) and L3 (5,000, which does not fit a
  prompt). A follow-up would run R and O at L2 and L3 with harder questions.
- **Governance is untested.** Access control, provenance, review workflow, and many teams sharing one set of definitions
  are features of auto-ontology that these tests did not measure.
- **One person wrote the questions, truths and decoys.** P8 froze the decoy templates before the questions (sha256 above),
  but template decoys are more regular than a real semantic layer.
- **Model confound.** P2 compares Claude against the tool's hosted model. P7 used a 4B model that fails the tool's schema
  on most questions. P8 used one model for all arms, but the base-table terms were compiled by the 4B model and the
  decoy-table terms by the hosted model.
- **Repeats.** P2 and P7 tool arms have 1 repeat in some cells (rate limits, a run-order defect).

## Repository layout

| Path | Content |
|---|---|
| `auto-ontology-showcase-projects.html` | Project document: plans P1–P8, status, results, decisions, log |
| `sec-ontology-map.html` | Picture of the SEC data and its ontology |
| `HANDOFF.md` | Resume notes between work sessions |
| `patches/llm_invoke.diff` | The 4 client patches to auto-ontology |
| `data/sec/load_sec.sql` | Load script for the SEC data set (download the zip from sec.gov) |
| `p2/` | P2: truth, questions, runners, answers, scores, correction rounds |
| `p7/` | P7: schema, truth SQL, questions, runners, answers, scores (no raw personal rows) |
| `p8/` | P8: decoys, definition pool, questions, levels, runners, MCP sign-in, search, answers (`runs/`), scores |

Not included: the auto-ontology clone, `.env` files and tokens, the raw SEC download (85 MB zip), the `cchist` rows,
the arm R embedding index (`python -I p8/search.py --build` rebuilds it).

## How to run it again

1. Clone auto-ontology at `c4495670`, apply `patches/llm_invoke.diff`, write `.env` from `.env.example` with your NVIDIA
   API key, and start the stack with `docker compose up -d`.
2. P2: download `2026q1.zip` from the SEC Financial Statement Data Sets page, load it with `data/sec/load_sec.sql`, set
   `CONNECTION_STRINGS` to the `sec` database, compile, then run `p2/run_ao.py` and score with `p2/score.py`.
3. P7 and P8 need the `cchist` rows, which come from a person's own Claude Code logs and are not published. With your own
   logs, `p7/load_cchist.py` builds them. P8 then runs: `p8/decoys.sql`, `p8/gen_defs.py`, `p8/freeze.py`,
   `p8/search.py --build`, `p8/load_store.py L0`, `sh p8/run_level.sh L0`, `p8/score.py`.
4. Arm O needs the MCP server and a sign-in: `p8/mcp_login.py` (1 browser sign-in, then `--refresh` with no browser).

Contact: az9713@yahoo.com
