"""Render audit.json -> self-contained HTML. No transcript access."""
import json, os, collections, html

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = r'C:\Users\<user>\Downloads\agent_letter_x\claude-history-audit.html'
d = json.load(open(os.path.join(HERE, 'audit.json'), encoding='utf-8'))


def sp(key):
    o = collections.defaultdict(collections.Counter)
    for k, v in d[key].items():
        a, _, b = k.partition('||')
        o[a][b] = v
    return o


human = collections.Counter(d['human_by_model'])
corr_msgs = collections.Counter(d['correction_msgs'])
turns = collections.Counter(d['assistant_turns'])
shell = collections.Counter(d['shell_cmds'])
tool_total = collections.Counter(d['tool_total'])
qa = collections.Counter(d['q_asked'])
qv = collections.Counter(d['q_violation'])
repow = collections.Counter(d['repowide'])
corr = sp('corrections')
danger = sp('danger')
errk = sp('err_kind')
errtool = sp('err_by_tool')
tooluse = sp('tool_use')

NICE = {
    'claude-opus-4-8': 'Opus 4.8', 'claude-fable-5': 'Fable 5',
    'claude-opus-5': 'Opus 5', 'claude-sonnet-5': 'Sonnet 5',
    'claude-sonnet-4-6': 'Sonnet 4.6', 'claude-opus-4-7': 'Opus 4.7',
    'claude-haiku-4-5-20251001': 'Haiku 4.5', 'gpt-5.6-sol': 'GPT-5.6 Sol',
    'gpt-5.6-terra': 'GPT-5.6 Terra', 'z-ai/glm-5.2-20260616': 'GLM 5.2',
    'unknown': 'unattributed', '?': 'unknown',
}
n = lambda m: NICE.get(m, m)
# models with enough traffic to compare
MAIN = [m for m in ['claude-opus-4-8', 'claude-fable-5', 'claude-opus-5', 'claude-sonnet-5']]

TOTAL_ERR = sum(sum(v.values()) for v in errk.values())
GENUINE = sum(v.get('genuine', 0) for v in errk.values())
DENIED = sum(v.get('user_denied', 0) for v in errk.values())
BADIN = sum(v.get('bad_tool_input', 0) for v in errk.values())


def pct(a, b, dp=1):
    return '—' if not b else f'{a / b * 100:.{dp}f}%'


def per(a, b, mult=1000, dp=1):
    return '—' if not b else f'{a / b * mult:.{dp}f}'


def rows(items):
    return '\n'.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in items)


def table(headers, body, cls=''):
    h = ''.join(f'<th>{x}</th>' for x in headers)
    return (f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead>'
            f'<tbody>{rows(body)}</tbody></table></div>')


# ---------- coverage ----------
days = 79
cov = table(['Measure', 'Value'], [
    ['Transcript files scanned', f"{d['files']:,}"],
    ['Records parsed', f"{d['lines']:,}"],
    ['Sessions', f"{d['sessions']:,}"],
    ['Distinct project folders', f"{d['projects']:,}"],
    ['Messages you typed', f"{d['human_msgs']:,}"],
    ['Tool calls by agents', f"{sum(tool_total.values()):,}"],
    ['Subagent records (excluded from corrections)', f"{d['sidechain_lines']:,}"],
    ['Date window', f"{d['ts_min'][:10]} to {d['ts_max'][:10]} ({days} days)"],
    ['Records that failed to parse', f"{d['parse_fail']}"],
])

monthly = table(['Month', 'Messages you typed'],
                [[k, f'{v:,}'] for k, v in sorted(d['monthly'].items())])

# ---------- volume ----------
vol = table(['Model', 'Agent turns', 'Tool calls', 'Shell commands', 'Your messages after it'],
            [[n(m), f'{turns[m]:,}', f'{tool_total[m]:,}', f'{shell[m]:,}', f'{human[m]:,}']
             for m, _ in turns.most_common() if m != '<synthetic>'])

# ---------- corrections ----------
crows = []
for m, _ in human.most_common():
    if human[m] < 50:
        continue
    crows.append([n(m), f'{human[m]:,}', f'{corr_msgs[m]:,}',
                  f"<b>{per(corr_msgs[m], human[m], 100, 1)}</b>"])
ctab = table(['Model', 'Your messages', 'Messages that read as a correction',
              'Corrections per 100 messages'], crows)

cats = collections.Counter()
for m, v in corr.items():
    cats.update(v)
