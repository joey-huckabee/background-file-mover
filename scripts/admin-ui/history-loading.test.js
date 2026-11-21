// Job history loading in the embedded admin page: the 40-page bound
// (10,240 jobs per round), "Load older jobs" and the incomplete-history notice.
const assert = require('assert');
const src = require('fs').readFileSync(require('path').join(__dirname, '../../rust/crates/file-mover/src/admin/admin.js'), 'utf8');
const start = src.indexOf('  var pageBudget = 40, olderCursor = null;');
const end = src.indexOf('  function stateOf(item)');
assert.ok(start > 0 && end > start, 'history loading code not found');

// A fake list route: jobs 1..total, newest first, 256 per page, exact cursors.
function server(total, options = {}) {
  const calls = [];
  const request = (path, deliberate, kind) => {
    const url = new URL(path, 'https://mover.invalid');
    assert.strictEqual(url.pathname, '/api/v2/admin/jobs');
    assert.strictEqual(url.searchParams.get('order'), 'desc');
    assert.strictEqual(kind, 'page');
    const limit = Number(url.searchParams.get('limit'));
    const cursor = url.searchParams.get('cursor');
    calls.push({ cursor, deliberate });
    const from = cursor === null ? total : Number(cursor) - 1;
    const items = [];
    for (let id = from; id >= 1 && items.length < limit; id--) { items.push({ job_id: String(id) }); }
    const last = items.length ? Number(items[items.length - 1].job_id) : 1;
    const page = calls.length;
    if (options.status && options.status(page)) { return Promise.resolve({ status: 503, body: null, current: true }); }
    return Promise.resolve({
      status: 200,
      body: { items, next_cursor: last > 1 ? String(last) : null },
      current: !(options.stale && options.stale(page)),
    });
  };
  return { calls, request };
}

function page(fake, viewName = 'history') {
  const nodes = {};
  const $ = (id) => (nodes[id] = nodes[id] || { hidden: false, textContent: '' });
  const api = new Function('$', 'request', 'state',
    'var allItems = [], view = state.view;\n' + src.slice(start, end) +
    '\nreturn { fetchAll: fetchAll, renderCompleteness: renderCompleteness,' +
    ' set: function (items) { allItems = items; },' +
    ' older: function () { pageBudget += 40; },' +
    ' cursor: function () { return olderCursor; } };')($, fake.request, { view: viewName });
  // As loadPage does: keep the loaded jobs, then show completeness.
  api.load = (deliberate) => api.fetchAll(deliberate).then((items) => {
    if (items !== null) { api.set(items); api.renderCompleteness(); }
    return items;
  });
  return { api, $ };
}

const ids = (items) => items.map((i) => Number(i.job_id));
const ascending = (from, to) => Array.from({ length: to - from + 1 }, (_, k) => from + k);

(async () => {
  // More than one round: the newest 10,240 load, oldest first; the rest wait.
  {
    const fake = server(10240 + 300);
    const { api, $ } = page(fake);
    const items = await api.load(true);
    assert.strictEqual(fake.calls.length, 40);
    assert.deepStrictEqual(ids(items), ascending(301, 10540));
    assert.strictEqual(api.cursor(), '301');
    assert.deepStrictEqual(fake.calls.map((c) => c.deliberate), [true].concat(Array(39).fill(false)),
      'only the first page of a deliberate load counts as interaction');
    assert.strictEqual($('older').hidden, false);
    assert.strictEqual($('incomplete').hidden, false);
    assert.ok($('incomplete').textContent.startsWith('Showing the newest 10240 jobs only.'));

    // Load older jobs: the next round reaches the oldest job; the notice goes.
    api.older();
    fake.calls.length = 0;
    const all = await api.load(true);
    assert.strictEqual(fake.calls.length, 42);
    assert.deepStrictEqual(ids(all), ascending(1, 10540));
    assert.strictEqual(api.cursor(), null);
    assert.strictEqual($('older').hidden, true);
    assert.strictEqual($('incomplete').hidden, true);
    assert.strictEqual($('incomplete').textContent, '');
  }
  // Exactly the bound: complete, no notice.
  {
    const fake = server(10240);
    const { api, $ } = page(fake);
    assert.strictEqual((await api.load(false)).length, 10240);
    assert.strictEqual(fake.calls.length, 40);
    assert.strictEqual(api.cursor(), null);
    assert.strictEqual($('older').hidden, true);
    assert.strictEqual($('incomplete').hidden, true);
  }
  // One job more than the bound: the oldest job is reported as not loaded.
  {
    const { api, $ } = page(server(10241));
    assert.deepStrictEqual(ids(await api.load(false)), ascending(2, 10241));
    assert.strictEqual(api.cursor(), '2');
    assert.strictEqual($('older').hidden, false);
  }
  // Storage and Settings keep the Load older button but hide the notice.
  {
    const { api, $ } = page(server(10241), 'settings');
    await api.load(false);
    assert.strictEqual($('older').hidden, false);
    assert.strictEqual($('incomplete').hidden, true);
  }
  // A superseded load (a newer one started) gives up without results.
  {
    const fake = server(5000, { stale: (n) => n === 3 });
    const { api } = page(fake);
    assert.strictEqual(await api.load(false), null);
    assert.strictEqual(fake.calls.length, 3);
  }
  // A failing page rejects the whole load; nothing partial is shown.
  {
    const { api } = page(server(5000, { status: (n) => n === 2 }));
    await assert.rejects(api.load(false), /status 503/);
  }
  // Empty history.
  {
    const fake = server(0);
    const { api, $ } = page(fake);
    assert.deepStrictEqual(await api.load(false), []);
    assert.strictEqual(fake.calls.length, 1);
    assert.strictEqual($('older').hidden, true);
  }
  console.log('history loading ok');
})().catch((e) => { console.error(e); process.exit(1); });
