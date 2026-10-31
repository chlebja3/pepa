#!/bin/bash
# PEPA training pipeline: base corpus -> screener and verifier training -> exam.
# The shipped models come from: corpus exam screener-data extend train-pair (train and eval give the first
# versions, qwen-noise and scr-e5-web, which extend builds on).
#
# Usage: ./pipeline.sh STAGE [STAGE ...]   stages: corpus exam screener-data train eval extend train-pair
#
# Layout (all paths relative to $WORK; the scripts stay next to this file):
#   $WORK/raw/<owner>__<dataset>.jsonl   public English corpora from the Hugging Face Hub (see sample_english.py PLAN)
#   $WORK/bench/eval-labels.jsonl        frozen evaluation texts {id, text, source, hint[, teacher]} (not published)
#   $WORK/bench/                         working folder: every intermediate and training file is written here
#   $WORK/chat-mix.jsonl                 general Czech chat rows mixed into the verifier training
#   $WORK/runs/                          trained models and per-row exam results
#
# Teachers: an OpenAI-compatible chat completions server (e.g. vLLM) serving the main teacher (translates, labels,
# writes texts, explanations and advice) and, for the base corpus, a second model that labels blind:
#   TEACHER_BASE_URL (default http://localhost:8000/v1), TEACHER_MODEL (served model name, default "model")
#   SECOND_BASE_URL  (default $TEACHER_BASE_URL),        SECOND_MODEL  (default $TEACHER_MODEL)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
PY=${PY:-python}
TORCHRUN=${TORCHRUN:-torchrun}
WORK=${WORK:-$PWD/work}
export TEACHER_BASE_URL=${TEACHER_BASE_URL:-http://localhost:8000/v1}
export TEACHER_MODEL=${TEACHER_MODEL:-model}
SECOND_BASE_URL=${SECOND_BASE_URL:-$TEACHER_BASE_URL}
SECOND_MODEL=${SECOND_MODEL:-$TEACHER_MODEL}
T="--url $TEACHER_BASE_URL/chat/completions --model $TEACHER_MODEL --workers 48"
T2="--url $SECOND_BASE_URL/chat/completions --model $SECOND_MODEL --workers 48"
mkdir -p "$WORK/bench" "$WORK/runs"
cd "$WORK/bench"

# keep rows whose teacher reply has a usable "text" (generate mode) as {id, text, source, hint}
texts() {  # IN OUT SOURCE MIN_CHARS
  $PY -c "
import json, sys
src, dst, source, min_chars = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
with open(dst, 'w') as f:
    for l in open(src):
        r = json.loads(l); t = r['teacher'].get('text')
        if isinstance(t, str) and len(t) > min_chars:
            f.write(json.dumps({'id': r['id'], 'text': t, 'source': source, 'hint': r['hint']}, ensure_ascii=False) + '\n')
" "$@"
}

# explanation for every row, advice for scam rows (as in frag-pipeline.sh)
explain_advise() {  # IN PREFIX -> PREFIX-final.jsonl
  $PY "$HERE/teacher.py" "$1" "$2-explained.jsonl" --mode explain $T
  grep '"verdict": "scam"' "$2-explained.jsonl" > "$2-scam.jsonl" || true
  $PY "$HERE/teacher.py" "$2-scam.jsonl" "$2-scam-rada.jsonl" --mode advise $T
  { grep -v '"verdict": "scam"' "$2-explained.jsonl"; cat "$2-scam-rada.jsonl"; } > "$2-final.jsonl"
}

stage_corpus() {
  # 1. English public corpora: balanced, deduplicated sample; the main teacher labels and translates to Czech,
  #    the second model labels the English original blind
  $PY "$HERE/sample_english.py" ../raw english.jsonl
  $PY "$HERE/teacher.py" english.jsonl english-teacher.jsonl --mode translate $T
  $PY "$HERE/teacher.py" english.jsonl english-second.jsonl --mode label $T2
  # 2. Czech web text (FineWeb-2 ces) in extension-sized blocks, labelled by the teacher (ordinary material)
  $PY "$HERE/fetch_fineweb.py" fineweb.jsonl
  $PY "$HERE/teacher.py" fineweb.jsonl fineweb-labelled.jsonl --mode label $T
  # 3. synthetic Czech messages for local scam schemes and look-alike legitimate ones, labelled blind
  $PY "$HERE/synthetic_specs.py" synth-specs.jsonl --seed 1
  $PY "$HERE/teacher.py" synth-specs.jsonl synth-gen.jsonl --mode generate $T --temperature 0.8
  texts synth-gen.jsonl synth-text.jsonl synthetic 15
  $PY "$HERE/teacher.py" synth-text.jsonl synth-labelled.jsonl --mode label $T2 --temperature 0
  # 4. keep agreeing teachers, cap sources, drop anything overlapping the frozen exam
  $PY "$HERE/merge_teachers.py" english-teacher.jsonl english-second.jsonl train-agreed.jsonl \
    --fineweb fineweb-labelled.jsonl --synthetic synth-labelled.jsonl --exclude eval-labels.jsonl
  # 5. one-sentence Czech reason for every row, advice for scams -> train-explained.jsonl
  explain_advise train-agreed.jsonl train
  mv train-final.jsonl train-explained.jsonl
  # 6. general Czech chat pairs written by the teacher from FineWeb texts -> ../chat-mix.jsonl {messages}
  $PY -c "
import json, random
rows = [json.loads(l) for l in open('fineweb.jsonl')]
random.Random(7).shuffle(rows)
with open('chat-src.jsonl', 'w') as f:
    for r in rows[:3000]:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
"
  $PY "$HERE/teacher.py" chat-src.jsonl chat-gen.jsonl --mode chat $T
  $PY -c "
import json
with open('../chat-mix.jsonl', 'w') as f:
    for l in open('chat-gen.jsonl'):
        t = json.loads(l)['teacher']
        if isinstance(t.get('question'), str) and isinstance(t.get('answer'), str):
            f.write(json.dumps({'messages': [{'role': 'user', 'content': t['question']},
                                             {'role': 'assistant', 'content': t['answer']}]}, ensure_ascii=False) + '\n')
"
}

stage_exam() {
  # dev half (settings and thresholds) and test half (reported once) of the frozen exam -> devtest/
  $PY "$HERE/split_exam.py" eval-labels.jsonl devtest
}

stage_screener_data() {
  # synthetic everyday e-mails (held-out eval + train) and web pages / SMS, generated and labelled blind
  $PY "$HERE/synthetic_specs.py" mail-specs-eval.jsonl --emails --seed 2
  $PY "$HERE/synthetic_specs.py" mail-specs-train.jsonl --emails --seed 3
  $PY "$HERE/synthetic_specs.py" web-specs-train.jsonl --web --seed 4
  "$HERE/mail-pipeline.sh"
  "$HERE/web-pipeline.sh"
  # train-web.jsonl = train-explained.jsonl + agreeing e-mails (+ chunks of legitimate ones) + web pages and SMS
  $PY "$HERE/add_synthetic_mail.py" train-explained.jsonl mail-labelled-train.jsonl train-mail.jsonl
  $PY "$HERE/add_synthetic_mail.py" train-mail.jsonl web-labelled-train.jsonl train-web.jsonl
  $PY "$HERE/add_synthetic_mail.py" - mail-labelled-eval.jsonl mail-eval.jsonl
}

stage_train() {
  # verifier qwen-noise: Qwen3.5-2B LoRA on 4 GPUs (about 2 h)
  $TORCHRUN --nproc-per-node 4 "$HERE/train_verifier.py" train-explained.jsonl ../runs/qwen-noise \
    --model Qwen/Qwen3.5-2B --rank 16 --batch 4 --accum 1 --noise 0.3 --mix ../chat-mix.jsonl
  # screener scr-e5-web: multilingual-e5-small on 1 GPU (about 5 min); also scores devtest/ into ../runs/screen-{dev,test}
  $PY "$HERE/train_screener.py" train-web.jsonl ../runs/scr-e5-web \
    --model intfloat/multilingual-e5-small --scam-weight 3 --lr 1e-4
}

exam_verifier() {  # NAME
  for half in dev test; do
    $PY "$HERE/bench_confidence_hf.py" ../runs/$half-1 --bench devtest/$half.jsonl --models Qwen/Qwen3.5-2B=../runs/$1/adapter
  done
}

stage_eval() {
  exam_verifier qwen-noise
  $PY "$HERE/tradeoff.py" ../runs/dev-1 ../runs/test-1 --recall 0.8 0.9 0.95
  $PY "$HERE/metrics.py" ../runs/test-1/*.jsonl
  # screener: route threshold (95 % dev recall) and alarm threshold (at most 1 % of dev ordinary rows above it)
  $PY "$HERE/tradeoff.py" ../runs/screen-dev ../runs/screen-test --recall 0.9 0.95
  $PY "$HERE/thr.py" scr-e5-web
  # held-out synthetic e-mails scored chunk by chunk as in the extension; ROUTE and ALARM come from thr.py
  if [ -n "$ROUTE" ] && [ -n "$ALARM" ]; then
    $PY "$HERE/score_mail.py" mail-eval.jsonl ../runs/scr-e5-web/model:$ROUTE:$ALARM
  fi
}

# ---- EXTENSION: the shipped models, verifier qwen-pair and screener scr-e5-fp ----
# qwen-pair:  train-explained-gram-mami-pair.jsonl = train-explained.jsonl, proofread, "new number" relabel,
#             + contrastive pairs (31 013 rows); training flags are the same as for qwen-noise.
# scr-e5-fp:  train-web-fp.jsonl = train-web.jsonl + short fragments and contrastive pairs (46 338 rows).
stage_extend() {
  # short fragments and two rounds of contrastive pairs (generated, labelled blind, explained, advised, proofread)
  "$HERE/frag-pipeline.sh"
  "$HERE/pair-pipeline.sh"
  "$HERE/pair2-pipeline.sh"
  cat pair-final.jsonl pair2-final.jsonl > pairs-final.jsonl
  # grammar: gram_gold.py checks a proofreading model on hand-checked sentences, e.g.
  #   python gram_gold.py $TEACHER_BASE_URL/chat/completions $TEACHER_MODEL
  # then proofread.py fixes the Czech of every reason and advice sentence (small edits only)
  $PY "$HERE/proofread.py" train-explained.jsonl train-explained-gram.jsonl gram-fixes.jsonl $PROOFREAD_FLAGS
  # verifier: "Ahoj mami, mám nové číslo" openers are scams by decision (relabel from "insufficient"), pairs on top
  $PY "$HERE/relabel_newnumber.py" train-explained-gram.jsonl train-explained-gram-mami.jsonl
  $PY "$HERE/merge_pairs.py" train-explained-gram-mami.jsonl pairs-final.jsonl train-explained-gram-mami-pair.jsonl
  # screener: the fragments too (proofread like the rest), and the pairs
  cat train-explained.jsonl frag-final.jsonl > train-base-frag.jsonl
  $PY "$HERE/proofread.py" train-base-frag.jsonl train-explained-frag-gram.jsonl gram-fixes-frag.jsonl $PROOFREAD_FLAGS
  $PY "$HERE/merge_pairs.py" train-explained-frag-gram.jsonl pairs-final.jsonl train-explained-frag-gram-pair.jsonl
  $PY "$HERE/screener_extra.py" train-web.jsonl train-explained.jsonl train-explained-frag-gram-pair.jsonl train-web-fp.jsonl
}

stage_train_pair() {
  # verifier qwen-pair: Qwen3.5-2B LoRA on 4 GPUs (about 2 h)
  $TORCHRUN --nproc-per-node 4 "$HERE/train_verifier.py" train-explained-gram-mami-pair.jsonl ../runs/qwen-pair \
    --model Qwen/Qwen3.5-2B --rank 16 --batch 4 --accum 1 --noise 0.3 --mix ../chat-mix.jsonl
  exam_verifier qwen-pair
  # screener scr-e5-fp: multilingual-e5-small on 1 GPU
  $PY "$HERE/train_screener.py" train-web-fp.jsonl ../runs/scr-e5-fp \
    --model intfloat/multilingual-e5-small --scam-weight 3 --lr 1e-4
  # thresholds from the dev half only: verifier orange at 90 % and red at 80 % of dev scams behind the screener
  # (WARN -4.0 and DANGER -1.375 in verifier.py), screener route at 97 % dev recall, alarm at 1 % of ordinary
  $PY "$HERE/tradeoff.py" ../runs/dev-1 ../runs/test-1 --recall 0.8 0.9 0.95
  RECALL=0.97 $PY "$HERE/thr.py" scr-e5-fp
}

[ $# -gt 0 ] || { sed -n '2,4p' "$0"; exit 1; }
for stage in "$@"; do
  "stage_${stage//-/_}"
done
