import fs from 'node:fs';
import vm from 'node:vm';

const htmlPath = process.argv[2];
if (!htmlPath) throw new Error('usage: node segment-forest-regression.mjs <index.html>');
const html = fs.readFileSync(htmlPath, 'utf8');

for (const required of [
  'Segment Forest', '分類Tree', 'Multi-layer lanes', 'ACTIVE CONDITIONS',
  'Vocal候補', 'Vocalなし候補', '開始区間', '区間数', '条件に一致する範囲',
  'rangeToWindow', 'recomputeMatches', 'currentClassifications', 'facetMatch(state.active,keys)'
]) {
  if (!html.includes(required)) throw new Error(\`missing UI/logic contract: \${required}\`);
}
if (/<(?:script|link)[^>]+(?:src|href)=["']https?:/i.test(html)) throw new Error('unexpected external runtime dependency');

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length !== 1) throw new Error(\`expected one inline script, got \${scripts.length}\`);
new Function(scripts[0]);
console.log('syntax: PASS');

function extractFunction(source, name) {
  const start = source.indexOf(\`function \${name}(\`);
  if (start < 0) throw new Error(\`function not found: \${name}\`);
  const brace = source.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(\`unterminated function: \${name}\`);
}

const facetSource = extractFunction(scripts[0], 'facetMatch');
const ctx = { Set, Object };
vm.createContext(ctx);
vm.runInContext(\`\${facetSource}; this.facetMatch = facetMatch;\`, ctx);
const active = new Set(['structure:a', 'structure:b', 'vocal:vocal']);
if (!ctx.facetMatch(active, new Set(['structure:b', 'vocal:vocal']))) throw new Error('same-tree OR / cross-tree AND positive case failed');
if (ctx.facetMatch(active, new Set(['structure:b']))) throw new Error('cross-tree AND negative case failed');
if (!ctx.facetMatch(new Set(), new Set())) throw new Error('empty filter should match');
console.log('facet semantics: PASS');

for (const pattern of [
  /el\.tree\.addEventListener\('click',[\s\S]*?rangeToWindow/,
  /el\.laneGrid\.addEventListener\('click',[\s\S]*?rangeToWindow/,
  /el\.start\.addEventListener\('input',[\s\S]*?updateSelection/,
  /el\.span\.addEventListener\('input',[\s\S]*?updateSelection/,
  /data-selftest|selftest/
]) if (!pattern.test(scripts[0])) throw new Error(\`interaction wiring missing: \${pattern}\`);
console.log('interaction wiring: PASS');

if (!html.includes('同一Tree内はOR、Tree間はAND')) throw new Error('facet rule is not visible to the user');
console.log('Segment Forest regression: PASS');
