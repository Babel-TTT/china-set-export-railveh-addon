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
//
// The extracted `jsonFetch` mirrors the real client, including the `/api`
// prefix, so a call site that prefixes it twice fails here as it would in the
// browser.  A step that cannot run throws and exits non-zero rather than
// printing a cell it never produced.
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
const API = '/api';
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
  // the same prefix rule as the real client: a caller passes the part after
  // /api, and passing /api again would 404 (that is what this mirrors)
  const response = await fetch(BASE + API + path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (body && body.error)) {
    throw new Error((body && body.error) || ('HTTP ' + response.status));
  }
  return body;
}
function rulePreview() { return ''; }
`;

const NAMES = ['caseOf', 'splitCase', 'valueBounds', 'newLeaf', 'nextFreeCase',
  'newSubSwitch', 'treeFromReport', 'variableSelect', 'modelSelect', 'switchBlock',
  'sectionEditor', 'registerSlot', 'renderRuleEditor', 'sectionCount', 'flushRuleTree',
  'ruleEditorAction', 'ruleEditorField', 'ruleEditorMode', 'fleetClickOpensCard'];

const factory = new Function('BASE', PUPPET + NAMES.map(grab).join('\n')
  + '\nreturn { caseOf, splitCase, flushRuleTree, ruleEditorAction, ruleEditorField,'
  + '\n         ruleEditorMode, fleetClickOpensCard };');

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

/**
 * The slot index of a node, as a rendered control would carry it.
 *
 * A write-back replaces the tree with the server's canonical nodes, so a node
 * held across a flush is stale, and a stale slot used to resolve to -1: the
 * control's click was then a silent no-op and this tool printed a step that had
 * not happened.  Fail loudly instead, and re-read the node from card.__tree
 * immediately before every call, the way a re-rendered control would.
 */
function slotOf(card, node) {
  const index = (card.__slots || []).indexOf(node);
  if (index < 0) {
    throw new Error('stale node: re-read it from card.__tree after the last flush');
  }
  return index;
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

  // 3. add a case.  It is pushed onto the end, but the tree the server sends
  //    back is canonical: the case-less fallback is last there, so the appended
  //    case sits before it and `children[len-1]` is the fallback, not the new
  //    case.  The two steps below therefore edit the fallback.
  let root = card.__tree[1][0];
  await api.ruleEditorAction(card, {
    dataset: { ruleAction: 'add-case', slot: String(slotOf(card, root)) } });
  log('＋ 加区间');

  const fallbackNode = () =>
    card.__tree[1][0].children[card.__tree[1][0].children.length - 1];
  await api.ruleEditorField(card, {
    dataset: { ruleField: 'model', slot: String(slotOf(card, fallbackNode())) }, value: 'b_l' });
  log('该兜底选模型 b_l');

  // 5. give the fallback a condition, so it stops being the fallback.  The write
  //    back above replaced the tree, so the node is re-read here as the
  //    re-rendered control would.
  await api.ruleEditorField(card, {
    dataset: { ruleField: 'value', slot: String(slotOf(card, fallbackNode())) }, value: '8' });
  log('该兜底改成 consist<=8');

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

  // 7. every operator the control offers has to survive a write-back
  //
  //    The cell stores a range, so `<` and `>` come back as `<=`/`>=` with the
  //    number moved by one: offering them made the control look like it jumped to
  //    another symbol as soon as it was used.  This is that regression, checked
  //    against the server's own canonical form rather than against a guess.
  console.log('\noperator list survives a write-back');
  const FAILURES = [];
  for (const [operator, low, high] of [['<=', 4], ['==', 5], ['>=', 3], ['..', 7, 9]]) {
    card.__tree = [[], [], []];
    card.__treeError = '';
    await api.ruleEditorMode(card, 'switch', 1);
    const pick = (field, value, index) => {
      const node = card.__tree[1][0].children[index ?? 0];
      return api.ruleEditorField(card, {
        dataset: { ruleField: field, slot: String(slotOf(card, node)) }, value: String(value) });
    };
    await pick('operator', operator);
    if (operator === '..') {
      await pick('value', low);
      await pick('value-high', high);
    } else {
      await pick('value', low);
    }
    const written = card.__tree[1][0].children[0].case;
    const back = api.splitCase(written).operator;
    const ok = back === operator && !card.__treeError;
    if (!ok) FAILURES.push(operator);
    console.log('%s 当 %s %s -> 区间 %s %s', ok ? '  ok ' : ' FAIL',
      operator === '..' ? `${low}..${high}` : `${operator}${low}`,
      `(${JSON.stringify(card.cell())})`, JSON.stringify(written),
      card.__treeError ? 'ERROR: ' + card.__treeError : '');
  }

  //    What the control *offers* matters as much as what it stores: `<` and `>`
  //    in that list were the whole bug.
  card.__tree = [[], [], []];
  await api.ruleEditorMode(card, 'switch', 1);
  const offered = [...card.querySelector('[data-rule-editor]').innerHTML
    .matchAll(/data-rule-field="operator"[\s\S]*?<\/select>/g)]
    .flatMap((select) => [...select[0].matchAll(/<option value="([^"]*)"/g)]
      .map((option) => option[1]));
  const expected = ['<=', '==', '>=', '..'];
  const offeredOk = JSON.stringify(offered) === JSON.stringify(expected);
  console.log('%s the operator list is exactly what the cell stores: %s',
    offeredOk ? '  ok ' : ' FAIL', JSON.stringify(offered));
  if (!offeredOk) FAILURES.push('offered ' + JSON.stringify(offered));

  // 8. a click inside a fleet card opens the vehicle -- except on the controls the
  //    card carries (折叠到 / 折叠项名称 / the order buttons).  Without that guard
  //    opening the dropdown navigated away, so the value could not be changed.
  console.log('\nclicking a fleet card control does not open the vehicle');
  const target = (selector) => ({
    closest: (asked) => (asked.split(', ').includes(selector) ? { selector } : null),
  });
  const cases = [['select', false], ['input', false], ['button', false],
    ['textarea', false], ['label', false], ['a', false], ['div', true],
    ['.vcard', true]];
  for (const [selector, expectedToOpen] of cases) {
    const opens = api.fleetClickOpensCard(target(selector));
    const ok = opens === expectedToOpen;
    if (!ok) FAILURES.push('fleetClickOpensCard(' + selector + ')');
    console.log('%s a click on <%s> %s the vehicle',
      ok ? '  ok ' : ' FAIL', selector, opens ? 'opens' : 'does not open');
  }
  // the guard has to be the one the listener actually asks
  const wired = /fleetList'\)\.addEventListener\('click',[\s\S]{0,120}?fleetClickOpensCard/.test(src);
  console.log('%s the fleet list listener asks the guard', wired ? '  ok ' : ' FAIL');
  if (!wired) FAILURES.push('the fleet list listener does not use fleetClickOpensCard');

  // 9. back to a single sheet, then invisible
  await api.ruleEditorMode(card, 'plain', 1);
  log('第 2 段 = 一张图');
  await api.ruleEditorMode(card, 'hidden', 1);
  log('第 2 段 = 隐形');

  console.log('\nfinal tree:', JSON.stringify(card.__tree));
  console.log('final error:', JSON.stringify(card.__treeError));
  console.log('operator failures:', FAILURES.length ? FAILURES : 'none');
  if (FAILURES.length) process.exitCode = 1;
})().catch((error) => { console.error('SIMULATION FAILED:', error); process.exit(1); });
