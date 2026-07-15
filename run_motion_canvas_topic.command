#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 RUN_ID TOPIC_REF 'TOPIC TITLE' [DURATION_SECONDS]" >&2
  exit 2
fi

RUN_ID="$1"
TOPIC_REF="$2"
TOPIC_TITLE="$3"
DURATION="${4:-120}"
FACTS="video_engine/topics/${TOPIC_REF}/facts.json"

if [[ ! -f "$FACTS" ]]; then
  python3 -m video_engine.cli prepare-topic "$TOPIC_REF"
fi

python3 template_lab/scripts/mav_generate.py \
  --run-id "$RUN_ID" \
  --facts "$FACTS" \
  --topic "$TOPIC_REF $TOPIC_TITLE" \
  --duration "$DURATION" \
  --animation-mode motion-canvas \
  --use-model --confirm-paid-api

python3 template_lab/scripts/mav_render.py \
  --run-id "$RUN_ID" \
  --animation-mode motion-canvas

echo "Completed: template_lab/runs/${RUN_ID}/motion_canvas/final.mp4"
