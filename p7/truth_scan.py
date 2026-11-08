"""P7 copy of the 2026-08-12 audit scan (rebuilt from its transcript), plus a time cutoff.
Only change: records with timestamp > CUTOFF are skipped, so the scan sees the store as on 2026-08-12.

Read-only scan of Claude Code transcripts -> aggregate JSON.

Never prints transcript content. Emits counts only.
ponytail: one pass, cheap-regex fast path for oversized lines.
"""
import json, glob, re, sys, collections, os

ROOT = 'C:/Users/<user>/.claude/projects'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'truth_scan.json')
CUTOFF = '2026-08-12T10:13:40.761Z'  # ts_max of the audit's final run
RE_TS = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
BIG = 120_000  # lines longer than this use the regex fast path

RE_ISERR = re.compile(r'"is_error"\s*:\s*true')
RE_TRES = re.compile(r'"type"\s*:\s*"tool_result"')

# --- correction detection (human messages only) -------------------------
CORRECTION = [
    (r'^\s*(no|nope|wrong|stop|nah)\b', 'blunt_no'),
    (r"\bthat'?s (not|wrong|incorrect)\b", 'blunt_no'),
    (r"\bnot what i (meant|asked|wanted|said)\b", 'misread'),
    (r"\bi (said|asked for|told you)\b", 'misread'),
    (r'\bmisunderstood\b|\bmisread\b|\bre-?read\b', 'misread'),
    (r'\bundo\b|\brevert (that|this|it)\b', 'unsolicited_edit'),
    (r"\bi didn'?t ask\b|\bdon'?t (edit|change|touch|modify)\b", 'unsolicited_edit'),
    (r'\bwhy did you (edit|change|add|create|delete|remove)\b', 'unsolicited_edit'),
    (r'\btoo (much|complex|complicated|many)\b|\bover-?engineer', 'overbuild'),
    (r'\bsimpler\b|\bsimplify\b|\byagni\b|\bbloat\b|\bminimal\b', 'overbuild'),
    (r"\byou (didn'?t need|did not need)\b", 'overbuild'),
    (r'\bkeep going\b|\bcarry on\b|\bgo on\b', 'stopped_early'),
    (r'^\s*continue\b|\bplease continue\b', 'stopped_early'),
    (r'\byou stopped\b|\bnot (done|finished)\b|\bfinish (it|the)\b|\bincomplete\b', 'stopped_early'),
    (r'\bwhy did you stop\b|\bthat\'?s not all\b|\brest of\b.*\b(it|them|the work)\b', 'stopped_early'),
    (r"\bdid you (test|verify|check|run)\b|\byou didn'?t (test|verify|check)\b", 'no_verify'),
    (r'\bverify\b.*\bfirst\b|\bprove it\b|\bshow me (the )?(proof|screenshot|output)\b', 'no_verify'),
    (r'\byou broke\b|\bworked before\b|\bregression\b|\bbroke (it|the)\b', 'regression'),
    (r'\bstill (broken|not working|failing|wrong|the same)\b', 'regression'),
    (r'\bwrong (command|tool|file|path|flag)\b|\buse .{0,20} instead\b', 'tool_misuse'),
    (r"\bthat command\b.*\b(fail|wrong|error)\b", 'tool_misuse'),
]
CORRECTION = [(re.compile(p, re.I), c, p) for p, c in CORRECTION]

# --- dangerous / heavy shell --------------------------------------------
DANGER = [
    (r'\bpkill\b|\bpgrep\b.*\bkill\b', 'kill_by_pattern'),
    (r'\btaskkill\b', 'kill_by_pattern'),
    (r'\bkill\s+-9\b|\bkill\s+\$\(|\bkill\s+\d+', 'kill_pid'),
    (r'\bStop-Process\b', 'kill_pid'),
    (r'\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r', 'rm_rf'),
    (r'Remove-Item\b[^\n]*-Recurse[^\n]*-Force', 'rm_rf'),
    (r'git\s+reset\s+--hard', 'git_hard_reset'),
    (r'git\s+push\b[^\n]*--force', 'git_force_push'),
    (r'git\s+clean\s+-[a-z]*f', 'git_clean'),
    (r'git\s+checkout\s+--\s', 'git_discard'),
]
DANGER = [(re.compile(p, re.I), c) for p, c in DANGER]

RE_REPOWIDE = re.compile(
    r'\b(npm|pnpm|yarn|bun|vp)\s+(run\s+)?(-r\s+)?(test|build|lint|typecheck|check)\b', re.I)
