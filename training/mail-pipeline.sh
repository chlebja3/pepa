#!/bin/bash
# generate synthetic e-mails, then label them blind (the label prompt never sees the intended verdict)
set -e
# run from the data folder (pipeline.sh does); the scripts live next to this file
HERE=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY=${PY:-python}
export TEACHER_BASE_URL=${TEACHER_BASE_URL:-http://localhost:8000/v1}
export TEACHER_MODEL=${TEACHER_MODEL:-model}
T="--url $TEACHER_BASE_URL/chat/completions --model $TEACHER_MODEL --workers 64"
for s in eval train; do
  $PY "$HERE/teacher.py" mail-specs-$s.jsonl mail-gen-$s.jsonl --mode generate $T --temperature 0.8
  $PY -c "
import json,sys
with open(\"mail-text-$s.jsonl\",\"w\") as f:
    for l in open(\"mail-gen-$s.jsonl\"):
        r=json.loads(l); t=r[\"teacher\"].get(\"text\")
        if isinstance(t,str) and len(t)>80: f.write(json.dumps({\"id\":r[\"id\"],\"text\":t,\"source\":\"synthetic-mail\",\"hint\":r[\"hint\"]},ensure_ascii=False)+\"\n\")
"
  $PY "$HERE/teacher.py" mail-text-$s.jsonl mail-labelled-$s.jsonl --mode label $T --max-chars 6000 --temperature 0
done
echo PIPELINE DONE
