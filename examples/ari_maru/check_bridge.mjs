// node examples/ari_maru/check_bridge.mjs  (로컬 API 실행 중이어야 함)
// Ari buildAriContext() 모양의 객체를 흉내 내 브리지가 순서·범위를 지키는지 확인한다.
import { askAriRag } from './ari-rag-bridge.js';

const ariContext = {
  language: 'ko',
  selectedRoute: { id: 'palace-history-course' },
  ranking: { topRoutes: [{ id: 'night-traditional-culture-course' }, { id: 'palace-history-course' }], topPlaces: [] },
};
for (const q of ['추천 순위 알려줘', '오늘 점심 뭐야?']) {
  const r = await askAriRag(q, ariContext);
  console.log(JSON.stringify({ q, kind: r.kind, status: r.data?.status, sources: r.data?.citations?.map((c) => c.source_id) }));
}