CATNAME = {
    'stopped_early': 'Stopped before the job was done',
    'overbuild': 'Built more than asked',
    'misread': 'Misread the request',
    'regression': 'Broke something that worked',
    'blunt_no': 'Flat rejection ("no", "wrong", "stop")',
    'no_verify': 'Claimed done without proof',
    'unsolicited_edit': 'Edited something you did not ask about',
    'tool_misuse': 'Wrong command, tool, or path',
}
cat_rows = []
for c, v in cats.most_common():
    cat_rows.append([CATNAME.get(c, c), f'{v:,}'] +
                    [f'{corr[m][c]:,}' for m in MAIN])
cattab = table(['Failure type', 'Total'] + [n(m) for m in MAIN], cat_rows)

pat_rows = [[f'<code>{html.escape(p)}</code>', f'{v:,}']
            for p, v in sorted(d['pattern'].items(), key=lambda x: -x[1])]
pattab = table(['Exact phrase pattern that matched', 'Hits'], pat_rows, 'small')

# ---------- tool errors ----------
erows = []
for m in [x for x, _ in turns.most_common() if tool_total[x] > 200]:
    g = errk[m].get('genuine', 0)
    erows.append([n(m), f'{tool_total[m]:,}', f'{g:,}', pct(g, tool_total[m], 2),
                  f"{errk[m].get('user_denied', 0):,}", f"{errk[m].get('bad_tool_input', 0):,}"])
etab = table(['Model', 'Tool calls', 'Real failures', 'Failure rate',
              'You blocked it', 'Malformed tool call'], erows)

et = collections.Counter()
for m, v in errtool.items():
    et.update(v)
tu = collections.Counter()
for m, v in tooluse.items():
    tu.update(v)
ertool = table(['Tool', 'Times used', 'Real failures', 'Failure rate'],
               [[t, f'{tu[t]:,}', f'{c:,}', pct(c, tu[t], 1)] for t, c in et.most_common(12)])

# ---------- danger ----------
DKIND = ['kill_by_pattern', 'kill_pid', 'rm_rf', 'git_hard_reset',
         'git_force_push', 'git_clean', 'git_discard']
DNAME = {'kill_by_pattern': 'Kill by name pattern<br><small>pkill / taskkill</small>',
         'kill_pid': 'Kill a process<br><small>kill / Stop-Process</small>',
         'rm_rf': 'Recursive force delete<br><small>rm -rf / Remove-Item -Recurse -Force</small>',
         'git_hard_reset': 'git reset --hard', 'git_force_push': 'git push --force',
         'git_clean': 'git clean -f', 'git_discard': 'git checkout -- (discard edits)'}
dmodels = [m for m in [x for x, _ in turns.most_common()] if sum(danger[m].values())]
drows = [[DNAME.get(k, k), f'{sum(danger[m][k] for m in dmodels):,}'] +
         [f'{danger[m][k]:,}' for m in MAIN] for k in DKIND]
drows.append(['<b>Total</b>', f"<b>{sum(sum(danger[m].values()) for m in dmodels):,}</b>"] +
             [f'<b>{sum(danger[m].values()):,}</b>' for m in MAIN])
drows.append(['<b>Per 1,000 shell commands</b>', '—'] +
             [f'<b>{per(sum(danger[m].values()), shell[m])}</b>' for m in MAIN])
dtab = table(['Risky command', 'Total'] + [n(m) for m in MAIN], drows)

# ---------- questions read-only ----------
qrows = []
for m in MAIN + ['unknown']:
    if not qa[m]:
        continue
    qrows.append([n(m), f'{qa[m]:,}', f'{qv[m]:,}', f'<b>{pct(qv[m], qa[m])}</b>'])
qtab = table(['Model', 'Questions you asked', 'Times it edited a file anyway',
              'Share of questions'], qrows)

rtab = table(['Model', 'Whole-project checks run'],
             [[n(m), f'{v:,}'] for m, v in repow.most_common()])

TOTQ = sum(qa[m] for m in qa)
TOTQV = sum(qv[m] for m in qv)
TOTD = sum(sum(danger[m].values()) for m in dmodels)
TOTKILL = sum(danger[m]['kill_by_pattern'] + danger[m]['kill_pid'] for m in dmodels)
TOTRM = sum(danger[m]['rm_rf'] for m in dmodels)
TOTC = sum(corr_msgs.values())

