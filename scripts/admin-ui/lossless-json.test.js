// Lossless JSON parser in the embedded admin page: wide integers stay exact.
const src = require('fs').readFileSync(require("path").join(__dirname, "../../rust/crates/file-mover/src/admin/admin.js"), 'utf8');
const body = src.slice(src.indexOf('function parseJSON'), src.indexOf('  function request'));
const parseJSON = new Function(body + '; return parseJSON;')();
const assert = require('assert');
const v = parseJSON(String.raw`{"a":18446744073709551615,"b":-9223372036854775808,"c":[0,1.5,1e3,null,true,false],"d":"x\u00e9\n\""}`);
assert.strictEqual(v.a, 18446744073709551615n);
assert.strictEqual(v.b, -9223372036854775808n);
assert.deepStrictEqual(v.c, [0n, 1.5, 1000, null, true, false]);
assert.strictEqual(v.d, 'xé\n"');
assert.strictEqual(parseJSON(' [ ] ').length, 0);
const bads = ['', '{', '[1,]', '01', '{"a":1}x', '"\u0001"', 'nul', '{"a" 1}', '1.', String.raw`"\x"`, '{"a":1,}'];
for (const bad of bads) assert.throws(() => parseJSON(bad), Error, JSON.stringify(bad));
console.log('lossless parser ok');

// Exact byte formatting: BigInt arithmetic, never binary64; rounds down, never overstates.
const bytesSrc = src.slice(src.indexOf('  function bytes(value)'), src.indexOf('  function time('));
const bytes = new Function(bytesSrc + '; return bytes;')();
assert.strictEqual(bytes(null), '—');
assert.strictEqual(bytes('0'), '0 bytes');
assert.strictEqual(bytes('1023'), '1023 bytes');
assert.strictEqual(bytes('1024'), '1.00 KiB (1024 bytes)');
assert.strictEqual(bytes('1649267441664'), '1.50 TiB (1649267441664 bytes)');
assert.strictEqual(bytes(18446744073709551615n), '15.99 EiB (18446744073709551615 bytes)');
const u128 = '340282366920938463463374607431768211455';
assert.strictEqual(bytes(u128), '295147905179352825855.99 EiB (' + u128 + ' bytes)');
console.log('byte formatting ok');

// Retry context encoder in the admin page agrees with the reference vectors.
(async () => {
  const path = require('path');
  const vectors = JSON.parse(require('fs').readFileSync(path.join(__dirname, '../../docs/api/retry-context.candidate.vectors.json'), 'utf8'));
  const start = src.indexOf('  var CONTROL = ');
  const encSrc = src.slice(start, src.indexOf('  var RETRY_RESULT'));
  const { freezeRetry, retryProblem } = new Function('crypto', 'btoa', 'TextEncoder',
    encSrc + '; return { freezeRetry: freezeRetry, retryProblem: retryProblem };')(globalThis.crypto, globalThis.btoa, globalThis.TextEncoder);
  let checked = 0;
  for (const k of vectors.known_answers.filter(k => k.body.job_ids.length === 1)) {
    const review = { instance_id: k.context.instance_id, job_id: k.job_id_decimal_strings[0], review_epoch: k.context.review_epochs[0] };
    const f = await freezeRetry(review, k.context.reason);
    assert.strictEqual(f.header, k.header_value, k.id);
    assert.strictEqual(f.body, JSON.stringify(k.body), k.id);
    assert.strictEqual(retryProblem(k.context.reason), null, k.id);
    checked++;
  }
  assert.ok(checked >= 1);
  // Valid reasons: the canonical escape equals JSON escaping (only " and \ occur).
  for (const reason of ['say "hi"', 'C:\\share\\x', 'ünï \u2028 ok', '\\"\\']) {
    const f = await freezeRetry({ instance_id: '0'.repeat(32), job_id: '9223372036854775807', review_epoch: 4294967295 }, reason);
    const payload = Buffer.from(f.header.slice(3), 'base64url').toString('utf8');
    assert.strictEqual(payload.slice(payload.indexOf('"reason":') + 9, -1), JSON.stringify(reason));
    assert.ok(payload.includes('"review_epochs":[4294967295]'));
    assert.strictEqual(f.body, '{"job_ids":[9223372036854775807]}');
  }
  for (const bad of ['', '   ', 'a\nb', 'tab\there', '\u0085', 'x\ud800', '\udc00y', 'é'.repeat(257)]) {
    assert.notStrictEqual(retryProblem(bad), null, JSON.stringify(bad));
  }
  assert.strictEqual(retryProblem('é'.repeat(256)), null);
  console.log('retry context encoder ok (' + checked + ' known answer)');
})().catch(e => { console.error(e); process.exit(1); });
