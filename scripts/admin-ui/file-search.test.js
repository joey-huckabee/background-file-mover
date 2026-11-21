// File-name search in the embedded admin page: debounce, cursor following,
// generations (stale replies dropped), restarts and the activity marker.
const assert = require('assert');
const src = require('fs').readFileSync(require('path').join(__dirname, '../../rust/crates/file-mover/src/admin/admin.js'), 'utf8');
const start = src.indexOf('  var statusBase = "";');
const end = src.indexOf('  // ---- end file-name search ----');
assert.ok(start > 0 && end > start, 'file-name search code not found');

function page() {
  const calls = [];   // { url, marked, resolve, reject, aborted }
  const timers = [];
  const env = { renders: [], status: { textContent: '' } };
  const ctl = { search: null };
  let generation = 0;
  // Like the page's request(): a new read of a kind aborts the older one.
  const request = (path, marked, kind) => {
    assert.strictEqual(kind, 'search');
    if (ctl.search) { ctl.search.abort(); }
    const mine = ++generation;
    const call = { url: new URL(path, 'https://mover.invalid'), marked, aborted: false };
    ctl.search = { abort: () => { call.aborted = true; call.reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); } };
    calls.push(call);
    return new Promise((resolve, reject) => {
      call.reject = reject;
      call.reply = (status, body) => resolve({ status, body, current: mine === generation });
    });
  };
  const api = new Function('request', 'quiet', 'renderHistory', '$', 'ctl', 'setTimeout', 'clearTimeout', 'state',
    'var allItems = state.items, query = "";\n' + src.slice(start, end) +
    '\nreturn { queue: function (q) { query = q; queueSearch(); },' +
    ' load: function (items) { allItems = items; refreshSearch(); },' +
    ' cancel: cancelSearch, match: serverMatch, note: searchNote,' +
    ' state: function () { return search.state; } };')(
    request,
    (e) => e.name === 'AbortError' || e.message === 'signed out',
    (live) => env.renders.push(live),
    () => env.status,
    ctl,
    (fn, ms) => { timers.push({ fn, ms, cleared: false }); return timers.length - 1; },
    (id) => { timers[id].cleared = true; },
    { items: [] });
  const fire = () => {
    const live = timers.filter((t) => !t.cleared && !t.fired);
    assert.strictEqual(live.length, 1, 'one pending debounce');
    assert.strictEqual(live[0].ms, 300);
    live[0].fired = true; live[0].fn();
  };
  return { api, calls, timers, env, fire };
}
const jobs = (from, to) => Array.from({ length: to - from + 1 }, (_, k) => ({ job_id: String(from + k) }));
const tick = () => new Promise((r) => setImmediate(r));
// parseJSON yields BigInt for integers, as the page sees them.
const reply = (ids, cursor, scanned) => ({ job_ids: ids, next_cursor: cursor, scanned_jobs: BigInt(scanned) });

