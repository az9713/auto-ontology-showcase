-- P8 decoy tables in database cchist. Real rows, copied from the 5 P7 base tables with warehouse patterns:
-- staging copies with duplicate loads, period splits, per-model splits, archive copies with 1 column changed, rollups.
-- Each decoy is a real table, so a decoy SQL gives a real number that can differ from the target.
-- Load: docker exec -i postgres psql -U postgres -d cchist < p8/decoys.sql
DROP TABLE IF EXISTS stg_tool_call, tool_call_2026h1, tool_call_2026h2, tool_call_opus, tool_call_sonnet, tool_call_fable,
  tool_call_archive, stg_human_message, human_message_2026q2, human_message_2026q3, human_message_archive,
  stg_tool_result, tool_result_2026h1, tool_result_2026h2, tool_result_archive, stg_message_pattern_hit,
  call_danger_hit_v1, tool_call_daily, human_message_daily;

-- Staging: every row once, plus a second load of 1 row in 40 (no primary key, so duplicates stay).
CREATE TABLE stg_tool_call AS SELECT * FROM tool_call UNION ALL SELECT * FROM tool_call WHERE call_id % 40 = 0;
CREATE TABLE stg_human_message AS SELECT * FROM human_message UNION ALL SELECT * FROM human_message WHERE msg_id % 40 = 0;
CREATE TABLE stg_tool_result AS SELECT * FROM tool_result UNION ALL SELECT * FROM tool_result WHERE result_id % 40 = 0;
CREATE TABLE stg_message_pattern_hit AS SELECT * FROM message_pattern_hit UNION ALL SELECT * FROM message_pattern_hit WHERE msg_id % 25 = 0;

-- Period splits (half years and quarters of 2026, by ts).
CREATE TABLE tool_call_2026h1 AS SELECT * FROM tool_call WHERE ts < '2026-07-01';
CREATE TABLE tool_call_2026h2 AS SELECT * FROM tool_call WHERE ts >= '2026-07-01';
CREATE TABLE tool_result_2026h1 AS SELECT * FROM tool_result WHERE ts < '2026-07-01';
CREATE TABLE tool_result_2026h2 AS SELECT * FROM tool_result WHERE ts >= '2026-07-01';
CREATE TABLE human_message_2026q2 AS SELECT * FROM human_message WHERE ts < '2026-07-01';
CREATE TABLE human_message_2026q3 AS SELECT * FROM human_message WHERE ts >= '2026-07-01';

-- Per-model-family splits.
CREATE TABLE tool_call_opus AS SELECT * FROM tool_call WHERE model LIKE 'claude-opus%';
CREATE TABLE tool_call_sonnet AS SELECT * FROM tool_call WHERE model LIKE 'claude-sonnet%';
CREATE TABLE tool_call_fable AS SELECT * FROM tool_call WHERE model LIKE 'claude-fable%';

-- Archive copies from an older log format: 1 column has a different meaning.
-- tool_call_archive: the old format had no sidechain flag, so is_sidechain is false on every row.
CREATE TABLE tool_call_archive AS SELECT call_id, file_id, line_no, ts, model, tool_name, false AS is_sidechain, is_shell FROM tool_call;
-- human_message_archive: the old classifier did not mark noise, so is_noise is false on every row.
CREATE TABLE human_message_archive AS SELECT msg_id, file_id, line_no, ts, model, is_sidechain, false AS is_noise, chars,
  ends_with_q, question_start, imperative FROM human_message;
-- tool_result_archive: the old format had no denied mark, so denied_mark is false on every row.
CREATE TABLE tool_result_archive AS SELECT result_id, file_id, line_no, ts, model, call_id, is_error, false AS denied_mark,
  validation_mark, fastpath FROM tool_result;
-- call_danger_hit_v1: the older danger taxonomy; pattern_id 2 was folded into 1 and 4 into 3.
CREATE TABLE call_danger_hit_v1 AS SELECT DISTINCT call_id, CASE pattern_id WHEN 2 THEN 1 WHEN 4 THEN 3 ELSE pattern_id END::smallint
  AS pattern_id FROM call_danger_hit;

-- Daily rollups.
CREATE TABLE tool_call_daily AS SELECT ts::date AS day, model, tool_name, is_sidechain, count(*)::integer AS n_calls
  FROM tool_call GROUP BY 1, 2, 3, 4;
CREATE TABLE human_message_daily AS SELECT ts::date AS day, model,
  count(*) FILTER (WHERE NOT is_sidechain AND NOT is_noise AND chars > 0)::integer AS typed_messages,
  count(*) FILTER (WHERE is_sidechain)::integer AS sidechain_prompts,
  count(*) FILTER (WHERE is_noise)::integer AS noise_messages
  FROM human_message GROUP BY 1, 2;
ANALYZE;
