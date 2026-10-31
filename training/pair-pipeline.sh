#!/bin/bash
# contrastive pairs (same request, normal vs suspicious context): generate, label blind, keep agreeing, explain, advise, proofread
set -e
# run from the data folder (pipeline.sh does); the scripts live next to this file
HERE=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY=${PY:-python}
export TEACHER_BASE_URL=${TEACHER_BASE_URL:-http://localhost:8000/v1}
export TEACHER_MODEL=${TEACHER_MODEL:-model}
T="--url $TEACHER_BASE_URL/chat/completions --model $TEACHER_MODEL --workers 48"
NEWNUM=$($PY -c "import contrast_specs as c; print([i for i,p in enumerate(c.PAIRS) if p[0]==\"save a relative's new number\"][0])")
$PY "$HERE/contrast_specs.py" pair-specs.jsonl 40 3010
$PY "$HERE/teacher.py" pair-specs.jsonl pair-gen.jsonl --mode generate $T --temperature 0.9
$PY -c "
import json,re
with open('pair-text.jsonl','w') as f:
    for l in open('pair-gen.jsonl'):
        r=json.loads(l); t=r['teacher'].get('text')
        if isinstance(t,str) and len(t)>15 and not re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]',t): f.write(json.dumps({'id':r['id'],'text':t,'source':'synthetic-contrast','hint':r['hint'],'principle':r['principle']},ensure_ascii=False)+'\n')
"
$PY "$HERE/teacher.py" pair-text.jsonl pair-labelled.jsonl --mode label $T --temperature 0
$PY -c "
import json
with open('pair-agree.jsonl','w') as f:
    for l in open('pair-labelled.jsonl'):
        r=json.loads(l); t=r['teacher']
        # the bare 'new number' opener is a scam by decision, even though a blind labeller calls it insufficient
        newnum=r['id'].startswith('pair-scam-$NEWNUM-')
        if t.get('usable') and (t.get('verdict')==r['hint'] or newnum):
            f.write(json.dumps({'id':r['id'],'text':r['text'],'source':r['source'],'style':None,'verdict':r['hint'],'category':t.get('category') or ('family' if newnum else None),'flags':t.get('flags',[]),'enron':False,'principle':r['principle']},ensure_ascii=False)+'\n')
"
$PY "$HERE/teacher.py" pair-agree.jsonl pair-explained.jsonl --mode explain $T
grep '"verdict": "scam"' pair-explained.jsonl > pair-scam.jsonl || true
$PY "$HERE/teacher.py" pair-scam.jsonl pair-scam-rada.jsonl --mode advise $T
{ grep -v '"verdict": "scam"' pair-explained.jsonl; cat pair-scam-rada.jsonl; } > pair-final-raw.jsonl
$PY "$HERE/proofread.py" pair-final-raw.jsonl pair-final.jsonl pair-fixes.jsonl
wc -l pair-specs.jsonl pair-text.jsonl pair-agree.jsonl pair-final.jsonl
echo PIPELINE DONE
