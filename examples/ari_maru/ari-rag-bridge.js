// MARU(Ari) → RAG 엔진 호출 예제. ari/app.js 에 바로 넣지 말고 후속 작업에서 검토 후 반영한다.
// 브라우저에는 모델 키·앱 키를 두지 않는다. 공개 MARU 범위에 묶인 중계 엔드포인트(/v1/public/chat)만 호출한다.
//
// 연결 방법(제안):
//   askAri(message) 안에서 기존 OpenAI/Ollama 시도보다 먼저
//     const rag = await askAriRag(message, buildAriContext());
//     if (rag.kind === 'rag') return rag.text;          // 근거 기반 답변(인용 포함)
//     if (rag.kind === 'abstain') return rag.text;      // 근거 부족/되묻기: 그대로 보여 준다
//   장애(kind === 'unavailable')일 때만 기존 fallbackAriReply()를 쓰되, 앞에 "로컬 안내(근거 검색 답변 아님)"를 붙인다.
//
// 기존 추천 순서 보존: context.ranking.topRoutes / topPlaces 의 ID 순서를 그대로 넘긴다(서버는 허용된 ID만 받고 순서를 바꾸지 않음).

const MARU_RAG_URL = (typeof window !== 'undefined' && window.MARU_RAG_URL) || 'http://127.0.0.1:8088/v1/public/chat';

export function toRagContext(ariContext) {
  return {
    course_id: ariContext?.selectedRoute?.id || undefined,
    place_id: ariContext?.selectedPlaceId || undefined,
    ranked_route_ids: (ariContext?.ranking?.topRoutes || []).map((r) => r.id),
    ranked_place_ids: (ariContext?.ranking?.topPlaces || []).map((p) => p.id),
  };
}

export function renderRagAnswer(data) {
  const lines = [data.answer];
  data.citations.forEach((c, i) => {
    const src = c.url ? ` ${c.url}` : '';
    const tag = c.source_type === 'synthetic' ? ' [합성 데이터]' : c.source_type === 'repository_data' ? ' [앱 데이터]' : '';
    lines.push(`[${i + 1}] ${c.title}${tag}${src}${c.note ? ` (${c.note})` : ''}`);
  });
  return lines.join('\n');
}

export async function askAriRag(message, ariContext, { fetchImpl = fetch, timeoutMs = 120000 } = {}) {
  const language = ariContext?.language === 'ko' ? 'ko' : (ariContext?.language ? 'en' : undefined);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetchImpl(MARU_RAG_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: String(message).slice(0, 500), language, context: toRagContext(ariContext) }),
      signal: ctrl.signal,
    });
    if (!res.ok) return { kind: 'unavailable', status: res.status };
    const data = await res.json();
    if (data.status === 'unavailable') return { kind: 'unavailable', data };
    const kind = data.status === 'answered' || data.status === 'partial' ? 'rag' : 'abstain';
    return { kind, data, text: renderRagAnswer(data) };
  } catch (error) {
    return { kind: 'unavailable', error: String(error) };
  } finally {
    clearTimeout(timer);
  }
}
