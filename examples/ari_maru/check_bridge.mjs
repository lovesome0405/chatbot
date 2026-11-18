// node examples/ari_maru/check_bridge.mjs  (로컬 API 실행 중이어야 함)
// Ari buildAriContext() 모양의 객체를 흉내 내 브리지가 순서·범위를 지키는지 확인한다.
import { askAriRag } from './ari-rag-bridge.js';

const ariContext = {
  language: 'ko',
  selectedRoute: { id: 'palace-history-course' },
  ranking: { topRoutes: [{ id: 'night-traditional-culture-course' }, { id: 'palace-history-course' }], topPlaces: [] },
};
const cases = [
  ['추천 순위 알려줘', undefined],
  ['오늘 점심 뭐야?', undefined],
  ['여기는 어떤 곳이야?', 'jongmyo-shrine'],   // 장소 카드에서 종묘를 고른 뒤의 후속 질문
  ['여기는 어떤 곳이야?', undefined],           // 장소를 넘기지 않으면 되묻기
];
for (const [q, placeId] of cases) {
  const r = await askAriRag(q, ariContext, { placeId });
  console.log(JSON.stringify({ q, placeId, kind: r.kind, status: r.data?.status, sources: r.data?.citations?.map((c) => c.source_id) }));
}