RE_HASPATH = re.compile(r'\s(\./|src/|test|[\w\-/]+\.(ts|tsx|js|py|go|rs|md))\b')

RE_QUESTION_START = re.compile(
    r'^\s*(what|why|how|where|which|who|when|is|are|was|were|does|do|did|can|could|'
    r'should|would|will|any|has|have|am i|do i|whats|what\'s)\b', re.I)
RE_IMPERATIVE = re.compile(
    r'\b(fix|add|make|implement|create|run|update|write|change|build|install|delete|'
    r'remove|refactor|rename|deploy|commit|push|generate|set up|setup)\b', re.I)

# noise that is not a typed human message
RE_NOISE = re.compile(
    r'^\s*<(system-reminder|command-name|command-message|command-args|'
    r'local-command-stdout|local-command-stderr|user-prompt-submit-hook|'
    r'bash-input|bash-stdout|bash-stderr|channel)\b', re.I)
RE_CAVEAT = re.compile(r'^Caveat: The messages below were generated', re.I)

EDIT_TOOLS = {'Edit', 'Write', 'NotebookEdit', 'MultiEdit'}

DENY_MARK = re.compile(
    r"user (doesn'?t want|rejected|declined|has denied)|"
    r"requested permission|tool use was rejected|operation was (aborted|cancelled|canceled)|"
    r"user chose not to", re.I)
VALIDATION_MARK = re.compile(r'InputValidationError|does not match the required schema', re.I)


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get('type') == 'text':
                out.append(b.get('text') or '')
        return '\n'.join(out)
    return ''


def has_tool_result(content):
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get('type') == 'tool_result' for b in content)


agg = {
    'files': 0, 'lines': 0, 'bigline_fastpath': 0, 'parse_fail': 0,
    'sessions': set(), 'projects': set(),
    'ts_min': None, 'ts_max': None,
    'human_msgs': 0, 'human_by_model': collections.Counter(),
    'human_chars': 0,
    'sidechain_lines': 0,
    'assistant_turns': collections.Counter(),      # model -> assistant messages
    'tool_use': collections.Counter(),             # (model, tool) -> n
    'tool_total': collections.Counter(),           # model -> n
    'tres_total': 0, 'tres_err_total': 0,
    'err_kind': collections.Counter(),             # (model, kind) -> n
    'err_by_tool': collections.Counter(),          # (model, tool) -> genuine errors
    'corrections': collections.Counter(),          # (model, category) -> n
    'pattern': collections.Counter(),              # regex source -> n
    'correction_msgs': collections.Counter(),      # model -> messages containing >=1 hit
    'danger': collections.Counter(),               # (model, kind) -> n
    'repowide': collections.Counter(),             # model -> n
    'shell_cmds': collections.Counter(),           # model -> n
    'q_asked': collections.Counter(),              # model -> questions asked
    'q_violation': collections.Counter(),          # model -> question followed by edit
    'monthly': collections.Counter(),              # YYYY-MM -> human msgs
}


def note_ts(ts):
    if not ts:
        return
    if agg['ts_min'] is None or ts < agg['ts_min']:
        agg['ts_min'] = ts
    if agg['ts_max'] is None or ts > agg['ts_max']:
        agg['ts_max'] = ts


files = glob.glob(ROOT + '/**/*.jsonl', recursive=True)
total = len(files)

