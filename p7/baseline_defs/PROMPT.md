# Baseline agent prompt (P7 arm f: arm d prompt + the certify.py definitions) — the same text is sent to each of the 3 runs

You are the BASELINE agent in a benchmark. Answer questions about a log of a user's sessions with AI coding
agents by writing SQL against a Postgres database. You get only the raw schema below. Nothing else.

Rules:
1. Use only the Bash tool, and only to run SQL with this command form:
   MSYS_NO_PATHCONV=1 docker exec postgres psql -U postgres -d cchist -c "<SQL>"
   (Use -A -F '|' for compact output if you want.)
2. Do NOT read, list, grep or open any file on disk, and do not use any tool other than Bash for
   psql and Write for the one output file. Do not use web search. Every number must come from a query result.
3. If the data cannot answer a question, say so (refused = true). Do not guess.
4. Answer each question on its own terms. Give a single number where a number is asked
   (a percentage as a number of percent, for example 12.5).

Schema (database cchist, schema public):
CREATE TABLE human_message (
  msg_id         integer PRIMARY KEY,
  file_id        integer NOT NULL,
  line_no        integer NOT NULL,
  ts             timestamptz,
  model          text NOT NULL,
  is_sidechain   boolean NOT NULL,
  is_noise       boolean NOT NULL,
  chars          integer NOT NULL,
  ends_with_q    boolean NOT NULL,
  question_start boolean NOT NULL,
  imperative     boolean NOT NULL
);
CREATE TABLE message_pattern_hit (
  msg_id     integer NOT NULL REFERENCES human_message(msg_id),
  pattern_id smallint NOT NULL,
  PRIMARY KEY (msg_id, pattern_id)
);
CREATE TABLE tool_call (
  call_id      integer PRIMARY KEY,
  file_id      integer NOT NULL,
  line_no      integer NOT NULL,
  ts           timestamptz,
  model        text NOT NULL,
  tool_name    text NOT NULL,
  is_sidechain boolean NOT NULL,
  is_shell     boolean NOT NULL
);
CREATE TABLE call_danger_hit (
  call_id    integer NOT NULL REFERENCES tool_call(call_id),
  pattern_id smallint NOT NULL,
  PRIMARY KEY (call_id, pattern_id)
);
CREATE TABLE tool_result (
  result_id       integer PRIMARY KEY,
  file_id         integer NOT NULL,
  line_no         integer NOT NULL,
  ts              timestamptz,
  model           text NOT NULL,
  call_id         integer REFERENCES tool_call(call_id),
  is_error        boolean NOT NULL,
  denied_mark     boolean NOT NULL,
  validation_mark boolean NOT NULL,
  fastpath        boolean NOT NULL
);

Definitions (certified by the data owner):
- User Message: One record of text sent to an agent (table human_message). A typed user message = is_sidechain false AND is_noise false AND chars > 0; rows with is_sidechain true (subagent prompts) or is_noise true (system and command text) are not user messages. A question = a typed user message with chars < 400 AND (ends_with_q OR question_start) AND NOT imperative. A question is followed by an edit when a tool_call in the same file_id, with line_no after the question and before the next typed user message of that file, has tool_name in ('Edit','Write','NotebookEdit','MultiEdit') and is_sidechain false; count each question once.
- Correction Pattern Hit: One correction-pattern match on a message (table message_pattern_hit). pattern_id: 1-2 blunt no, 3-5 misread, 6-8 unsolicited edit, 9-11 over-building, 12-15 stopped early, 16-17 no verification, 18-19 regression, 20-21 tool misuse. A correction message = a typed user message with at least 1 hit (count distinct msg_id). The number of corrections of one category counts hits (rows), not messages.
- Tool Call: One tool call by an agent (table tool_call), sidechain calls included; model is the agent model (for example claude-opus-4-8 = Opus 4.8). Read calls = rows with tool_name = 'Read'. Risky shell commands are rows of call_danger_hit; its pattern_id: 1-2 kill by pattern (pkill, taskkill), 3-4 kill by PID, 5-6 rm -rf, 7 git reset --hard, 8 git push --force, 9 git clean, 10 git checkout --. Kill-by-pattern commands = hits with pattern_id 1 or 2 (count hits), attributed to tool_call.model.
- Tool Result: One tool result (table tool_result). A failed call = is_error true AND denied_mark false AND validation_mark false (denied and validation errors are not failures). Failed Read calls = tool_result joined to tool_call on call_id with tool_name = 'Read' and the failure condition.

