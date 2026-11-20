#!/usr/bin/env bash
# 실제 경로 제한 시간 측정(v0.4.0): 브라우저 대신 curl → LOLYPOLY(운영과 같은 WSGI 설정) → 엔진 → Ollama.
# 질문 두 개: 정형 조회(모델 0회) / 생성(문서 질문). 생성 지연을 키우려고 엔진을 7B 로 하나 더 띄워 30초 경계를 넘긴다.
# 사용: LOLY=/path/LOLYPOLY LOLY_PY=/path/.venv-loly/bin/python KEY=<lolypoly 키> bash scripts/measure_timeouts.sh > out.tsv
set -u
ENGINE_DIR=$(cd "$(dirname "$0")/.." && pwd)
export PYTHONPATH=$ENGINE_DIR/src:$ENGINE_DIR
cd "$ENGINE_DIR"
OLLAMA_MODEL=qwen2.5:7b .venv/bin/uvicorn ragcore.api:app --host 127.0.0.1 --port 8092 >/tmp/engine7b.log 2>&1 &
E7=$!
cd "$LOLY"
common="LOLYPOLY_RAG_APP_KEY=$KEY DJANGO_DEBUG=True"
# 학교 PC 구성(deploy/windows/run_web.py): waitress channel_timeout=30
env LOLYPOLY_RAG_API_URL=http://127.0.0.1:8092 LOLYPOLY_RAG_APP_KEY=$KEY "$LOLY_PY" -c "
import os,sys; sys.path.insert(0,'.'); os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
from waitress import serve; from config.wsgi import application
serve(application, host='127.0.0.1', port=8011, threads=8, connection_limit=200, channel_timeout=30)" >/tmp/waitress.log 2>&1 &
W=$!
# Render/Docker 구성(Dockerfile): gunicorn --workers 2 --threads 4 --timeout 30
env LOLYPOLY_RAG_API_URL=http://127.0.0.1:8092 LOLYPOLY_RAG_APP_KEY=$KEY "${LOLY_PY%/python}/gunicorn" config.wsgi:application \
  --bind 127.0.0.1:8012 --workers 2 --threads 4 --timeout 30 >/tmp/gunicorn.log 2>&1 &
G=$!
sleep 25
ask() {  # $1=port $2=question → 상태코드 총초 Server-Timing(엔진 로그에서)
  jar=$(mktemp); curl -s -c "$jar" -o /dev/null "http://127.0.0.1:$1/meals/"
  tok=$(awk '/csrftoken/{print $7}' "$jar")
  out=$(curl -s -b "$jar" -o /tmp/ans.json -w "%{http_code}\t%{time_total}" -X POST "http://127.0.0.1:$1/assistant/ask/" \
    -H "Content-Type: application/json" -H "X-CSRFToken: $tok" -H "Referer: http://127.0.0.1:$1/meals/" \
    --max-time 120 -d "{\"question\": \"$2\"}")
  st=$(python3 -c "import json;print(json.load(open('/tmp/ans.json')).get('status') or json.load(open('/tmp/ans.json')).get('error'))" 2>/dev/null)
  echo -e "$1\t$2\t$out\t$st"
  rm -f "$jar"
}
echo -e "port\tquestion\thttp\tseconds\tresult"
for port in 8011 8012; do
  ask $port "11월 10일 점심 뭐야?"
  ask $port "학과수석 입학자 장학금 혜택과 조건을 자세히 알려줘"
  ask $port "국가장학금이랑 근로 장학금 차이를 설명해줘"
done
grep -h '"latency_ms"' /tmp/engine7b.log | tail -6
kill $E7 $W $G 2>/dev/null
