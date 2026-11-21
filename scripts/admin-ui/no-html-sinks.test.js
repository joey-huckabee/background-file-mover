// The dashboard inserts dynamic values as text only (L2-DASH-003): no HTML
// parsing sinks or dynamic code in the page script, and no inline handlers.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const dir = path.join(__dirname, '../../rust/crates/file-mover/src/admin');
const script = fs.readFileSync(path.join(dir, 'admin.js'), 'utf8');
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
for (const sink of ['innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function', 'setTimeout("', "setTimeout('", 'srcdoc']) {
  assert.ok(!script.includes(sink), `admin.js uses ${sink}`);
}
assert.ok(!/\son[a-z]+\s*=/i.test(html), 'index.html has an inline event handler');
assert.ok(script.includes('textContent'), 'expected text insertion');
console.log('no HTML sinks ok');
