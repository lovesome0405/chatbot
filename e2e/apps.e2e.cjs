// 두 실제 앱 화면 E2E (v0.4.0). 정상 경로는 브라우저 → 실제 앱 → 실제 엔진(e5 + Ollama) → PostgreSQL/pgvector.
// 장애 분기는 Playwright 네트워크 제어(page.route)로 모의한다(실제 장애 시험과 구분해 기록).
//
// 준비(README "앱 화면 E2E" 참고):
//   엔진 8088(일반, 기준 시각 덮어쓰기 거부) · 8089(평가 전용, RAG_FIXED_NOW=2026-09-15T12:00) · 8090(평가 전용, 2026-11-01T12:00)
//   LOLYPOLY  http://127.0.0.1:8000  (LOLYPOLY_RAG_API_URL=http://127.0.0.1:8088, LOLYPOLY_RAG_APP_KEY=<lolypoly 키>)
//   MARU(ari) http://127.0.0.1:8765  (정적 서버. rag-config.json 은 이 스크립트가 가로채 endpoint 를 넣는다)
// 실행: node e2e/apps.e2e.cjs [--only lolypoly|maru]   결과: reports/v0.4.0/e2e/results.json + 화면 캡처
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'reports', 'v0.4.0', 'e2e');
const LOLY = process.env.LOLY_URL || 'http://127.0.0.1:8000';
const MARU = process.env.MARU_URL || 'http://127.0.0.1:8765';
const ENGINE = process.env.ENGINE_URL || 'http://127.0.0.1:8088';
const ENGINE_EVAL_IN = 'http://127.0.0.1:8089';
const ENGINE_EVAL_AFTER = 'http://127.0.0.1:8090';
const only = process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1] : '';
const results = [];
fs.mkdirSync(OUT, { recursive: true });

