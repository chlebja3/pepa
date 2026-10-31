#!/bin/bash
# synthetic web pages and SMS for the screener, labelled blind like the e-mails (mail-pipeline.sh)
set -e
# run from the data folder (pipeline.sh does); the scripts live next to this file
HERE=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY=${PY:-python}
export TEACHER_BASE_URL=${TEACHER_BASE_URL:-http://localhost:8000/v1}
export TEACHER_MODEL=${TEACHER_MODEL:-model}
T="--url $TEACHER_BASE_URL/chat/completions --model $TEACHER_MODEL --workers 48"
$PY "$HERE/teacher.py" web-specs-train.jsonl web-gen-train.jsonl --mode generate $T --temperature 0.8
$PY -c "
import json
with open(\"web-text-train.jsonl\",\"w\") as f:
    for l in open(\"web-gen-train.jsonl\"):
        r=json.loads(l); t=r[\"teacher\"].get(\"text\")
        if isinstance(t,str) and len(t)>30: f.write(json.dumps({\"id\":r[\"id\"],\"text\":t,\"source\":\"synthetic-web\",\"hint\":r[\"hint\"]},ensure_ascii=False)+\"\n\")
"
$PY "$HERE/teacher.py" web-text-train.jsonl web-labelled-train.jsonl --mode label $T --max-chars 6000 --temperature 0
echo PIPELINE DONE
