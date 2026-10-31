#!/bin/bash
# short fragments (call lines, chat messages, ad snippets): generate, label blind, keep agreeing, explain, advise scams
set -e
# run from the data folder (pipeline.sh does); the scripts live next to this file
HERE=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY=${PY:-python}
export TEACHER_BASE_URL=${TEACHER_BASE_URL:-http://localhost:8000/v1}
export TEACHER_MODEL=${TEACHER_MODEL:-model}
T="--url $TEACHER_BASE_URL/chat/completions --model $TEACHER_MODEL --workers 48"
$PY "$HERE/fragment_specs.py" frag-specs.jsonl 60 2610
$PY "$HERE/teacher.py" frag-specs.jsonl frag-gen.jsonl --mode generate $T --temperature 0.8
$PY -c "
import json
with open('frag-text.jsonl','w') as f:
    for l in open('frag-gen.jsonl'):
        r=json.loads(l); t=r['teacher'].get('text')
        if isinstance(t,str) and len(t)>15: f.write(json.dumps({'id':r['id'],'text':t,'source':'synthetic-fragment','hint':r['hint']},ensure_ascii=False)+'\n')
"
$PY "$HERE/teacher.py" frag-text.jsonl frag-labelled.jsonl --mode label $T --temperature 0
$PY -c "
import json
with open('frag-agree.jsonl','w') as f:
    for l in open('frag-labelled.jsonl'):
        r=json.loads(l); t=r['teacher']
        if t.get('usable') and t.get('verdict')==r['hint']:
            f.write(json.dumps({'id':r['id'],'text':r['text'],'source':r['source'],'style':None,'verdict':t['verdict'],'category':t.get('category'),'flags':t.get('flags',[]),'enron':False},ensure_ascii=False)+'\n')
"
$PY "$HERE/teacher.py" frag-agree.jsonl frag-explained.jsonl --mode explain $T
grep '"verdict": "scam"' frag-explained.jsonl > frag-scam.jsonl || true
$PY "$HERE/teacher.py" frag-scam.jsonl frag-scam-rada.jsonl --mode advise $T
{ grep -v '"verdict": "scam"' frag-explained.jsonl; cat frag-scam-rada.jsonl; } > frag-final.jsonl
wc -l frag-specs.jsonl frag-text.jsonl frag-agree.jsonl frag-final.jsonl
echo PIPELINE DONE
