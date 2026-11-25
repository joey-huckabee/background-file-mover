const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../../rust/crates/file-mover/src/admin/admin.js'), 'utf8');
function extract(name, context = {}) {
  const match = source.match(new RegExp('function ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}'));
  assert(match, 'missing ' + name);
  return vm.runInNewContext('(' + match[0] + ')', context);
}
const text = extract('privateLeftoversText');
const attention = extract('needsAttention');
assert.strictEqual(text({file_id: '2', folder_path: '/source/.file-mover/42-2'}),
  'Unexpected files were left in the mover’s private folder for file 2: /source/.file-mover/42-2');
const injected = '/source/<img src=x onerror=alert(1)>/.file-mover/1-0';
assert.strictEqual(text({file_id: '0', folder_path: injected}),
  'Unexpected files were left in the mover’s private folder for file 0: ' + injected);
assert.strictEqual(attention({condition: 'Committed', private_leftovers_count: 1}), true);
assert.strictEqual(attention({condition: 'Cancelled', private_leftovers_count: 2}), true);
assert.strictEqual(attention({condition: 'Committed'}), false);
assert.strictEqual(attention({condition: 'ReviewRequired'}), true);
assert.strictEqual(attention({condition: 'CleanupPending', source_cleanup_failed: true}), true);
assert(source.includes('activity.appendChild(el("p", privateLeftoversText(entry), "notice"))'));
assert(source.includes('allItems.filter(needsAttention).length'));
console.log('private leftover text and attention classification ok');

// Run the real Needs attention renderer, not just the predicate: a committed
// job with leftovers must actually appear alongside review jobs.
function element(tag, text) {
  return {tag, textContent: text || '', children: [], appendChild(child) { this.children.push(child); }};
}
const nodes = {'attention-status': element('p'), 'attention-rows': element('tbody')};
const items = [{job_id: '1', condition: 'Committed', private_leftovers_count: 1},
  {job_id: '2', condition: 'ReviewRequired'}, {job_id: '3', condition: 'Committed'}];
extract('renderAttention', {
  allItems: items, needsAttention: attention, olderCursor: null,
  $: id => nodes[id], clear: node => { node.children = []; }, el: element,
  jobCell: item => element('td', item.job_id), progress: () => element('span'),
  folderCell: () => element('td'), labelCells: () => {}
})();
assert.strictEqual(nodes['attention-rows'].children.length, 2);
assert.strictEqual(nodes['attention-status'].textContent, '2 jobs needing attention.');
const notice = nodes['attention-rows'].children[0].children[1].children[0];
assert(notice.textContent.startsWith('Unexpected files were left in the mover’s private folder.'));
console.log('committed leftover job rendered under Needs attention ok');