Certified SQL:
- Typed User Messages: Count of typed user messages.
  SELECT count(*) AS typed_user_messages FROM cchist.public.human_message h WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0
- User Questions: Count of questions the user asked.
  SELECT count(*) AS questions FROM cchist.public.human_message h WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0 AND h.chars < 400 AND (h.ends_with_q OR h.question_start) AND NOT h.imperative
- Questions Followed By An Edit: Count of user questions followed by an edit before the next typed user message.
  WITH c AS (SELECT h.file_id, h.line_no, h.chars < 400 AND (h.ends_with_q OR h.question_start) AND NOT h.imperative AS is_q, lead(h.line_no) OVER (PARTITION BY h.file_id ORDER BY h.line_no) AS next_line FROM cchist.public.human_message h WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0) SELECT count(*) AS questions_followed_by_edit FROM c WHERE c.is_q AND EXISTS (SELECT 1 FROM cchist.public.tool_call t WHERE t.file_id = c.file_id AND t.line_no > c.line_no AND (c.next_line IS NULL OR t.line_no < c.next_line) AND t.tool_name IN ('Edit', 'Write', 'NotebookEdit', 'MultiEdit') AND NOT t.is_sidechain)
- Correction Messages: Count of typed user messages with at least 1 correction.
  SELECT count(DISTINCT h.msg_id) AS correction_messages FROM cchist.public.human_message h JOIN cchist.public.message_pattern_hit p ON p.msg_id = h.msg_id WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0
- Stopped Early Corrections: Count of 'stopped early' corrections (hits of pattern_id 12-15).
  SELECT count(*) AS stopped_early_corrections FROM cchist.public.human_message h JOIN cchist.public.message_pattern_hit p ON p.msg_id = h.msg_id WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0 AND p.pattern_id BETWEEN 12 AND 15
- Over-Building Corrections: Count of 'over-building' corrections (hits of pattern_id 9-11).
  SELECT count(*) AS overbuilding_corrections FROM cchist.public.human_message h JOIN cchist.public.message_pattern_hit p ON p.msg_id = h.msg_id WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0 AND p.pattern_id BETWEEN 9 AND 11
- Read Calls: Count of all Read tool calls.
  SELECT count(*) AS read_calls FROM cchist.public.tool_call c WHERE c.tool_name = 'Read'
- Kill-By-Pattern Commands: Count of kill-by-pattern commands (danger pattern_id 1-2 hits), all models.
  SELECT count(*) AS kill_by_pattern_commands FROM cchist.public.call_danger_hit d JOIN cchist.public.tool_call c ON c.call_id = d.call_id WHERE d.pattern_id IN (1, 2)
- Failed Read Calls: Count of failed Read calls.
  SELECT count(*) AS failed_read_calls FROM cchist.public.tool_result r JOIN cchist.public.tool_call c ON c.call_id = r.call_id WHERE c.tool_name = 'Read' AND r.is_error AND NOT r.denied_mark AND NOT r.validation_mark

Questions:
- human_msgs: How many messages did the user type to the agents?
- correction_msgs: How many of the user's messages contained at least one correction?
- correction_rate: What percentage of the user's messages contained at least one correction?
- stopped_early: How many 'stopped early' corrections did the user make?
- overbuild: How many 'over-building' corrections did the user make?
- read_failures: How many Read calls failed?
- read_failure_rate: What percentage of Read calls failed?
- questions: How many questions did the user ask?
- question_violations: How many of the user's questions were followed by an edit?
- kill_by_pattern: How many kill-by-pattern commands did the agents run?
- kill_by_pattern_opus48: How many kill-by-pattern commands did Opus 4.8 run?
- tokens: How many tokens did the agents use in total?
- top_project: Which project had the most corrections?
- git_commits: How many git commits did the agents make?
- common_word: What word appears most often in the user's corrections?
- cost: How much did the sessions cost in US dollars?

Output: write one JSON Lines file at the path given below, one line per question:
{"qid": "...", "refused": true|false, "value": <number or null>, "answer": "<one sentence>", "sql": "<the final SQL you used, or null>"}
Then reply with only the word DONE.
