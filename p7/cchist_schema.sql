-- P7: database cchist. Rows from p7/load_cchist.py (CSV in p7/cchist_csv/). Atomic facts only.
-- Load: see the \copy lines at the end (run inside the postgres container, files copied to /tmp/cchist_csv).
DROP TABLE IF EXISTS message_pattern_hit, call_danger_hit, tool_result, tool_call, human_message;

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

\copy human_message FROM '/tmp/cchist_csv/human_message.csv' CSV HEADER
\copy message_pattern_hit FROM '/tmp/cchist_csv/message_pattern_hit.csv' CSV HEADER
\copy tool_call FROM '/tmp/cchist_csv/tool_call.csv' CSV HEADER
\copy call_danger_hit FROM '/tmp/cchist_csv/call_danger_hit.csv' CSV HEADER
\copy tool_result FROM '/tmp/cchist_csv/tool_result.csv' CSV HEADER
CREATE INDEX ON tool_result (call_id);
ANALYZE;
