import json, re, glob, os
from collections import Counter
pool={d['id']:d for d in json.load(open('pool.json',encoding='utf-8'))}
qs={q['id']:q for q in json.load(open('questions.json',encoding='utf-8'))['questions']}
def norm(s):
    s=(s or '').lower().replace('cchist.public.','')
    s=re.sub(r'\bas \w+\b','',s); s=re.sub(r'[\s;]+',' ',s).strip()
    return s
res={}; turns={}
for f in glob.glob('runs/*_L[01]_r*_b*.jsonl'):
    arm,lv=os.path.basename(f).split('_')[:2]
    c=res.setdefault((lv,arm),Counter())
    for line in open(f,encoding='utf-8'):
        if not line.strip(): continue
        a=json.loads(line); q=qs[a['qid']]
        if q['class'] not in ('copy','near-variant'): continue
        c['n']+=1
        sql=a.get('sql') or ''
        if 'cchist.public' in sql: c['prefix']+=1
        if norm(sql)==norm(pool[q['target_id']]['sql']): c['exact']+=1
for f in glob.glob('runs/*_L[01]_r*_b*.run.json'):
    arm,lv=os.path.basename(f).split('_')[:2]
    turns.setdefault((lv,arm),[]).append(json.load(open(f,encoding='utf-8')).get('num_turns'))
for k in sorted(res):
    c=res[k]; t=turns[k]
    print(k, f"copy+near answers {c['n']}: exact target SQL {c['exact']}, cchist.public prefix {c['prefix']}; turns/process {min(t)}-{max(t)} mean {sum(t)/len(t):.1f}")
