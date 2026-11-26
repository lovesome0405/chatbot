"""첫 질문 지연 측정: 운영 엔진(127.0.0.1:8088) /v1/chat 에 같은 문서 질문을 반복.
앱 키는 .env 에서 읽기만 하고 출력·저장하지 않는다.
사용: python coldstart.py "<질문>" [--stop] [--max 120]
"""
import json, subprocess, sys, time
import httpx

ENV = r"D:\lolypoly\rag\chatbot\.env"
OLLAMA = r"D:\lolypoly\rag\ollama\ollama.exe"
q = sys.argv[1]
stop = "--stop" in sys.argv
maxs = float(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 120

key = None
for line in open(ENV, encoding="utf-8-sig"):
    if line.strip().startswith("RAG_APP_KEYS="):
        for pair in line.split("=", 1)[1].strip().strip('"').split(","):
            proj, _, k = pair.partition(":")
            if proj.strip() == "lolypoly":
                key = k.strip()
assert key, "lolypoly key not found"

def loaded():
    try:
        ps = httpx.get("http://127.0.0.1:11434/api/ps", timeout=2).json()
        return ",".join(m["name"] for m in ps.get("models", [])) or "-"
    except Exception as e:
        return f"err:{e}"

if "--pre" in sys.argv:   # 엔진의 '적재됨' 캐시(30초)가 지나도록 조용히 기다림
    time.sleep(float(sys.argv[sys.argv.index("--pre") + 1]))
if stop:
    subprocess.run([OLLAMA, "stop", "qwen2.5:1.5b"], check=False)
    time.sleep(1)
t0 = time.perf_counter()
print(f"start {time.strftime('%H:%M:%S')} loaded={loaded()} stop={stop}")
normal = 0
while time.perf_counter() - t0 < maxs:
    ts = time.perf_counter() - t0
    r = httpx.post("http://127.0.0.1:8088/v1/chat", json={"question": q, "language": "ko"},
                   headers={"Authorization": f"Bearer {key}"}, timeout=60)
    d = r.json()
    lat = time.perf_counter() - t0 - ts
    timing = r.headers.get("Server-Timing", "")
    gen = [p for p in timing.split(",") if "generation" in p]
    print(json.dumps({"t_send": round(ts, 1), "latency_s": round(lat, 2), "http": r.status_code,
                      "status": d.get("status"), "route": d.get("route"), "citations": len(d.get("citations") or []),
                      "gen": gen[0].strip() if gen else "", "loaded_after": loaded(),
                      "answer": (d.get("answer") or "")[:90]}, ensure_ascii=False))
    gen_ms = float(gen[0].split("dur=")[1]) if gen and "dur=" in gen[0] else 0
    normal = normal + 1 if gen_ms > 0 and "준비" not in (d.get("answer") or "") else 0
    if normal >= 3:
        break
    time.sleep(3)