function record(app, name, ok, detail = {}) {
  results.push({ app, name, ok: Boolean(ok), ...detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} [${app}] ${name}${detail.note ? ' — ' + detail.note : ''}`);
}

async function noHorizontalScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}

// ── LOLYPOLY ────────────────────────────────────────────────
async function lolypoly(browser) {
  const ctx = await browser.newContext({ ...devices['iPhone 13'], locale: 'ko-KR' });
  // 첫 방문 업데이트 안내 창·설치 안내는 이 시험의 대상이 아니라 본 것으로 표시해 둔다
  await ctx.addInitScript(() => {
    localStorage.setItem('lolypoly-seen-version', '0.4.1-beta');
    localStorage.setItem('lolypoly-install-dismissed-at', String(Date.now()));
  });
  const page = await ctx.newPage();
  const asks = [];
  page.on('request', (r) => { if (r.url().includes('/assistant/ask/')) asks.push({ t: Date.now(), body: r.postData() }); });
  await page.goto(`${LOLY}/meals/`);
  const box = page.locator('[data-assistant]');
  record('lolypoly', '식단 화면에 안내 칸 표시', await box.isVisible());
  const log = page.locator('[data-assistant-log] > li');

  async function ask(q, { expectCount } = {}) {
    const before = await log.count();
    await page.fill('[data-assistant-input]', q);
    const t0 = Date.now();
    await page.click('[data-assistant-send]');
    await page.waitForFunction((n) => document.querySelectorAll('[data-assistant-log] > li').length >= n,
      expectCount ?? before + 2, { timeout: 90000 });
    const last = log.last();
    return { ms: Date.now() - t0, cls: await last.getAttribute('class'), text: await last.innerText(),
      links: await last.locator('a').evaluateAll((as) => as.map((a) => ({ href: a.href, target: a.target, rel: a.rel }))) };
  }

  // 1) 오늘(실제 날짜, 자료 없음) 점심 — 예시 버튼
  const t0 = Date.now();
  await page.click('[data-assistant-example] >> nth=0');
  await page.waitForFunction(() => document.querySelectorAll('[data-assistant-log] > li').length >= 2, null, { timeout: 90000 });
  const today = { ms: Date.now() - t0, cls: await log.last().getAttribute('class'), text: await log.last().innerText(),
    links: await log.last().locator('a').evaluateAll((as) => as.map((a) => a.href)) };
  record('lolypoly', '자료 없는 날: 마지막 확인 시각·공식 식단 경로', today.cls.includes('is-insufficient_evidence')
    && today.text.includes('마지막 확인') && today.links.some((h) => h.includes('menu=4819')), { answer: today.text, ms: today.ms });
  await page.screenshot({ path: path.join(OUT, 'lolypoly-missing-day.png'), fullPage: false });

  // 2) 자료가 있는 날
  const day = await ask('11월 10일 점심 뭐야?');
  record('lolypoly', '자료 있는 식단(11-10 중식) 정형 조회', day.cls.includes('is-answered') && day.text.includes('상하이파스타')
    && day.text.includes('앱 수집 자료'), { answer: day.text, ms: day.ms });

  // 3) 장학표 정확한 행
  const sch = await ask('성적우수장학금은 신입생도 1학기에 받을 수 있어?');
  record('lolypoly', '장학표 행 3(대상·학기·금액 같은 행)', sch.text.startsWith('안내') || sch.text.includes('아니요')
    ? sch.text.includes('아니요') && sch.text.includes('행 3') && sch.text.includes('1개학기 교육비 전액면제') && sch.text.includes('공식 원문')
    : false, { answer: sch.text, ms: sch.ms });
  const official = sch.links.find((l) => l.href.includes('menu=4799'));
  record('lolypoly', '출처 링크: 공식 장학 페이지, 새 창·noopener', official && official.target === '_blank' && official.rel.includes('noopener'),
    { link: official });
  if (official) {
    const [popup] = await Promise.all([ctx.waitForEvent('page', { timeout: 15000 }).catch(() => null),
      log.last().locator('a[href*="menu=4799"]').first().click()]);
    record('lolypoly', '출처 클릭 시 새 탭 열림', Boolean(popup), { url: popup ? popup.url() : null });
    if (popup) await popup.close();
  }

  // 4) 실제 생성 경로(문서 질문)
  const gen = await ask('학과수석 입학자 장학금 혜택이 뭐야?');
  record('lolypoly', '문서 질문 실제 임베딩·생성(qwen2.5:3b)', gen.cls.includes('is-answered') && gen.text.includes('[1]'),
    { answer: gen.text, ms: gen.ms });

  // 5) 되묻기 → 같은 입력칸으로 답
  const clar = await ask('11월 10일 메뉴 뭐야?');
  const clarOk = clar.cls.includes('is-clarification_needed');
  const followed = clarOk ? await ask('점심') : null;
  record('lolypoly', '되묻기 후 입력칸으로 답하기', clarOk && followed && followed.text.includes('상하이파스타'),
    { first: clar.text, second: followed && followed.text, sent: asks.slice(-1)[0]?.body });

  // 6) 중복 전송 방지: 보내는 중 다시 눌러도 요청 1건
  const n0 = asks.length;
  await page.fill('[data-assistant-input]', '학과수석 입학자는 몇 년 동안 면제야?');
  await page.click('[data-assistant-send]');
  await page.click('[data-assistant-send]', { force: true, timeout: 2000 }).catch(() => {});
  await page.press('[data-assistant-input]', 'Enter').catch(() => {});
  await page.waitForFunction(() => document.querySelector('[data-assistant]').getAttribute('aria-busy') === 'false', null, { timeout: 90000 });
  record('lolypoly', '전송 중 중복 전송 방지', asks.length - n0 === 1, { requests: asks.length - n0 });

  // 7) 장애(모의): 연결 끊김 → 입력 복구·다시 시도 → 실제 응답 (화면 기록 상한 12개 때문에 먼저 '대화 지우기')
  await page.click('[data-assistant-clear]');
  record('lolypoly', '대화 지우기', (await log.count()) === 0);
  const before = await log.count();
  await page.route('**/assistant/ask/', (route) => route.abort('connectionreset'));
  await page.fill('[data-assistant-input]', '11월 11일 저녁 뭐야?');
  await page.click('[data-assistant-send]');
  await page.waitForSelector('.assistant__status.is-error');
  const failState = { status: await page.innerText('[data-assistant-status]'), input: await page.inputValue('[data-assistant-input]'),
    retry: await page.isVisible('[data-assistant-retry]'), logCount: await log.count() };
  await page.unroute('**/assistant/ask/');
  await page.click('[data-assistant-retry]');
  await page.waitForFunction((n) => document.querySelectorAll('[data-assistant-log] > li').length >= n + 2, before, { timeout: 90000 });
  record('lolypoly', '[모의] 연결 끊김 → 입력 복구, 기록에 오류 없음, 다시 시도 성공', failState.input === '11월 11일 저녁 뭐야?'
    && failState.retry && failState.logCount === before && (await log.last().innerText()).includes('석식'), failState);

  for (const [code, kind] of [[429, '많아요'], [504, '오래']]) {
    await page.route('**/assistant/ask/', (route) => route.fulfill({ status: code, contentType: 'application/json',
      body: JSON.stringify({ error: code === 429 ? 'rate_limited' : 'timeout', message: code === 429 ? '질문이 너무 많아요. 잠시 뒤 다시 시도해 주세요.' : '답변이 너무 오래 걸려서 멈췄어요. 잠시 뒤 다시 시도해 주세요.' }) }));
    await page.fill('[data-assistant-input]', '오늘 저녁 뭐야?');
    await page.click('[data-assistant-send]');
    await page.waitForSelector('.assistant__status.is-error');
    const s = await page.innerText('[data-assistant-status]');
    record('lolypoly', `[모의] HTTP ${code} 안내와 입력 복구`, s.includes(kind) && (await page.inputValue('[data-assistant-input]')) === '오늘 저녁 뭐야?', { status: s });
    await page.unroute('**/assistant/ask/');
  }

  record('lolypoly', '모바일(iPhone 13) 가로 넘침 없음', await noHorizontalScroll(page));
  await box.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, 'lolypoly-assistant-mobile.png'), fullPage: true });
  await ctx.close();
}

// ── MARU(ari) ───────────────────────────────────────────────
// 아리 기록은 14개 상한·인사말이 있어 개수 대신 저장된 마지막 답의 시각으로 새 답을 기다린다
const lastAt = (page) => page.evaluate(() => {
  const items = JSON.parse(localStorage.getItem('hanroute.mobile.ariMessages') || '[]');
  return items.length ? items[items.length - 1].createdAt : 0;
});
const waitReply = (page, mark) => page.waitForFunction((m) => {
  const items = JSON.parse(localStorage.getItem('hanroute.mobile.ariMessages') || '[]');
  const last = items[items.length - 1];
  return last && last.role === 'assistant' && last.createdAt > m
    && document.querySelector('[data-ari-panel]').getAttribute('aria-busy') !== 'true';
}, mark, { timeout: 90000 });
async function maru(browser) {
  const ctx = await browser.newContext({ ...devices['Pixel 7'], locale: 'en-US' });
  let endpoint = `${ENGINE}/v1/public/chat`;
  await ctx.route('**/rag-config.json', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ endpoint }) }));
  await ctx.addInitScript(() => {
    if (!sessionStorage.getItem('e2e-init')) {
      localStorage.clear();
      localStorage.setItem('hanroute.mobile.language', 'en');
      sessionStorage.setItem('e2e-init', '1');
    }
  });
  const page = await ctx.newPage();
  const sent = [];
  page.on('request', (r) => { if (r.url().includes('/v1/public/chat')) sent.push(JSON.parse(r.postData() || '{}')); });
  const msgs = page.locator('[data-ari-messages] .ari-message');

  async function askAri(q) {
    const mark = await lastAt(page);
    await page.fill('[data-ari-input]', q);
    const t0 = Date.now();
    await page.click('[data-ari-send]');
    await waitReply(page, mark);
    const last = msgs.last();
    return { ms: Date.now() - t0, cls: await last.getAttribute('class'), text: await last.innerText(), body: sent[sent.length - 1],
      links: await last.locator('a').evaluateAll((as) => as.map((a) => ({ href: a.href, target: a.target, rel: a.rel }))) };
  }

  await page.goto(`${MARU}/route-detail.html?id=palace-history-course`);
  await page.waitForSelector('[data-ari-place]');
  const placeIds = await page.locator('[data-ari-place]').evaluateAll((bs) => bs.map((b) => b.dataset.ariPlace));
  const [A, B] = [placeIds.find((id) => id === 'gyeongbokgung-palace') || placeIds[0], placeIds.find((id) => id === 'national-folk-museum') || placeIds[1]];
  await page.click(`[data-ari-place="${A}"]`);
  await page.waitForSelector('[data-ari-panel][aria-hidden="false"]');
  await page.click('[data-ari-close]');
  await page.click(`[data-ari-place="${B}"]`);   // A → B 전환
  const chip = await page.innerText('[data-ari-place-chip]');
  const r1 = await askAri('What is this place?');
  record('maru', `장소 A(${A})→B(${B}) 전환 후 "What is this place?" — B만 전달·B 출처`, r1.body.context.place_id === B
    && r1.body.context.course_id === 'palace-history-course' && r1.body.language === 'en'
    && r1.text.includes('App data') && !/[가-힣]{6,}/.test(r1.text.split('\n').find((l) => l.trim() && !l.startsWith('Ari')) || ''),
    { chip, answer: r1.text, context: r1.body.context, ms: r1.ms });
  await page.screenshot({ path: path.join(OUT, 'maru-place-answer-mobile.png') });
  const src = r1.links[0];
  record('maru', '출처 링크(앱 데이터)는 새 창·noopener', src && src.target === '_blank' && src.rel.includes('noopener'), { link: src });

  // 선택 해제 → 같은 질문은 장소 없이 → 되묻기
  await page.click('[data-ari-place-clear]');
  const r2 = await askAri('What is this place?');
  record('maru', '선택 해제 뒤 오래된 장소 ID 없음 → clarification_needed 그대로 표시', !('place_id' in r2.body.context)
    && r2.cls.includes('is-clarification_needed'), { answer: r2.text, context: r2.body.context });

  // 코스 순서
  const r3 = await askAri('What is the order of this course?');
  record('maru', '코스 질문: 앱 데이터의 방문 순서', r3.text.includes('→') && r3.body.context.course_id === 'palace-history-course'
    && Array.isArray(r3.body.context.ranked_route_ids) && r3.body.context.ranked_route_ids.length > 0,
    { answer: r3.text, context: r3.body.context, ms: r3.ms });

  // 중복 전송 방지(엔터 연타 + 빠른 질문)
  const n0 = sent.length;
  await page.fill('[data-ari-input]', 'Tell me about Jongmyo Shrine');
  await page.press('[data-ari-input]', 'Enter');
  await page.press('[data-ari-input]', 'Enter').catch(() => {});
  await page.click('[data-ari-quick] >> nth=0', { timeout: 1500 }).catch(() => {});
  await page.waitForFunction(() => document.querySelector('[data-ari-panel]').getAttribute('aria-busy') === 'false', null, { timeout: 90000 });
  const jm = await msgs.last().innerText();
  record('maru', '전송 중 중복 전송 방지', sent.length - n0 === 1, { requests: sent.length - n0, answer: jm });
  record('maru', 'M14 화면 확인: 종묘 답에 잘못된 구 이름 없음', !/Jungmu/i.test(jm), { answer: jm });

  // 페이지 전환 → 장소 상태 초기화
  const geo = await page.evaluate(() => { const r = (q) => { const e = document.querySelector(q); const b = e.getBoundingClientRect(); return [Math.round(b.top), Math.round(b.bottom)]; };
    return { vh: innerHeight, panel: r('[data-ari-panel]'), close: r('[data-ari-close]'), msgs: r('[data-ari-messages]') }; });
  record('maru', '대화가 길어도 아리 패널 닫기 버튼이 화면 안', geo.close[0] >= 0 && geo.close[1] <= geo.vh, geo);
  await page.screenshot({ path: path.join(OUT, 'maru-panel-long.png') });
  await page.click('[data-ari-close]');
  const closed = await page.evaluate(() => !document.querySelector('[data-ari-root]').classList.contains('is-open'));
  record('maru', '닫기 버튼으로 패널 닫힘', closed);
  if (!closed) await page.evaluate(() => closeAriChat());
  await page.click(`[data-ari-place="${B}"]`);
  await page.goto(`${MARU}/index.html`);
  await page.click('[data-ari-open]');
  const r4 = await askAri('What is this place?');
  record('maru', '페이지 전환 뒤 이전 장소·코스 ID 없음', !('place_id' in r4.body.context) && !('course_id' in r4.body.context), { context: r4.body.context });

  // 장애(모의): 연결 끊김 → 상태 줄 오류 + 로컬 안내 표시 + 입력 복구 → 다시 시도
  await page.route('**/v1/public/chat', (route) => route.abort('connectionrefused'));
  const n1 = JSON.parse(await page.evaluate(() => localStorage.getItem('hanroute.mobile.ariMessages') || '[]')).length;
  await page.fill('[data-ari-input]', 'Tell me about Changdeokgung Palace');
  await page.click('[data-ari-send]');
  await page.waitForSelector('.ari-status.is-error');
  const local = await msgs.last().innerText();
  const st = { status: await page.innerText('[data-ari-status]'), input: await page.inputValue('[data-ari-input]'),
    retry: await page.isVisible('[data-ari-retry]'),
    added: Math.min(2, JSON.parse(await page.evaluate(() => localStorage.getItem('hanroute.mobile.ariMessages') || '[]')).length - n1 + (n1 >= 13 ? 2 : 0)) };
  record('maru', '[모의] 연결 끊김: 오류는 상태 줄, 로컬 안내 라벨, 입력 복구', st.retry && st.input.includes('Changdeokgung')
    && local.includes('Local guide') && !local.includes("Couldn't reach") && st.added === 2, { ...st, local: local.slice(0, 160) });
  await page.unroute('**/v1/public/chat');
  const m2mark = await lastAt(page);
  await page.click('[data-ari-retry]');
  await waitReply(page, m2mark);
  const retried = await msgs.last().getAttribute('class');
  record('maru', '[모의 해제] 다시 시도 → 실제 엔진 응답', retried.includes('is-rag'), { cls: retried });

  for (const [mock, label] of [[{ status: 429, body: '{"detail":"too many requests"}' }, 'Too many'],
    [{ status: 200, body: JSON.stringify({ status: 'unavailable', route: 'none', answer: 'A temporary error', citations: [], as_of: '', request_id: 'x' }) }, 'problem']]) {
    await page.route('**/v1/public/chat', (route) => route.fulfill({ status: mock.status, contentType: 'application/json', body: mock.body }));
    await page.fill('[data-ari-input]', 'Is Deoksugung open now?');
    await page.click('[data-ari-send]');
    await page.waitForSelector('.ari-status.is-error');
    const s = await page.innerText('[data-ari-status]');
    record('maru', `[모의] ${mock.status === 429 ? 'HTTP 429' : 'status=unavailable'} → 로컬 안내 라벨`, s.includes(label)
      && (await msgs.last().innerText()).includes('Local guide'), { status: s });
    await page.unroute('**/v1/public/chat');
  }

  // 월대 출입 제한: 평가 서버(고정 시각)
  for (const [ep, label, check] of [[ENGINE_EVAL_IN, '2026-09-15(기간 안)', (t) => /(restricted|cannot go up|can't go up)/i.test(t) && t.includes('Official source') && t.includes('2026-10-31')],
    [ENGINE_EVAL_AFTER, '2026-11-01(종료 후)', (t) => !/you can't go up now/i.test(t) && /(couldn't|can't confirm|ended|period)/i.test(t)]]) {
    endpoint = `${ep}/v1/public/chat`;
    const p2 = await ctx.newPage();
    await p2.goto(`${MARU}/index.html`);
    await p2.click('[data-ari-open]');
    const m2 = p2.locator('[data-ari-messages] .ari-message');
    const mk = await lastAt(p2);
    await p2.fill('[data-ari-input]', 'Can I go up to the Geunjeongjeon terrace now?');
    await p2.click('[data-ari-send]');
    await waitReply(p2, mk);
    const t = await m2.last().innerText();
    record('maru', `월대 출입 제한 ${label} — 평가 서버 고정 시각`, check(t), { answer: t });
    if (label.startsWith('2026-09')) await p2.screenshot({ path: path.join(OUT, 'maru-woldae-restricted.png') });
    await p2.close();
  }
  endpoint = `${ENGINE}/v1/public/chat`;

  // 일반 서버는 기준 시각 덮어쓰기를 거부
  const override = await page.evaluate(async (url) => (await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: 'Can I go up to the Geunjeongjeon terrace now?', reference_time: '2026-09-15T12:00:00' }) })).status,
  `${ENGINE}/v1/public/chat`);
  record('maru', '일반 서버: reference_time 요청 거부(400)', override === 400, { status: override });

  // RAG 끄기 → 기존 흐름(엔진 호출 없음)
  endpoint = 'off';
  const p3 = await ctx.newPage();
  const sentOff = [];
  p3.on('request', (r) => { if (r.url().includes('/v1/public/chat')) sentOff.push(r.url()); });
  await p3.goto(`${MARU}/index.html`);
  await p3.click('[data-ari-open]');
  const m3 = p3.locator('[data-ari-messages] .ari-message');
  const k3 = await lastAt(p3);
  await p3.fill('[data-ari-input]', 'Recommend a palace course');
  await p3.click('[data-ari-send]');
  await waitReply(p3, k3);
  const offText = await m3.last().innerText();
  record('maru', 'RAG 설정 off → 기존 아리 흐름(엔진 호출 0, 로컬 라벨 없음)', sentOff.length === 0 && !offText.includes('Local guide'),
    { answer: offText.slice(0, 160) });
  await p3.close();

  record('maru', '모바일(Pixel 7) 가로 넘침 없음', await noHorizontalScroll(page));
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  try {
    if (!only || only === 'lolypoly') await lolypoly(browser);
    if (!only || only === 'maru') await maru(browser);
  } catch (error) {
    record('runner', 'unexpected error', false, { note: String(error && error.stack || error).slice(0, 800) });
  } finally {
    await browser.close();
    const file = path.join(OUT, `results${only ? '-' + only : ''}.json`);
    fs.writeFileSync(file, JSON.stringify({ run_at: new Date().toISOString(), results }, null, 1));
    const fail = results.filter((r) => !r.ok).length;
    console.log(`\n${results.length - fail}/${results.length} passed → ${file}`);
    process.exit(fail ? 1 : 0);
  }
})();
