// ari app.js 의 resolveAriRagEndpoint 규칙 확인(브라우저 없이). 실행: node e2e/ari_config.test.cjs <ari>/app.js
const fs = require('fs');
const assert = require('assert');
const src = fs.readFileSync(process.argv[2] || '../ari/app.js', 'utf8');
const pick = (name) => src.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n}\\n`))[0];
const ARI_RAG_LOCAL_DEFAULT = 'http://127.0.0.1:8088/v1/public/chat';
eval(pick('isLocalHostName') + pick('resolveAriRagEndpoint') + 'globalThis.resolve = resolveAriRagEndpoint;');
const local = new URL('http://127.0.0.1:8765/index.html');
const pub = new URL('https://maru.example.org/index.html');
const cases = [
  ['off', local, ''], ['', local, ''], ['off', pub, ''],
  ['auto', local, ARI_RAG_LOCAL_DEFAULT], ['auto', pub, ''],                       // 로컬 기본값은 로컬 페이지에서만
  ['http://127.0.0.1:8088/v1/public/chat', pub, ''],                                 // 공개 페이지 → 127.0.0.1 거부
  ['http://rag.example.org/v1/public/chat', pub, ''],                                // https 아님 거부
  ['https://rag.example.org/v1/public/chat', pub, 'https://rag.example.org/v1/public/chat'],
  ['javascript:alert(1)', pub, ''],
];
for (const [raw, loc, want] of cases) assert.strictEqual(resolve(raw, loc), want, `${raw} @ ${loc.host}`);
console.log(`ari rag-config 규칙 ${cases.length}/${cases.length} 통과`);