for fi, path in enumerate(files):
    if fi % 200 == 0:
        print(f'  {fi}/{total}', file=sys.stderr, flush=True)
    agg['files'] += 1
    last_model = None          # model of most recent assistant turn in this file
    tool_names = {}            # tool_use_id -> name
    pending_q = False          # last human msg was a question
    pending_q_model = None
    try:
        fh = open(path, encoding='utf-8', errors='replace')
    except OSError:
        continue
    with fh:
        for line in fh:
            agg['lines'] += 1
            if len(line) > BIG:
                mts = RE_TS.search(line)
                if mts and mts.group(1) > CUTOFF:
                    continue
                # fast path: only harvest tool_result / error signal
                agg['bigline_fastpath'] += 1
                n = len(RE_TRES.findall(line))
                if n:
                    agg['tres_total'] += n
                    e = len(RE_ISERR.findall(line))
                    agg['tres_err_total'] += e
                    if e:
                        agg['err_kind'][(last_model or 'unknown', 'genuine')] += e
                continue
            try:
                d = json.loads(line)
            except Exception:
                agg['parse_fail'] += 1
                continue

            if (d.get('timestamp') or '') > CUTOFF:
                continue
            t = d.get('type')
            sid = d.get('sessionId')
            if sid:
                agg['sessions'].add(sid)
            cwd = d.get('cwd')
            if cwd:
                agg['projects'].add(cwd)
            note_ts(d.get('timestamp'))
            side = bool(d.get('isSidechain'))
            if side:
                agg['sidechain_lines'] += 1
            msg = d.get('message') or {}
            content = msg.get('content')

            if t == 'assistant':
                model = msg.get('model') or 'unknown'
                if model == '<synthetic>':
                    continue
                last_model = model
                agg['assistant_turns'][model] += 1
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict) or b.get('type') != 'tool_use':
                            continue
                        name = b.get('name') or '?'
                        tool_names[b.get('id')] = name
                        agg['tool_use'][(model, name)] += 1
                        agg['tool_total'][model] += 1
                        if pending_q and name in EDIT_TOOLS and not side:
                            agg['q_violation'][pending_q_model or model] += 1
                            pending_q = False
                        inp = b.get('input') or {}
                        cmd = inp.get('command') if isinstance(inp, dict) else None
                        if isinstance(cmd, str) and name in ('Bash', 'PowerShell'):
                            agg['shell_cmds'][model] += 1
                            for rx, kind in DANGER:
                                if rx.search(cmd):
                                    agg['danger'][(model, kind)] += 1
                            m = RE_REPOWIDE.search(cmd)
                            if m and not RE_HASPATH.search(cmd):
                                agg['repowide'][model] += 1

            elif t == 'user':
                if has_tool_result(content):
                    for b in content:
                        if not isinstance(b, dict) or b.get('type') != 'tool_result':
                            continue
                        agg['tres_total'] += 1
                        if not b.get('is_error'):
                            continue
                        agg['tres_err_total'] += 1
                        body = b.get('content')
                        body = body if isinstance(body, str) else json.dumps(body)[:4000]
                        mdl = last_model or 'unknown'
                        if DENY_MARK.search(body):
                            kind = 'user_denied'
                        elif VALIDATION_MARK.search(body):
                            kind = 'bad_tool_input'
                        else:
                            kind = 'genuine'
                            agg['err_by_tool'][(mdl, tool_names.get(b.get('tool_use_id'), '?'))] += 1
                        agg['err_kind'][(mdl, kind)] += 1
                    continue

                if side:
                    continue  # orchestrator prompt, not the owner
                txt = text_of(content)
                if not txt.strip():
                    continue
                if RE_NOISE.match(txt.strip()) or RE_CAVEAT.match(txt.strip()):
                    continue
                # strip trailing injected reminders before matching
                txt = re.split(r'<system-reminder>', txt)[0].strip()
                if not txt:
                    continue

                mdl = last_model or 'unknown'
                agg['human_msgs'] += 1
                agg['human_chars'] += len(txt)
                agg['human_by_model'][mdl] += 1
                ts = d.get('timestamp') or ''
                if len(ts) >= 7:
                    agg['monthly'][ts[:7]] += 1

                hit = False
                for rx, cat, pat in CORRECTION:
                    if rx.search(txt):
                        agg['corrections'][(mdl, cat)] += 1
                        agg['pattern'][pat] += 1
                        hit = True
                if hit:
                    agg['correction_msgs'][mdl] += 1

                short = len(txt) < 400
                is_q = short and (txt.rstrip().endswith('?') or RE_QUESTION_START.match(txt))
                if is_q and not RE_IMPERATIVE.search(txt):
                    agg['q_asked'][mdl] += 1
                    pending_q = True
                    pending_q_model = mdl
                else:
                    pending_q = False

# --- serialise -----------------------------------------------------------
def ckey(c):
    return {('%s||%s' % k if isinstance(k, tuple) else str(k)): v for k, v in c.items()}

out = {k: (sorted(v) if isinstance(v, set) else ckey(v) if isinstance(v, collections.Counter) else v)
       for k, v in agg.items()}
out['sessions'] = len(agg['sessions'])
out['projects'] = len(agg['projects'])
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=1)

print('DONE', OUT)
print('files', agg['files'], 'lines', agg['lines'], 'fastpath', agg['bigline_fastpath'],
      'parsefail', agg['parse_fail'])
print('sessions', out['sessions'], 'projects', out['projects'])
print('human msgs', agg['human_msgs'], 'window', agg['ts_min'], '->', agg['ts_max'])
print('tool_results', agg['tres_total'], 'errors', agg['tres_err_total'])
print('models', dict(agg['assistant_turns']))