CSS = """
:root{--bg:#fbfaf8;--fg:#1c1a17;--mut:#6b655d;--line:#e2ddd4;--card:#fff;
--accent:#8a4b2a;--warn:#9a3412;--ok:#3f6212;--code:#f3f0ea;}
:root:not([data-theme=light]){}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#14120f;--fg:#eae5dc;--mut:#9a9186;--line:#2e2a24;--card:#1b1815;
--accent:#e0a074;--warn:#f0a080;--ok:#a3c25a;--code:#221f1a;}}
:root[data-theme=dark]{--bg:#14120f;--fg:#eae5dc;--mut:#9a9186;--line:#2e2a24;
--card:#1b1815;--accent:#e0a074;--warn:#f0a080;--ok:#a3c25a;--code:#221f1a;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;
font:16px/1.65 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif;}
.wrap{max-width:960px;margin:0 auto;padding:48px 22px 96px}
h1{font-size:2.05rem;line-height:1.15;margin:0 0 .3em;letter-spacing:-.02em}
h2{font-size:1.32rem;margin:2.9em 0 .2em;letter-spacing:-.01em;
padding-top:.9em;border-top:1px solid var(--line)}
h3{font-size:1.02rem;margin:2em 0 .4em;color:var(--accent)}
.sub{color:var(--mut);font-size:1.02rem;margin:0 0 2em}
.lede{font-size:1.06rem}
p{margin:.85em 0}
.tw{overflow-x:auto;margin:1.1em 0;border:1px solid var(--line);border-radius:10px;
background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:.93rem;min-width:460px}
th,td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--line);
vertical-align:top}
th{font-weight:600;font-size:.79rem;text-transform:uppercase;letter-spacing:.05em;
color:var(--mut);background:color-mix(in srgb,var(--line) 30%,transparent)}
tr:last-child td{border-bottom:none}
td:not(:first-child),th:not(:first-child){text-align:right;
font-variant-numeric:tabular-nums;white-space:nowrap}
table.small{font-size:.8rem}
code{background:var(--code);padding:1px 5px;border-radius:4px;
font:.85em ui-monospace,"Cascadia Code",Consolas,monospace}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;
margin:1.6em 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px}
.kpi b{display:block;font-size:1.75rem;line-height:1.1;letter-spacing:-.02em;
font-variant-numeric:tabular-nums}
.kpi span{color:var(--mut);font-size:.79rem;display:block;margin-top:5px}
.note{border-left:3px solid var(--accent);background:var(--card);padding:13px 17px;
margin:1.4em 0;border-radius:0 8px 8px 0}
.note.warn{border-color:var(--warn)}
.note p:first-child{margin-top:0}.note p:last-child{margin-bottom:0}
.tag{display:inline-block;font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;
padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--mut);
vertical-align:middle;margin-left:8px}
ol,ul{padding-left:1.3em}li{margin:.42em 0}
footer{margin-top:4em;padding-top:1.4em;border-top:1px solid var(--line);
color:var(--mut);font-size:.85rem}
"""

