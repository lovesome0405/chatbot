// app.js의 실제 함수 원문을 잘라 node vm에서 실행하고, Python 이식(ari_baseline.score)과 점수를 대조한다.
//   node scripts/ari_parity.mjs <ari app.js 경로> <cases.json>   → stdout: [{message, haystack_id, js_score}]
import fs from 'node:fs';
import vm from 'node:vm';

const [appPath, casesPath] = process.argv.slice(2);
const src = fs.readFileSync(appPath, 'utf8');
function extract(name) {
  const start = src.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing ${name}`);
  let depth = 0, i = src.indexOf('{', start);
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  return src.slice(start, i + 1);
}
const code = ['normalizeSearchText', 'tokenizeAriSearchText', 'scoreAriTextMatch'].map(extract).join('\n');
const ctx = vm.createContext({});
vm.runInContext(code, ctx);
const cases = JSON.parse(fs.readFileSync(casesPath, 'utf8'));
const out = cases.map((c) => ({ message: c.message, id: c.id, js_score: vm.runInContext(`scoreAriTextMatch(${JSON.stringify(c.message)}, ${JSON.stringify(c.haystack)})`, ctx) }));
process.stdout.write(JSON.stringify(out));