(async () => {
  // Debounce, the first request marked, cursor continuations unmarked.
  {
    const { api, calls, env, fire } = page();
    api.load(jobs(5, 40));
    api.queue('run 7/é');
    assert.strictEqual(calls.length, 0, 'nothing is sent while typing');
    fire();
    assert.strictEqual(calls.length, 1);
    const first = calls[0].url;
    assert.strictEqual(first.pathname, '/api/v2/admin/jobs/search');
    assert.strictEqual(first.search, '?q=run%207%2F%C3%A9&until=5');
    assert.strictEqual(calls[0].marked, true, 'the typed search counts as activity');
    assert.ok(api.note().startsWith(' · Searching file names… 0 jobs checked'));
    calls[0].reply(200, reply(['40', '31'], 'c1.i.s.d.5.30', 10));
    await tick();
    assert.strictEqual(calls.length, 2);
    assert.strictEqual(calls[1].url.searchParams.get('cursor'), 'c1.i.s.d.5.30', 'the token is passed back unchanged');
    assert.strictEqual(calls[1].url.searchParams.get('until'), '5');
    assert.strictEqual(calls[1].marked, false, 'continuations are background reads');
    assert.deepStrictEqual(env.renders, [true], 'new matches redraw the list, keeping an open detail');
    assert.ok(api.match({ job_id: '31' }) && !api.match({ job_id: '30' }));
    assert.strictEqual(api.note(), ' · Searching file names… 10 jobs checked');
    // A chunk without new matches only updates the note.
    calls[1].reply(200, reply(['31'], 'c1.i.s.d.5.20', 10));
    await tick();
    assert.deepStrictEqual(env.renders, [true]);
    assert.ok(env.status.textContent.endsWith('20 jobs checked'));
    calls[2].reply(200, reply(['6'], null, 15));
    await tick();
    assert.strictEqual(calls.length, 3);
    assert.strictEqual(api.state(), 'done');
    assert.strictEqual(api.note(), '');
    assert.ok(api.match({ job_id: '6' }));
  }
  // A newer query aborts the older search and drops its late reply.
  {
    const { api, calls, fire } = page();
    api.load(jobs(1, 9));
    api.queue('alpha'); fire();
    const old = calls[0];
    api.queue('beta');
    assert.strictEqual(old.aborted, true);
    assert.strictEqual(api.match({ job_id: '3' }), false, 'old matches never show for the new query');
    fire();
    assert.strictEqual(calls[1].url.searchParams.get('q'), 'beta');
    calls[1].reply(200, reply(['2'], null, 9));
    await tick();
    assert.ok(api.match({ job_id: '2' }));
    // Typing again before the pause clears the earlier pending one.
    api.queue('gamma'); api.queue('delta');
    fire();
    assert.strictEqual(calls[2].url.searchParams.get('q'), 'delta');
  }
  // A stale reply (superseded at the request layer) is ignored.
  {
    const { api, calls, fire } = page();
    api.load(jobs(1, 9));
    api.queue('x'); fire();
    api.load(jobs(1, 12)); // The loaded range changed: restart, as a background read.
    assert.strictEqual(calls.length, 2);
    assert.strictEqual(calls[1].marked, false);
    assert.strictEqual(calls[0].aborted, true);
    calls[1].reply(200, reply(['12'], null, 12));
    await tick();
    assert.ok(api.match({ job_id: '12' }));
    // Same range again (a live refresh with no new job): no restart.
    api.load(jobs(1, 12));
    assert.strictEqual(calls.length, 2);
  }
  // "Load older jobs" moves the oldest loaded job: the search restarts with the new bound.
  {
    const { api, calls, fire } = page();
    api.load(jobs(300, 900));
    api.queue('take'); fire();
    calls[0].reply(200, reply([], null, 601));
    await tick();
    api.load(jobs(1, 900));
    assert.strictEqual(calls.length, 2);
    assert.strictEqual(calls[1].url.searchParams.get('until'), '1');
    assert.strictEqual(calls[1].url.searchParams.get('cursor'), null);
  }
  // A failure keeps local matches, says so, and a reload retries.
  {
    const { api, calls, env, fire } = page();
    api.load(jobs(1, 3));
    api.queue('x'); fire();
    calls[0].reply(503, { error: 'storage_unavailable' });
    await tick();
    assert.strictEqual(api.state(), 'failed');
    assert.strictEqual(api.note(), ' · File names could not be searched. Try again.');
    assert.ok(env.status.textContent.endsWith('Try again.'));
    api.load(jobs(1, 3)); // Refresh: same range, but a failed search is retried.
    assert.strictEqual(calls.length, 2);
    assert.strictEqual(calls[1].marked, false);
  }
  // Nothing is sent for an empty, over-long or control-character query, or
  // with no jobs loaded; cancel (sign-out, Show all jobs) drops everything.
  {
    const { api, calls, timers, fire } = page();
    api.load(jobs(1, 3));
    api.queue('');
    assert.strictEqual(timers.length, 0);
    api.queue('é'.repeat(257)); fire();
    api.queue('a\u0007b'); fire();
    assert.strictEqual(calls.length, 0);
    api.queue('é'.repeat(256)); fire();
    assert.strictEqual(calls.length, 1, '256 characters are allowed');
    api.cancel();
    assert.strictEqual(calls[0].aborted, true);
    assert.strictEqual(api.state(), 'idle');
    const empty = page();
    empty.api.queue('x'); empty.fire();
    assert.strictEqual(empty.calls.length, 0);
  }
  console.log('file-name search ok');
})().catch((e) => { console.error(e); process.exit(1); });