HTML = f"""<title>History Audit</title>
<style>{CSS}</style>
<div class="wrap">
<h1>What actually goes wrong when I work with you</h1>
<p class="sub">A read-only audit of your Claude Code history &middot;
{d['ts_min'][:10]} to {d['ts_max'][:10]}</p>

<p class="lede">This copies Theo's method: do not guess which rules you need, count the
failures you already had. Every number below comes from your own transcripts. Nothing
was changed, and no transcript text was read into the conversation &mdash; a script did
the counting and reported totals only.</p>

<div class="grid">
<div class="kpi"><b>{d['files']:,}</b><span>transcript files</span></div>
<div class="kpi"><b>{d['human_msgs']:,}</b><span>messages you typed</span></div>
<div class="kpi"><b>{sum(tool_total.values()):,}</b><span>tool calls by agents</span></div>
<div class="kpi"><b>{TOTC:,}</b><span>read as corrections</span></div>
<div class="kpi"><b>{TOTD:,}</b><span>risky shell commands</span></div>
</div>

<h2>1. How to read this</h2>
<p>Three warnings, so you do not over-trust the numbers.</p>
<ol>
<li><b>These are word-matching guesses, not judgements.</b> A script looked for phrases
like "no", "simpler", "you broke". It cannot tell a correction from a joke. Treat every
count as a pointer to look closer, not as proof.</li>
<li><b>Harder jobs go to stronger models.</b> You send your hardest work to Fable&nbsp;5
and Opus. Those models will look worse on any correction count for that reason alone.
Theo hit the same trap and said so explicitly.</li>
<li><b>Every rate has its denominator printed next to it.</b> Compare rates, never raw
totals.</li>
</ol>

<h3>Coverage</h3>
{cov}
{monthly}
<p class="sub" style="font-size:.9rem;margin-top:-.4em">Your history is 11 weeks old and
heavily concentrated in July 2026.</p>

<h2>2. How much work each model did</h2>
<p>Context first. Without this the later tables mislead.</p>
{vol}
<p>Opus&nbsp;4.8 did the most work by a wide margin, then Fable&nbsp;5 and Opus&nbsp;5.
"Your messages after it" is the denominator used in the next section: it counts messages
you typed directly after that model's turn.</p>

<h2>3. How often you had to correct <span class="tag">headline</span></h2>
{ctab}
<p>The spread is narrow. Overall <b>{TOTC:,} of your {d['human_msgs']:,} messages
&mdash; {pct(TOTC, d['human_msgs'])}, about one in {d['human_msgs'] / TOTC:.0f}</b>
&mdash; read as a correction, and no model sits far from that. This is the most useful
fact in the report: your correction rate is a
property of <em>your setup</em>, not of which model you pick. Swapping models will not
fix it. Changing your instructions might.</p>

<h3>What you were correcting</h3>
{cattab}

<div class="note warn">
<p><b>Read this before trusting the table above.</b> The "built more than asked" row is
inflated. It counts the words <code>minimal</code>, <code>simplify</code> and
<code>yagni</code> &mdash; but those are your standing house style, so you often type
them <em>before</em> the agent does anything wrong. That is an instruction, not a
correction. The honest version of that row is closer to the 64 hits on
<code>too much / too complex / over-engineer</code>.</p>
</div>

<p>Here is the raw evidence, so you can judge each pattern yourself:</p>
{pattab}

<h3>What survives the scrutiny</h3>
<ol>
<li><b>Stopping early is your real number one.</b> 125 messages say some form of
<em>you stopped / not done / incomplete / finish it</em>, plus 122 more of
<em>continue / keep going</em>. Those phrases have no innocent reading. This is the
failure worth writing a rule about.</li>
<li><b>Misreading the request is second.</b> 82 messages contain
<em>misunderstood / misread / re-read</em>, plus 13 of <em>I said / I asked for</em>.</li>
<li><b>Breaking working things is third and it is expensive.</b> 52 hits on
<em>you broke / worked before / regression</em>, and 22 on <em>still broken</em>. Low
count, high cost each time.</li>
<li><b>Unrequested edits are rare.</b> 32 total. Your agents mostly stay in their lane.</li>
</ol>

<h2>4. Questions that turned into edits <span class="tag">Theo's rule</span></h2>
<p>Theo's most-praised single line is <em>"questions are read-only"</em>. He added it
because models started editing when he only asked about something. Here is your version
of that count. A "question" is a short message ending in "?" or opening with a question
word, with no command verb in it.</p>
{qtab}
<p><b>{TOTQV} times out of {TOTQ} questions &mdash; about
{pct(TOTQV, TOTQ, 0)} &mdash; an agent edited a file when you had only asked something.</b>
Opus&nbsp;4.8 is the worst at one in five. This is a real, specific, fixable failure, and
you currently have no rule against it.</p>

<h2>5. Risky shell commands</h2>
<p>Theo's audit found Opus 5 killing the wrong processes, including the app it was
running inside. Here is the same count for you. Note carefully: this counts commands
<em>attempted</em>. It does <b>not</b> mean any of them caused damage. Most were probably
correct.</p>
{dtab}
<p>Totals: <b>{TOTKILL}</b> process-kill commands and <b>{TOTRM}</b> recursive force
deletes across the whole window.</p>
<div class="note">
<p><b>Kill-by-pattern is the one to watch.</b> {sum(danger[m]['kill_by_pattern'] for m in dmodels)}
commands used <code>pkill</code> or <code>taskkill</code>, which match a process by
<em>name</em> rather than by a known ID. That is exactly the failure Theo made rule
number one in his file: your own agent process, and other unrelated jobs, can match the
same name pattern. Opus&nbsp;4.8 accounts for {danger['claude-opus-4-8']['kill_by_pattern']}
of them.</p>
</div>
<h3>Whole-project checks</h3>
<p>Running the full test or build suite when a targeted check would do. Theo calls these
out because they burn minutes and machine time for no extra information.</p>
{rtab}
<p>{sum(repow.values())} in total. Low, but Fable&nbsp;5 does it most.</p>

<h2>6. Tool failures</h2>
<p>The raw error flag is misleading, so it is split three ways: commands that genuinely
failed, calls you refused to permit, and malformed tool calls the agent got wrong on its
own.</p>
{etab}
<p>Overall: <b>{GENUINE:,}</b> real failures, <b>{DENIED:,}</b> you blocked, and
<b>{BADIN:,}</b> malformed calls, out of {sum(tool_total.values()):,} tool calls.
The real failure rate is about {pct(GENUINE, sum(tool_total.values()), 1)} &mdash;
healthy. Malformed calls are the interesting column, because those are pure model error
with no external cause. Opus&nbsp;4.8 leads at {errk['claude-opus-4-8'].get('bad_tool_input', 0)}.</p>
<h3>Which tools fail</h3>
{ertool}
<div class="note">
<p><b>Read failing {pct(et['Read'], tu['Read'], 1)} of the time is a workflow smell.</b>
{et['Read']:,} failed <code>Read</code> calls almost always mean one thing: the agent
guessed a file path instead of finding it first. That is a cheap fix &mdash; a rule
saying "locate with Glob or Grep before Read" would remove most of them.</p>
</div>

<h2>7. What the evidence supports changing</h2>
<p>Theo's rule is one instruction per <em>confirmed, repeated</em> failure. Nothing here
was applied. These are proposals, ranked by how well your own data backs them.</p>
<ol>
<li><b>Make questions read-only.</b> Backed by {TOTQV} incidents in {TOTQ} questions.
Strongest evidence in the report, and the cheapest fix.</li>
<li><b>Ban kill-by-pattern.</b> Backed by
{sum(danger[m]['kill_by_pattern'] for m in dmodels)} <code>pkill</code>/<code>taskkill</code>
commands. Copy Theo's shape: kill only a process ID you captured yourself when you started it.</li>
<li><b>Require finishing, or naming what is left.</b> Backed by 261 stop-early
corrections, your largest clean category. Theo's phrasing works: finish every part, and
state plainly which parts you did not do and why.</li>
<li><b>Find the path before reading it.</b> Backed by {et['Read']:,} failed reads.</li>
<li><b>Say what broke and what you checked.</b> Backed by 74 regression corrections and
55 "prove it" messages. These are your most expensive failures even though they are not
your most frequent.</li>
</ol>
<div class="note">
<p><b>And the thing not to do:</b> your correction rate barely moves between models
({min(corr_msgs[m] / human[m] for m in MAIN) * 100:.1f}% to
{max(corr_msgs[m] / human[m] for m in MAIN) * 100:.1f}%). Do not spend effort choosing
models. Spend it on the instructions, which are shared across all of them.</p>
</div>

<h2>8. What this audit did not cover</h2>
<ul>
<li><b>Codex history.</b> 900 session files, 1.1&nbsp;GB, sitting in
<code>~/.codex/sessions</code>. Untouched, because you asked for Claude Code. Worth a
second pass if you want the cross-harness comparison Theo did.</li>
<li><b>Subagent behaviour.</b> {d['sidechain_lines']:,} records came from subagents.
Their tool use is counted, but corrections are not, because those messages come from an
orchestrating agent and not from you.</li>
<li><b>Whether corrections were justified.</b> A phrase match cannot tell whether the
agent was actually wrong.</li>
<li><b>{human['unknown']:,} of your messages</b> could not be attributed to a model
because no agent turn came before them in the file. They are usually the first message
of a session, and they are excluded from the per-model rates.</li>
<li><b>Cost and time.</b> Not measured. Theo tracks how long over-long jobs take; that
needs a different pass.</li>
</ul>

<footer>
<p>Read-only audit. {d['files']:,} files and {d['lines']:,} records scanned by script;
no transcript content entered the conversation, and no file was modified except this
report. {d['parse_fail']} record failed to parse. {d['bigline_fastpath']:,} oversized
records used a reduced counting path and contribute only to the tool-failure totals.</p>
<p>Generated by Claude Opus 5 in Claude Code, following the audit method described by
Theo (t3.gg) in <i>How I Rebuilt My Coding-Agent Workflow</i>.</p>
</footer>
</div>
"""

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('WROTE', OUT, len(HTML), 'bytes')
