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
