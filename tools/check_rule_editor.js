// Drives the workbench block editor's operations against a running workbench and
// prints the cell each step writes, so every operation can be checked against the
// NML the generator will actually compile.
//
// It needs node and a running server, so it is not part of `make check`:
//
//   python3 web/workbench/server.py --port 4174 &
//   node tools/check_rule_editor.js http://127.0.0.1:4174
//
// The tree edits live in web/workbench/app.js, and this runs those very functions
// (extracted from the file) rather than a copy of them, so a control that stops
// producing a valid cell shows up here.  Every printed cell was rendered AND
// parsed again by the generator's own parser on the server, so a printed cell is
// by construction one the generator accepts.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'web/workbench/app.js'), 'utf8');
const BASE = process.argv[2] || 'http://127.0.0.1:4174';

function grab(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('not found: ' + name);
  // a few of these are `async function`, and dropping the keyword would make the
  // extracted body's await a syntax error
  const prefix = src.slice(Math.max(0, start - 6), start) === 'async ' ? start - 6 : start;
  let depth = 0;
  for (let j = src.indexOf('{', start); j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (!depth) return src.slice(prefix, j + 1); }
  }
  throw new Error('unbalanced: ' + name);
}

const PUPPET = `
const esc = (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const mono = (v) => '<span class="mono">' + esc(v) + '</span>';
const shortVariable = (n) => String(n || '')
  .replace('position_in_consist_from_end', 'tailpos').replace('position_in_consist', 'pos')
  .replace('num_vehs_in_consist', 'consist').replace('position_in_articulated_veh', 'unitpos');
const RULE_VARIABLES = [
  ['position_in_consist', 'pos', '整列第几节'],
  ['position_in_consist_from_end', 'tailpos', '从尾数第几节'],
  ['num_vehs_in_consist', 'consist', '整列共几节'],
  ['position_in_articulated_veh', 'unitpos', '本车第几段'],
];
const state = {
  row: { id: 'df4c', parts: '2|8|2', power_section: '1' },
  fleet: { liveries: [{ _index: 0, id: 'df4c' }] },
};
let rulePreviewSerial = 0;
const spriteRecords = (id) => ['h_s', 'h_l', 'b_l'].map((basename) => ({ basename }));
async function jsonFetch(path, options) {
  const response = await fetch(BASE + path, options);
  const body = await response.json();
  if (!response.ok && body && body.error) throw new Error(body.error);
  return body;
}
function rulePreview() { return ''; }
`;

const NAMES = ['caseOf', 'splitCase', 'valueBounds', 'newLeaf', 'nextFreeCase',
  'newSubSwitch', 'treeFromReport', 'variableSelect', 'modelSelect', 'switchBlock',
  'sectionEditor', 'registerSlot', 'renderRuleEditor', 'sectionCount', 'flushRuleTree',
  'ruleEditorAction', 'ruleEditorField', 'ruleEditorMode'];

const factory = new Function('BASE', PUPPET + NAMES.map(grab).join('\n')
  + '\nreturn { caseOf, flushRuleTree, ruleEditorAction, ruleEditorField, ruleEditorMode };');

function fakeCard() {
  const els = {};
  return {
    dataset: { livery: '0' },
    __slots: [],
    __tree: undefined,
    __treeError: '',
    querySelector(selector) {
      if (!els[selector]) {
        els[selector] = { value: '', innerHTML: '', dataset: {}, isConnected: true };
      }
      return els[selector];
    },
    cell() { return this.querySelector('[data-livery-field="graphics_parts"]').value; },
  };
}

/** The slot index of a node, as a rendered control would carry it. */
function slotOf(card, node) {
  return (card.__slots || []).indexOf(node);
}

(async () => {
  const api = factory(BASE);
  const card = fakeCard();
  function log(step) {
    console.log('%s\n    cell = %s %s', step, JSON.stringify(card.cell()),
      card.__treeError ? '\n    ERROR: ' + card.__treeError : '');
  }

  // 1. the row has no rules at all, so the editor offers to start
  card.__tree = null;
  card.__treeError = '';
  await api.ruleEditorAction(card, { dataset: { ruleAction: 'start', slot: '-1' } });
  log('开始按段设置 (start)');

  // 2. section 2 switches from invisible to "filter by a condition"
  await api.ruleEditorMode(card, 'switch', 1);
  log('第 2 段 = 按条件分');

  // 3. add a case and point it at a sheet
  let root = card.__tree[1][0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'add-case', slot: String(slotOf(card, root)) } });
  log('＋ 加区间');

  const added = card.__tree[1][0].children[0];
  await api.ruleEditorField(card, {
    dataset: { ruleField: 'model', slot: String(slotOf(card, added)) }, value: 'h_s' });
  log('该区间选模型 h_s');

  await api.ruleEditorField(card, {
    dataset: { ruleField: 'value', slot: String(slotOf(card, added)) }, value: '6' });
  log('该区间数值改成 6');

  // 4. add the fallback sheet
  root = card.__tree[1][0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'add-default', slot: String(slotOf(card, root)) } });
  log('加兜底');
  const fallback = card.__tree[1][0].children.find((child) => !child.case);
  await api.ruleEditorField(card, {
    dataset: { ruleField: 'model', slot: String(slotOf(card, fallback)) }, value: 'h_l' });
  log('兜底选模型 h_l');

  // 5. a case that filters further instead of showing a sheet
  root = card.__tree[1][0];
  const first = card.__tree[1][0].children[0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'fold', slot: String(slotOf(card, first)) } });
  log('该区间改成「再筛一层」');
  const nested = card.__tree[1][0].children[0];
  await api.ruleEditorField(card, {
    dataset: { ruleField: 'value', slot: String(slotOf(card, nested)) }, value: '2' });
  log('内层数值 = 2');

  // 6. the outer fallback continues the chain into a second switch
  root = card.__tree[1][0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'drop-default', slot: String(slotOf(card, root)) } });
  log('删掉兜底');
  root = card.__tree[1][0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'chain', slot: String(slotOf(card, root)) } });
  log('兜底改成「再筛一层」(chain)');

  // 7. back to a single sheet, then invisible
  await api.ruleEditorMode(card, 'plain', 1);
  log('第 2 段 = 一张图');
  await api.ruleEditorMode(card, 'hidden', 1);
  log('第 2 段 = 隐形');

  console.log('\nfinal tree:', JSON.stringify(card.__tree));
  console.log('final error:', JSON.stringify(card.__treeError));
})().catch((error) => { console.error('SIMULATION FAILED:', error); process.exit(1); });
