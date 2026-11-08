-- P7: 1 SQL per truth number (database cchist). Each must equal p7/truth_scan.json.
-- Counted human message = NOT is_sidechain AND NOT is_noise AND chars > 0.
-- Correction pattern ids (position in CORRECTION): 1-2 blunt_no, 3-5 misread, 6-8 unsolicited_edit,
-- 9-11 overbuild, 12-15 stopped_early, 16-17 no_verify, 18-19 regression, 20-21 tool_misuse.
-- Danger pattern ids (position in DANGER): 1-2 kill_by_pattern, 3-4 kill_pid, 5-6 rm_rf, 7 git_hard_reset,
-- 8 git_force_push, 9 git_clean, 10 git_discard.

-- T1 typed human messages (6498)
SELECT 'T1_human_msgs' AS k, count(*) FROM human_message
WHERE NOT is_sidechain AND NOT is_noise AND chars > 0;

-- T2 messages with at least 1 correction (601)
SELECT 'T2_correction_msgs', count(DISTINCT h.msg_id) FROM human_message h JOIN message_pattern_hit p USING (msg_id)
WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0;

-- T3 "stopped early" corrections = pattern hits, not messages (261)
SELECT 'T3_stopped_early', count(*) FROM human_message h JOIN message_pattern_hit p USING (msg_id)
WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0 AND p.pattern_id BETWEEN 12 AND 15;

-- T4 "over-building" corrections = pattern hits (246)
SELECT 'T4_overbuild', count(*) FROM human_message h JOIN message_pattern_hit p USING (msg_id)
WHERE NOT h.is_sidechain AND NOT h.is_noise AND h.chars > 0 AND p.pattern_id BETWEEN 9 AND 11;

-- T5 failed Read calls: error result, not denied, not validation, linked to a Read call (493)
SELECT 'T5_read_failures', count(*) FROM tool_result r JOIN tool_call c USING (call_id)
WHERE c.tool_name = 'Read' AND r.is_error AND NOT r.denied_mark AND NOT r.validation_mark;

-- T6 all Read calls, sidechain included (13933)
SELECT 'T6_read_calls', count(*) FROM tool_call WHERE tool_name = 'Read';

-- T7 questions (585)
SELECT 'T7_questions', count(*) FROM human_message
WHERE NOT is_sidechain AND NOT is_noise AND chars > 0
  AND chars < 400 AND (ends_with_q OR question_start) AND NOT imperative;

-- T8 questions followed by an edit before the next counted message, main thread only (92)
WITH c AS (
  SELECT msg_id, file_id, line_no, model,
         chars < 400 AND (ends_with_q OR question_start) AND NOT imperative AS is_q,
         lead(line_no) OVER (PARTITION BY file_id ORDER BY line_no) AS next_line
  FROM human_message WHERE NOT is_sidechain AND NOT is_noise AND chars > 0)
SELECT 'T8_question_violations', count(*) FROM c
WHERE is_q AND EXISTS (
  SELECT 1 FROM tool_call t
  WHERE t.file_id = c.file_id AND t.line_no > c.line_no AND (c.next_line IS NULL OR t.line_no < c.next_line)
    AND t.tool_name IN ('Edit', 'Write', 'NotebookEdit', 'MultiEdit') AND NOT t.is_sidechain);

-- T9 kill-by-pattern commands = hits of danger patterns 1-2, per model of the call (106)
SELECT 'T9_kill_by_pattern|' || c.model, count(*) FROM call_danger_hit d JOIN tool_call c USING (call_id)
WHERE d.pattern_id IN (1, 2) GROUP BY c.model ORDER BY 1;
