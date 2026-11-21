// Forbidden-spelling regression check for the dashboard (part of L2-DASH-003).
// It fails if the page script gains a common HTML-parsing sink or dynamic-code
// call, including whitespace variants, or if the page gains an inline handler.
// It is a lexical check, not proof: aliased or computed access would evade it.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const dir = path.join(__dirname, '../../rust/crates/file-mover/src/admin');
const script = fs.readFileSync(path.join(dir, 'admin.js'), 'utf8');
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
const forbidden = [
  /\b(innerHTML|outerHTML|insertAdjacentHTML|srcdoc|createContextualFragment|DOMParser)\b/,
  /document\s*\.\s*write/,
  /\beval\s*\(/,
  /\bnew\s+Function\b/,
  /\bFunction\s*\(/,
  /\bset(Timeout|Interval)\s*\(\s*["'`]/,
  /setAttribute\s*\(\s*["'`]\s*on/i,
  /\[\s*["'`](innerHTML|outerHTML)["'`]\s*\]/,
];
for (const pattern of forbidden) {
  const m = script.match(pattern);
  assert.ok(!m, `admin.js matches ${pattern}: ${m && m[0]}`);
}
assert.ok(!/\son[a-z]+\s*=/i.test(html), 'index.html has an inline event handler');
assert.ok(script.includes('textContent'), 'expected text insertion');
// The checker itself must catch the variants it advertises.
for (const sample of ['x.innerHTML = y', 'eval (s)', 'setTimeout ("code", 1)', 'new  Function("a")',
  'el.setAttribute( "onclick", s)', 'document . write(s)', 'el["outerHTML"] = s']) {
  assert.ok(forbidden.some((p) => p.test(sample)), `pattern set misses: ${sample}`);
}
console.log('no HTML sinks ok');
