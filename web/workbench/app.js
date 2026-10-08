/* China Set: Export Rail Vehicles Add-on -- workbench front end.
 *
 * Plain JavaScript on purpose: the repository builds OpenTTD NewGRFs, not web
 * applications, so this file must run from a checkout with nothing installed.
 * Every form is generated from /api/schema, so adding a column to the data
 * tables only means updating web/workbench/schema.py.
 */
(() => {
  'use strict';

  const API = '/api';
  const VIEW_COLS = 8;          // sprite sheets hold 8 isometric views in a strip
  const VIEW_PX = 124;          // display cell size for the small views
  const VIEW_NAMES = ['SW', 'SE', 'NW', 'NE', 'W', 'S', 'N', 'E'];

  const state = {
    schema: null,
    fleet: { vehicles: [], counts: {}, git: {}, grf: {}, strings: 0 },
    strings: [],
    stringComments: [],
    stage: 'fleet',
    selected: null,        // { table, id }
    row: null,             // the unmodified row as loaded
    liveryIndex: null,     // which livery row tier 3 is showing
    stringFilter: 'livery',   // the string table opens on the livery labels
    dirty: false,
    doc: null,
    job: null,
    spriteView: 4,
  };

  const $ = (id) => document.getElementById(id);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  // a rule preview is answered by the server, so a fast typist can have several
  // requests in flight; only the newest one may write to the box
  let rulePreviewSerial = 0;
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const mono = (value) => `<span class="mono">${esc(value)}</span>`;

  function setStatus(message, kind = '') {
    const box = $('status');
    box.textContent = message;
    box.className = 'status ' + kind;
  }

  function warn(message) {
    setStatus(message, 'busy');
  }

  /** Report a save: errors block, warnings are informational. */
  function report(result, successMessage) {
    const errors = result.errors || [];
    const warnings = result.warnings || [];
    if (errors.length) {
      setStatus('校验未通过：\n' + errors.join('\n'), 'error');
      return false;
    }
    setStatus(warnings.length
      ? `${successMessage}\n注意：${warnings.join('\n注意：')}`
      : successMessage, warnings.length ? 'busy' : 'ok');
    return true;
  }

  async function jsonFetch(path, options = {}) {
    const response = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.error) {
      // the server refuses a write based on a stale read, so the browser has to
      // pick the file up again before the change can be repeated
      if (body.reload) {
        loadFleet().catch(() => {});
        if (state.selected) openVehicle(state.selected.table, state.selected.id);
      }
      throw new Error(body.error || ('HTTP ' + response.status));
    }
    return body;
  }

  // ---------------------------------------------------------------- fleet
  async function loadFleet() {
    const data = await jsonFetch('/state');
    state.fleet = data;
    state.strings = data.string_rows || state.strings;
    state.sheets = {};   // the sprite sheets may have just been re-rendered
    applyCounters(data);
    renderFleet();
    renderAux();
    renderStrings();
    if (data.total === 0) {
      setStatus('车队为空。用「新建车辆」添加第一台车，保存后点「生成代码」。');
    } else if (!state.dirty) {
      setStatus(`${data.total} 台车已登记。`, 'ok');
    }
  }

  function applyCounters(data) {
    $('repoRev').textContent = (data.git && data.git.describe) || 'no git';
    $('repoRev').className = 'pill' + (data.git && data.git.dirty ? ' tag warn' : '');
    $('counts').innerHTML = [
      ['机车', data.counts['locomotives.csv'] || 0],
      ['客车', data.counts['coaches.csv'] || 0],
      ['货车', data.counts['wagons.csv'] || 0],
      ['拖车', data.counts['unit_wagons.csv'] || 0],
      ['涂装行', (data.liveries || []).length],
      ['外观行', (data.variants || []).length],
      ['字符串', data.strings],
      ['GRF 字节', data.grf && data.grf.exists ? data.grf.size : '无'],
    ].map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('');
  }

  function applyState(data) {
    if (!data) return;
    state.fleet = data;
    state.strings = data.string_rows || state.strings;
    applyCounters(data);
    renderFleet();
    renderAux();
    renderVariants();
    renderStrings();
    renderStringDatalist();
  }

  /**
   * Every STR constant the string table defines, as one shared datalist.
   *
   * The fleet overview's 折叠项名称 box points at it (`list="strList"`), so the
   * author chooses a constant that exists instead of typing one and finding out
   * at `make check` that it does not.
   */
  function renderStringDatalist() {
    let list = $('strList');
    if (!list) {
      list = document.createElement('datalist');
      list.id = 'strList';
      document.body.appendChild(list);
    }
    const names = [...new Set((state.strings || [])
      .map((row) => String(row.constant || '').trim())
      .filter((name) => name.startsWith('STR_')))].sort();
    list.innerHTML = names.map((name) => `<option value="${esc(name)}"></option>`).join('');
  }

  /**
   * The fleet in purchase menu order.
   *
   * The arrows move a vehicle within this list, not within what is on screen, so
   * a search or a table filter cannot make them mean something else.  The server
   * computes `menu_index` from the same rule the generator uses for the sort
   * block, so this is the order the depot will show.
   */
  function fleetMenuOrder() {
    return (state.fleet.vehicles || []).slice()
      .sort((a, b) => (a.menu_index ?? 0) - (b.menu_index ?? 0));
  }

  /**
   * The vehicles that may be this one's parent in the purchase menu.
   *
   * Same table only (OpenTTD resolves the parent inside one GRF feature list),
   * never itself, and never one of its own descendants -- that would make a
   * cycle, which the generator refuses and the depot could not draw.
   */
  function groupCandidates(vehicle) {
    const all = state.fleet.vehicles || [];
    const parentOf = (id) => {
      const row = all.find((v) => v.table === vehicle.table && v.id === id);
      return row ? (row.variant_group || '').trim() : '';
    };
    return all
      .filter((other) => other.table === vehicle.table && other.id !== vehicle.id)
      .filter((other) => {
        const seen = new Set();
        let node = other.id;
        while (node && !seen.has(node)) {
          if (node === vehicle.id) return false;
          seen.add(node);
          node = parentOf(node);
        }
        return true;
      });
  }

  async function saveFleetMenu(rows, message) {
    try {
      const result = await jsonFetch('/fleet-menu', {
        method: 'POST',
        body: JSON.stringify({ rows }),
      });
      if (!report(result, message)) return;
      applyState(result.state);
      renderFleet();
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  /** Move one vehicle one place in the purchase menu. */
  async function moveFleet(vehicle, step) {
    const order = fleetMenuOrder();
    const index = order.findIndex(
      (item) => item.table === vehicle.table && item.id === vehicle.id);
    const target = index + step;
    if (index < 0 || target < 0 || target >= order.length) return;
    const moved = order.slice();
    [moved[index], moved[target]] = [moved[target], moved[index]];
    // renumber the whole list in tens, so a later insert fits between two rows
    await saveFleetMenu(moved.map((item, position) => ({
      table: item.table, id: item.id, menu_order: String((position + 1) * 10),
    })), '已调整购买菜单顺序。');
  }

  function renderFleet() {
    const search = ($('fleetSearch').value || '').trim().toLowerCase();
    const tableFilter = $('fleetTable').value;
    const list = $('fleetList');
    const vehicles = fleetMenuOrder().filter((vehicle) => {
      if (tableFilter && vehicle.table !== tableFilter) return false;
      if (!search) return true;
      return [vehicle.id, vehicle.name_string, vehicle.comment, vehicle.category]
        .join(' ').toLowerCase().includes(search);
    });

    if (!vehicles.length) {
      list.innerHTML = `<div class="empty"><p>${state.fleet.total
        ? '没有匹配的车辆。' : '车队为空，还没有任何车辆数据行。'}</p>
        <p class="hint">用右上角的「新建车辆」开始，或运行「生成车辆代码」检查空工程是否可编译。</p></div>`;
      return;
    }

    const order = fleetMenuOrder();
    list.innerHTML = vehicles.map((vehicle) => {
      const selected = state.selected && state.selected.id === vehicle.id
        && state.selected.table === vehicle.table;
      const tags = [
        `<span class="tag cyan">${esc(vehicle.category || '—')}</span>`,
        vehicle.vehicle_id != null ? `<span class="tag">ID ${vehicle.vehicle_id}</span>` : '',
        vehicle.track_type ? `<span class="tag">${esc(vehicle.track_type)}</span>` : '',
        vehicle.livery_count
          ? `<span class="tag">${vehicle.livery_count} 种涂装</span>`
          : '<span class="tag warn">默认涂装</span>',
        vehicle.sprites_ready
          ? '<span class="tag ok">精灵图就绪</span>'
          : `<span class="tag bad">缺 ${(vehicle.sprites_missing || []).length || '?'} 张贴图</span>`,
        vehicle.graphics_rules && vehicle.graphics_rules.set
          ? '<span class="tag">分节换图</span>' : '',
        vehicle.ac_supply === '1' ? '<span class="tag">供电</span>' : '',
        vehicle.mu === '1' ? '<span class="tag">动车组</span>' : '',
      ].filter(Boolean).join('');

      // purchase menu / group membership, editable right here in the overview
      const group = (vehicle.variant_group || '').trim();
      const series = (vehicle.series_string || '').trim();
      const candidates = groupCandidates(vehicle);
      const known = !series || Boolean(stringContent(series));
      const atTop = vehicle.menu_index === 0;
      const atEnd = vehicle.menu_index === (order.length - 1);
      const menu = `<div class="vmenu">
        <span class="hint">顺序</span>
        <span class="tag">${vehicle.menu_index + 1} / ${order.length}</span>
        <button data-fleet-move="-1" ${atTop ? 'disabled' : ''}
          title="在购买菜单里上移一位">▲</button>
        <button data-fleet-move="1" ${atEnd ? 'disabled' : ''}
          title="在购买菜单里下移一位">▼</button>
        <span class="hint">折叠到</span>
        <select data-fleet-group title="在购买菜单里把这台车折叠到另一台车下面">
          <option value="">独立一条</option>
          ${candidates.map((other) => `<option value="${esc(other.id)}"
            ${other.id === group ? ' selected' : ''}>${esc(other.id)}</option>`).join('')}
          ${group && !candidates.some((other) => other.id === group)
            ? `<option value="${esc(group)}" selected>${esc(group)}（不在本表）</option>` : ''}
        </select>
        <span class="hint">折叠项名称</span>
        <input data-fleet-series value="${esc(series)}" list="strList"
          placeholder="STR_… 留空 = 用共享系列名"
          title="折叠起来那一级显示的名字；填字符串表里已有的 STR 常量">
        ${known ? '' : `<span class="tag bad" title="这个常量不在字符串表里，make check 会报 missing">字符串不存在</span>`}
        ${vehicle.children_count
          ? `<span class="tag cyan">${vehicle.children_count} 个变体折在这里</span>`
          : ''}
        ${group && vehicle.children_count
          ? '<span class="tag warn" title="上游把多层嵌套标为实验性，建议只用一层">自己也折叠了</span>'
          : ''}
      </div>`;

      return `<div class="vcard${selected ? ' sel' : ''}" data-table="${esc(vehicle.table)}" data-id="${esc(vehicle.id)}">
        <div>
          <div class="vid">${esc(vehicle.id)} <span class="vname">${esc(vehicle.name_string || '')}</span></div>
          <div class="tags">${tags}</div>
          ${menu}
        </div>
        <div class="right-col hint">
          <div>${esc(vehicle.intro_year || '—')} 年 · ${esc(vehicle.speed || '—')} km/h</div>
          <div>${esc(vehicle.power || '—')} · ${esc(vehicle.weight || '—')} t</div>
        </div>
      </div>`;
    }).join('');
  }

  // --------------------------------------------------------------- detail
  function fieldApplies(field, table, row) {
    if (!field.applies || field.applies === 'all') return true;
    if (field.applies === 'locomotive') return table === 'locomotives.csv';
    return true;
  }

  function fieldControl(field, value, wide) {
    const id = 'f_' + field.name;
    const label = `<label for="${id}">${esc(field.label)}`
      + (field.required ? ' <span class="req">*</span>' : '')
      + (field.unit ? ` <span class="unit">${esc(field.unit)}</span>` : '')
      + '</label>';
    let control = '';
    if (field.kind === 'enum') {
      let choices = field.choices || [];
      if (field.dynamic === 'railtypes') choices = (state.schema.railtypes || []);
      const options = ['<option value=""></option>']
        .concat(choices.map((choice) => `<option value="${esc(choice)}"${choice === value ? ' selected' : ''
          }>${esc(choice)}</option>`));
      if (value && !choices.includes(value)) {
        options.push(`<option value="${esc(value)}" selected>${esc(value)}（不在表中）</option>`);
      }
      control = `<select id="${id}" data-field="${esc(field.name)}">${options.join('')}</select>`;
    } else if (field.kind === 'text-long') {
      control = `<textarea id="${id}" data-field="${esc(field.name)}"
        placeholder="${esc(field.placeholder)}">${esc(value)}</textarea>`;
    } else if (field.kind === 'toggle') {
      // genpnml.py reads a flag through _bool(): the value is stripped and
      // lowercased, then compared against {"1","y","yes","true","t","on"};
      // everything else -- including "0", "no", "off" and "false" -- is false,
      // and an empty cell falls back to the generator's default.  The tables
      // and data/README.md spell these as 1 and 0, so offer exactly that and do
      // not tempt anybody into a spelling that is false by accident.
      const choices = [['', '（留空 / 用生成器默认）'], ['1', '1 · 开启'], ['0', '0 · 关闭']];
      const options = choices.map(([option, text]) =>
        `<option value="${option}"${option === value ? ' selected' : ''}>${text}</option>`);
      if (value && !choices.some(([option]) => option === value)) {
        // a hand written "yes"/"true"/"on" is legal too, so keep it visible
        options.push(`<option value="${esc(value)}" selected>${esc(value)}（手写值）</option>`);
      }
      return `<div class="field toggle${wide ? ' field-wide' : ''}">
        <label for="${id}">${esc(field.label)}</label>
        <div class="box"><select id="${id}" data-field="${esc(field.name)}">${options.join('')}</select></div>
        ${field.help ? `<div class="help">${esc(field.help)}</div>` : ''}
      </div>`;
    } else {
      const numeric = field.kind === 'int' || field.kind === 'float';
      control = `<input id="${id}" data-field="${esc(field.name)}" type="text"
        ${numeric ? 'inputmode="decimal"' : ''} value="${esc(value)}"
        placeholder="${esc(field.placeholder)}">`;
    }
    return `<div class="field${wide ? ' field-wide' : ''}">${label}${control}
      ${field.help ? `<div class="help">${esc(field.help)}</div>` : ''}</div>`;
  }

  function currentVehicle() {
    if (!state.selected) return null;
    return (state.fleet.vehicles || []).find((item) => item.id === state.selected.id
      && item.table === state.selected.table) || null;
  }

  /** Everything the three tiers need to know about the selected vehicle. */
  function vehicleFacts(vehicle, row) {
    const parts = (row.parts || '').split(/[|,;]/).map((piece) => piece.trim())
      .filter(Boolean);
    const powerSection = (row.power_section || '').trim();
    const facts = [
      ['车辆 ID', row.id || '—'],
      ['数据表', state.selected.table],
      ['ID 段序号', vehicle && vehicle.vehicle_id != null ? String(vehicle.vehicle_id) : '待生成'],
      ['NML 段', vehicle && vehicle.band ? vehicle.band : '—'],
      ['精灵图目录', `gfx/${row.folder || '?'}/`],
      ['分段', parts.length
        ? `${parts.join(' + ')} = ${parts.reduce((sum, p) => sum + Number(p || 0), 0)} 段`
        : '—'],
      ['车身段', powerSection ? `第 ${Number(powerSection) + 1} 段（索引 ${powerSection}）` : '—'],
      ['涂装', `${(state.fleet.liveries || []).filter((item) =>
        (item.id || '').trim() === row.id).length} 行`],
    ];
    return facts.map(([label, value]) =>
      `<div class="fact"><span>${esc(label)}</span><b>${esc(value)}</b></div>`).join('');
  }

  function renderDetail() {
    const row = state.row;
    if (!row) {
      $('detailEmpty').classList.remove('hidden');
      $('detailBody').classList.add('hidden');
      return;
    }
    $('detailEmpty').classList.add('hidden');
    $('detailBody').classList.remove('hidden');

    const table = state.selected.table;
    const vehicle = currentVehicle();
    $('detailId').textContent = row.id || '(未命名)';
    $('detailMeta').textContent = [
      vehicle && vehicle.vehicle_id != null ? `ID ${vehicle.vehicle_id}` : '',
      vehicle && vehicle.band ? `段 ${vehicle.band}` : '',
      table,
    ].filter(Boolean).join(' · ');
    $('vehicleFacts').innerHTML = vehicleFacts(vehicle, row);

    const wide = new Set(['additional_text', 'comment', 'parts', 'capacity_by_cargo',
      'train_flags', 'refittable_cargo_classes', 'cargo_allow_refit', 'cargo_disallow_refit',
      'graphics_parts', 'templates']);
    let html = '';
    for (const group of state.schema.groups) {
      const fields = state.schema.vehicle_fields.filter((field) => field.group === group.id);
      if (!fields.length) continue;
      const body = fields
        .filter((field) => field.name in row)
        .map((field) => fieldControl(field, row[field.name] ?? '',
          wide.has(field.name) || field.kind === 'text-long'))
        .join('');
      if (!body) continue;
      html += `<div class="group"><div class="group-head"><b>${esc(group.label)}</b>
        <span class="hint">${esc(group.note || '')}</span></div>
        <div class="group-body">${body}</div></div>`;
    }
    $('detailGroups').innerHTML = html;
    all('#detailGroups [data-field]').forEach((input) => {
      input.addEventListener('input', () => { state.dirty = true; });
      input.addEventListener('change', () => { state.dirty = true; });
    });
    loadPnmlPreview();
    renderAux();
  }

  /**
   * The row as the table stores it, with the server's display fields dropped.
   *
   * Every row the server sends is decorated with `_`-prefixed presentation keys
   * (`_index`, `_basename`, `_graphics`, `_label_used`, …).  They live in the same
   * object the editor posts back, and they are not columns, so sending them made
   * the save fail with 「未知的列」.  Dropping every leading underscore keeps this
   * in step with the server automatically instead of listing the keys by hand.
   */
  function stripRow(row) {
    const out = {};
    Object.keys(row || {}).forEach((name) => {
      if (!name.startsWith('_')) out[name] = row[name];
    });
    return out;
  }

  function collectDetail() {
    const row = stripRow(state.row);
    all('#detailGroups [data-field]').forEach((input) => {
      row[input.dataset.field] = input.value.trim();
    });
    return row;
  }

  async function openVehicle(table, id) {
    try {
      const data = await jsonFetch(`/vehicle?table=${encodeURIComponent(table)}&id=${encodeURIComponent(id)}`);
      state.selected = { table, id };
      state.row = data.row;
      state.dirty = false;
      state.liveryIndex = null;
      // tier 2 and 3 follow tier 1: pick the first paint scheme of this vehicle
      const first = (state.fleet.liveries || []).find((item) => (item.id || '').trim() === id);
      state.liveryIndex = first ? first._index : null;
      renderFleet();
      renderDetail();
      setStage('vehicle');
      setStatus(`已载入 ${id}`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function saveVehicle() {
    if (!state.selected) return;
    const row = collectDetail();
    try {
      const result = await jsonFetch('/save', {
        method: 'POST',
        body: JSON.stringify({
          table: state.selected.table,
          original: state.row,
          row,
          create: false,
        }),
      });
      if (!report(result, `已保存 ${state.selected.table} 中的 ${row.id}。下一步：生成车辆代码。`)) {
        return;
      }
      state.row = row;
      state.selected.id = row.id;
      state.dirty = false;
      applyState(result.state);
      renderDetail();
      renderSpriteTier();
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  // ---------------------------------------------------------------- modal
  function openModal(title, bodyHtml, onOk) {
    $('modalTitle').textContent = title;
    $('modalBody').innerHTML = bodyHtml;
    $('modal').classList.remove('hidden');
    $('modalOk').onclick = async () => {
      const ok = await onOk();
      if (ok !== false) closeModal();
    };
  }
  function closeModal() { $('modal').classList.add('hidden'); $('modalOk').onclick = null; }

  function newVehicleDialog() {
    const tables = state.schema.tables;
    const categories = state.schema.categories;
    const folders = [...new Set((state.fleet.vehicles || []).map((v) => v.folder))].sort();
    openModal('新建车辆', `
      <div class="grid2">
        <div class="field"><label>所在表 <span class="req">*</span></label>
          <select id="n_table">${tables.map((table) =>
            `<option value="${esc(table.id)}">${esc(table.label)}（${esc(table.id)}）</option>`).join('')}</select></div>
        <div class="field"><label>车辆 ID <span class="req">*</span></label>
          <input id="n_id" placeholder="ckd4a"></div>
        <div class="field"><label>显示名称 <span class="req">*</span></label>
          <input id="n_name" placeholder="CKD4A (Export)"></div>
        <div class="field"><label>gfx 子目录 <span class="req">*</span></label>
          <input id="n_folder" placeholder="diesel/df4c" list="n_folders">
          <div class="help">可以写多级，例如 diesel/df4c；最多 4 层，用 / 分隔。</div>
          <datalist id="n_folders">${folders.map((folder) =>
            `<option value="${esc(folder)}"></option>`).join('')}</datalist></div>
        <div class="field"><label>类别（仅机车表生效）</label>
          <select id="n_category">${categories.map((category) =>
            `<option value="${esc(category)}"${category === 'diesel' ? ' selected' : ''}>${esc(category)}</option>`).join('')}</select></div>
      </div>
      <p class="hint">每台车固定为 <span class="mono">2 + 车身 + 2</span> 三段，车身长度在「车辆明细」里用
      <span class="mono">parts</span> 改。创建后可在明细里补齐其余列。ID 段由所在表与类别决定，不用手填。</p>
    `, async () => {
      const table = $('n_table').value;
      const id = ($('n_id').value || '').trim().toLowerCase();
      const row = { id, name_string: ($('n_name').value || '').trim(), folder: ($('n_folder').value || '').trim() };
      const category = $('n_category').value;
      if (table === 'locomotives.csv') row.category = category;
      else row.folder = row.folder || (table === 'coaches.csv' ? 'coaches'
        : table === 'wagons.csv' ? 'wagons' : 'unit-wagons');
      row.folder = row.folder || (table === 'locomotives.csv' ? category : 'wagons');
      // start from the schema defaults so the first save already compiles
      for (const field of state.schema.vehicle_fields) {
        if (!(field.name in row) && field.default !== '' && field.default != null) {
          row[field.name] = String(field.default);
        }
      }
      try {
        const result = await jsonFetch('/save', {
          method: 'POST',
          body: JSON.stringify({ table, row, create: true }),
        });
        if (!result.ok) {
          setStatus('校验未通过：\n' + result.errors.join('\n'), 'error');
          return false;
        }
        applyState(result.state);
        setStatus(`已新建 ${id}。点「生成代码」写出它的 PNML；模型要自己放进 gfx/${row.folder || '?'}/。`, 'ok');
        await openVehicle(table, id);
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  function copyVehicleDialog() {
    if (!state.selected) return;
    const row = collectDetail();
    openModal('复制为新车辆', `
      <div class="grid2">
        <div class="field"><label>新车辆 ID <span class="req">*</span></label>
          <input id="c_id" placeholder="${esc(row.id)}_2"></div>
        <div class="field"><label>新显示名称</label>
          <input id="c_name" value="${esc(row.name_string || '')}"></div>
      </div>
      <p class="hint">同一张表内的所有列都会复制，之后可以逐项改。</p>
    `, async () => {
      const newId = ($('c_id').value || '').trim().toLowerCase();
      try {
        const result = await jsonFetch('/copy', {
          method: 'POST',
          body: JSON.stringify({ table: state.selected.table, id: row.id, new_id: newId,
            name_string: ($('c_name').value || '').trim() }),
        });
        if (!result.ok) {
          setStatus('校验未通过：\n' + (result.errors || []).join('\n'), 'error');
          return false;
        }
        applyState(result.state);
        setStatus(`已复制为 ${newId}。`, 'ok');
        await openVehicle(state.selected.table, newId);
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  function deleteVehicleDialog() {
    if (!state.selected) return;
    const row = collectStateSafeRow();
    const id = row.id;
    const table = state.selected.table;
    const dependents = (state.fleet.liveries || []).filter((item) => (item.id || '').trim() === id)
      .concat((state.fleet.variants || []).filter((item) => (item.id || '').trim() === id));
    openModal('删除车辆', `
      <p>将从 <b>${esc(table)}</b> 中删除 <b>${esc(id)}</b>。</p>
      ${dependents.length ? `<p class="tag warn">还有 ${dependents.length} 行涂装 / 货运外观引用它，需要另行删除。</p>` : ''}
      <label class="check"><input type="checkbox" id="d_prune" checked>
        同时删除它的 .pnml、.vox 与已渲染的 PNG</label>
      <p class="hint">表里的行会被立即移除；生成的索引文件在下一次「生成代码」时刷新。</p>
    `, async () => {
      try {
        const result = await jsonFetch('/delete', {
          method: 'POST',
          body: JSON.stringify({ table, id, prune: $('d_prune').checked }),
        });
        applyState(result.state);
        state.selected = null;
        state.row = null;
        renderDetail();
        setStatus(`已删除 ${id}${result.removed.length ? `，清理 ${result.removed.length} 个文件` : ''}。`
          + (dependents.length ? ` 注意：仍有 ${dependents.length} 行涂装/外观引用它。` : ''), 'ok');
        setStage('fleet');
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  function collectStateSafeRow() {
    return state.row || (state.selected ? { id: state.selected.id } : {});
  }

  // ------------------------------------------------- tier 2: 涂装管理
  /** The livery rows of the vehicle tier 1 is showing, in table order. */
  function liveriesOf(vehicleId) {
    return (state.fleet.liveries || []).filter((row) => (row.id || '').trim() === vehicleId);
  }

  /** The text a string constant resolves to, for display next to the field. */
  function stringContent(constant) {
    const name = (constant || '').trim();
    if (!name) return '';
    const entry = (state.strings || []).find((item) => item.constant === name);
    if (!entry) return '';
    const parts = [];
    if (entry.chinese) parts.push(entry.chinese);
    if (entry.english && entry.english !== entry.chinese) parts.push(entry.english);
    return parts.map((text) => esc(text)).join(' <span class="unit">/</span> ');
  }

  /** Every string the language table defines, so a livery can be pointed at a
   * label without leaving the page. */
  function stringOptions(current) {
    const known = (state.strings || []);
    const value = (current || '').trim();
    const options = ['<option value=""></option>'].concat(known.map((entry) => {
      const label = entry.chinese || entry.english || '';
      return `<option value="${esc(entry.constant)}"${entry.constant === value ? ' selected' : ''
        }>${esc(liveryLabel(entry.constant))}${label ? ' · ' + esc(label) : ''}</option>`;
    }));
    if (value && !known.some((entry) => entry.constant === value)) {
      options.push(`<option value="${esc(value)}" selected>${esc(liveryLabel(value))}（不在字符串表中）</option>`);
    }
    return options.join('');
  }

  /** A livery label is written LV_<NAME>; the code constant is STR_LV_<NAME>.
   * Show the short form in the picker so the field matches data/liveries.csv. */
  function liveryLabel(constant) {
    const name = (constant || '').trim();
    return name.startsWith('STR_LV_') ? name.slice(4) : name;
  }

  /** Where a livery row's model lives, and whether it is there. */
  function modelBadge(row) {
    const basename = row._basename || '';
    if (!row._folder) {
      return `<span class="bad">这台车没有 gfx 子目录</span>`;
    }
    if (!row._vox && !row._png) {
      return `<span class="bad">缺 ${esc(basename)}.vox</span>`;
    }
    if (!row._vox) {
      return `<span class="tag warn">有 PNG 但没有 .vox</span>`;
    }
    return row._png
      ? `<span class="tag ok">已渲染</span>`
      : `<span class="tag warn">.vox 就绪，未渲染</span>`;
  }

  /** The short table-language name of an NML variable, e.g. "pos". */
  function shortVariable(name) {
    return String(name || '')
      .replace('position_in_consist_from_end', 'tailpos')
      .replace('position_in_consist', 'pos')
      .replace('num_vehs_in_consist', 'consist')
      .replace('position_in_articulated_veh', 'unitpos');
  }

  /**
   * One section's rules as nested indented rows, matching the generated NML.
   *
   * The two things a row needs come from different places, which is why the
   * parent's variable is passed down: a node's `case` is a value of the variable
   * its *parent* switch selects on, while `selector`/`selector_below` is the
   * variable this node's own switch selects on.  Reading them off one node would
   * label `consist 0..6` as if it were a position.
   */
  function ruleTreeHtml(section) {
    const branch = (node, depth, isSwitch, parentVariable) => {
      const own = shortVariable(node.selector || node.selector_below);
      // the condition that led here belongs to the switch above this node
      const lead = (parentVariable && node.case)
        ? `${esc(shortVariable(parentVariable))} ${esc(node.case)}` : '';
      if (isSwitch) {
        const head = `<div class="rule-row" style="--depth:${depth}">
          <span class="tag cyan">${lead ? lead + '：' : ''}按 ${esc(own || '?')} 判断</span></div>`;
        return head + (node.children || []).map(
          (child) => branch(child, depth + 1, (child.children || []).length > 0, own)).join('');
      }
      return `<div class="rule-row" style="--depth:${depth}">
        <span class="tag${lead ? '' : ' cyan'}">${lead
        ? `${lead} → ${mono(node.basename)}`
        : `其余情况 → ${mono(node.basename)}`}</span></div>`;
    };
    const rows = (section.roots || []).map(
      (root) => branch(root, 0, true, '')).join('');
    if (!rows) {
      return `<div class="rule-row"><span class="tag">这一段隐形（用 empty_sprites）</span></div>`;
    }
    return rows;
  }

  // ------------------------------------------------------------------------
  // 分节图像规则的图形编辑器
  //
  // 这里的每一个控件都对应生成出来的 NML 的一部分：一个「块」就是一个 switch，
  // 块里的每一行是一个 case，行的「目标」要么是一张精灵（return spriteset…），
  // 要么是「再筛一层」（return 下一个 switch）。界面上搭出来的树会交给服务端
  // 用生成器自己的解析器写回单元格并重新解析，所以屏幕上看到的永远是编译时
  // 真正会读到的内容。
  // ------------------------------------------------------------------------

  const RULE_VARIABLES = [
    ['position_in_consist', 'pos', '整列第几节'],
    ['position_in_consist_from_end', 'tailpos', '从尾数第几节'],
    ['num_vehs_in_consist', 'consist', '整列共几节'],
    ['position_in_articulated_veh', 'unitpos', '本车第几段'],
  ];

  /**
   * 一个区间在 NML 里的写法；与 genpnml.predicate_selector 一一对应。
   *
   * 只做生成器能**原样存回**的那几种：一个区间在表格里只有 `<=n`、`==n`、
   * `>=n` 和 `low..high` 四种写法。`pos<2` 和 `pos>2` 是 `<=1` 和 `>=3` 的
   * 同义词，生成器一写回就变成后者，所以下拉框里不提供——提供了就会「选了又跳回
   * 别的符号」。上下都有界的 `3..8` 没有任何运算符能表达（`pos>=3` 和 `pos<=8`
   * 是两个条件，而同一个变量不能在一条路径上选两次），所以它是单独的一种。
   */
  function caseOf(operator, value, upper) {
    const clamp = (input) => Math.max(0, Math.min(255, Number(input) || 0));
    const n = clamp(value);
    if (operator === '==') return String(n);
    if (operator === '..') {
      const high = clamp(upper);
      return n === high ? String(n) : `${n}..${high}`;
    }
    // The control no longer offers `<` and `>`, so these two are only reached if
    // something else calls this with a spelling the cell language still accepts;
    // they are translated to the equivalent the storage keeps rather than
    // silently treated as `<=`.
    if (operator === '<') return caseOf('<=', Math.max(1, n) - 1);
    if (operator === '>') return caseOf('>=', Math.min(254, n) + 1);
    const low = operator === '>=' ? n : 0;
    const high = operator === '>=' ? 255 : n;
    return low === high ? String(low) : `${low}..${high}`;
  }

  /** 数值框允许的范围；`==` 和 `..` 的两个框都是全范围。 */
  function valueBounds() {
    return [0, 255];
  }

  /** 反过来：把一个区间拆成下拉框和输入框要显示的样子。 */
  function splitCase(text) {
    const value = String(text ?? '');
    const range = /^(\d+)\.\.(\d+)$/.exec(value);
    if (range) {
      const low = Number(range[1]); const high = Number(range[2]);
      if (low === high) return { operator: '==', value: low, low, high, raw: value };
      if (low === 0) return { operator: '<=', value: high, low, high, raw: value };
      if (high === 255) return { operator: '>=', value: low, low, high, raw: value };
      return { operator: '..', value: low, low, high, raw: value };
    }
    if (/^\d+$/.test(value)) {
      return { operator: '==', value: Number(value), low: Number(value),
        high: Number(value), raw: value };
    }
    return { operator: '', value: 0, low: 0, high: 0, raw: value };
  }

  function newLeaf(basename) {
    return { selector: '', case: '', basename: basename || '', selector_below: '',
      children: [] };
  }

  /**
   * 一个还没被占用的区间，用来做新行的占位。
   *
   * 只取「最小值」是不够的：如果这一段已经有 `consist<=6`，那么 `consist==1`
   * 落在它里面，生成器会报「被前面的条件完全覆盖，永远不会生效」。所以这里先
   * 把已有区间摊开，找一个真正没被覆盖的值。
   */
  function nextFreeCase(node) {
    const used = node.children.filter((child) => child.case).map((child) => {
      const part = splitCase(child.case);
      if (part.operator === '==') return [part.value, part.value];
      if (part.operator === '<=') return [0, part.value];
      if (part.operator === '>=') return [part.value, 255];
      if (part.operator === '..') return [part.low, part.high];
      return [0, 255];                      // 认不出来的区间，当作全覆盖
    });
    for (let value = 0; value < 256; value += 1) {
      if (!used.some(([low, high]) => value >= low && value <= high)) {
        return caseOf('==', value);
      }
    }
    return caseOf('==', 0);
  }

  /** 「再筛一层」挂出来的新开关：先给一个区间和一个兜底，免得是空开关。 */
  function newSubSwitch(variable, basename) {
    return { selector: '', case: '', basename: '', selector_below: variable,
      children: [{ ...newLeaf(basename), case: caseOf('==', 0) }, newLeaf(basename)] };
  }

  /** 一段的规则树：null = 完全没有规则，[] = 这一整段隐形。 */
  function treeFromReport(report) {
    if (!report || !report.set || report.error) return null;
    return report.sections.map((section) => section.roots || []);
  }

  function ruleVariables(node) {
    const own = node.selector || node.selector_below || '';
    return RULE_VARIABLES.some((item) => item[0] === own) ? own
      : (node.selector ? '' : 'position_in_consist');
  }

  function variableSelect(node, slot, isBranch) {
    const current = node.selector || node.selector_below || '';
    const options = RULE_VARIABLES.map(([name, short, about]) =>
      `<option value="${name}"${name === current ? ' selected' : ''}>${short} · ${esc(about)}</option>`);
    if (!RULE_VARIABLES.some((item) => item[0] === current)) {
      options.unshift(`<option value="${esc(current)}" selected>${esc(current || '?')}</option>`);
    }
    return `<select data-rule-field="selector" data-slot="${slot}"
      data-branch="${isBranch ? 1 : 0}">${options.join('')}</select>`;
  }

  function modelSelect(node, slot, basenames, fallback) {
    const current = node.basename || '';
    const known = basenames.includes(current) || !current;
    const options = [`<option value=""${current ? '' : ' selected'}>— 选一张 —</option>`]
      .concat(known ? [] : [`<option value="${esc(current)}" selected>${esc(current)}</option>`])
      .concat(basenames.map((name) =>
        `<option value="${esc(name)}"${name === current ? ' selected' : ''}>${esc(name)}</option>`));
    return `<select data-rule-field="model" data-slot="${slot}" title="${esc(fallback)}">
      ${options.join('')}</select>`;
  }

  /**
   * 一个 switch 块。`isTop` 决定它的兜底能不能是「再筛一层」：
   * 串联的下一层开关只能挂在最外层开关的兜底上，写在里面表格语言表达不出来。
   */
  function switchBlock(card, node, slot, isTop, basenames) {
    const rows = node.children.map((child, index) => ({ child, index }))
      .filter((item) => item.child.case)
      .map(({ child, index }) => {
        const part = splitCase(child.case);
        const nested = Boolean(child.selector_below);
        const slotOfChild = registerSlot(card, child);
        const bounds = valueBounds();
        const variable = esc(shortVariable(node.selector || node.selector_below));
        // The list holds only the operators the cell can store unchanged.  `<`
        // and `>` are not among them: they are `<=`/`>=` with the number moved by
        // one, so the generator writes the equivalent back and the control would
        // appear to jump to another symbol the moment it was used.
        const operators = ['<=', '==', '>=', '..'];
        const amount = part.operator === '..'
          ? `<input type="number" min="${bounds[0]}" max="${bounds[1]}" value="${esc(part.low)}"
               data-rule-field="value" data-slot="${slotOfChild}" title="区间下限">
             <span class="rule-unit">..</span>
             <input type="number" min="${bounds[0]}" max="${bounds[1]}" value="${esc(part.high)}"
               data-rule-field="value-high" data-slot="${slotOfChild}" title="区间上限">
             <span class="rule-unit">${variable}</span>`
          : `<input type="number" min="${bounds[0]}" max="${bounds[1]}" value="${esc(part.value)}"
               data-rule-field="value" data-slot="${slotOfChild}">
             <span class="rule-unit">${variable}</span>`;
        return `<div class="rule-case">
          <span class="rule-when">当</span>
          <select data-rule-field="operator" data-slot="${slotOfChild}"
            title="一个区间在表格里只有这四种写法；&lt; 与 &gt; 会被写成等价的 &lt;= / &gt;=">
            ${operators.map((op) =>
              `<option value="${op}"${op === part.operator ? ' selected' : ''}>${op === '..' ? '区间' : esc(op)}</option>`).join('')}
          </select>
          ${amount}
          ${part.operator ? '' : `<span class="tag warn" title="认不出来的区间写法，请用「直接编辑文本」">区间 ${esc(part.raw)} 无法编辑</span>`}
          <span class="rule-arrow">→</span>
          ${nested
            ? `<span class="tag cyan">再筛一层 · ${esc(shortVariable(child.selector_below))}</span>
               <button data-rule-action="unfold" data-slot="${slotOfChild}"
                 title="把这一层收起来，改回选一张图">改成一张图</button>`
            : modelSelect(child, slotOfChild, basenames, '这一区间显示的模型')}
          ${nested ? '' : `<button data-rule-action="fold" data-slot="${slotOfChild}"
            title="在这个区间里再按一个变量细分">再筛一层</button>`}
          <button class="danger" data-rule-action="drop-case" data-index="${index}"
            data-slot="${slot}">✕</button>
        </div>${nested ? switchBlock(card, child, slotOfChild, false, basenames) : ''}`;
      }).join('');

    const defaults = node.children.map((child, index) => ({ child, index }))
      .filter((item) => !item.child.case);
    const fallback = defaults.length ? defaults[0].child : null;
    let fallbackHtml;
    if (!fallback) {
      fallbackHtml = `<div class="rule-case default">
        <span class="rule-when">其余</span><span class="rule-arrow">→</span>
        <span class="hint">没有兜底：都不匹配时这一段隐形</span>
        <button data-rule-action="add-default" data-slot="${slot}">加兜底</button>
        ${isTop ? `<button data-rule-action="chain" data-slot="${slot}"
          title="其余的值交给下一层开关判断">再筛一层</button>` : ''}
      </div>`;
    } else {
      const slotOfFallback = registerSlot(card, fallback);
      const nested = Boolean(fallback.selector_below);
      fallbackHtml = `<div class="rule-case default">
        <span class="rule-when">其余</span><span class="rule-arrow">→</span>
        ${nested
          ? `<span class="tag cyan">再筛一层 · ${esc(shortVariable(fallback.selector_below))}</span>
             <button data-rule-action="unfold" data-slot="${slotOfFallback}">改成一张图</button>`
          : modelSelect(fallback, slotOfFallback, basenames, '兜底显示的模型')}
        ${nested || !isTop ? '' : `<button data-rule-action="fold" data-slot="${slotOfFallback}">再筛一层</button>`}
        <button class="danger" data-rule-action="drop-default" data-slot="${slot}">✕</button>
      </div>${nested ? switchBlock(card, fallback, slotOfFallback, false, basenames) : ''}`;
    }

    const cases = node.children.filter((child) => child.case).length;
    return `<div class="rule-block">
      <div class="rule-block-head">
        <span class="rule-switch">按</span>
        ${variableSelect(node, slot, false)}
        <span class="rule-switch">判断</span>
        <span class="hint">${cases} 个区间</span>
        <button data-rule-action="add-case" data-slot="${slot}">＋ 加区间</button>
      </div>
      ${rows}${fallbackHtml}
    </div>`;
  }

  /** 段内模式：隐形 / 一张图 / 按条件分。 */
  function sectionEditor(card, section, index, basenames) {
    const roots = section[index];
    const root = roots.length ? roots[0] : null;
    const mode = !roots.length ? 'hidden'
      : ((root && !root.selector) ? 'plain' : 'switch');
    const head = `<div class="rule-section-head">
      <span class="part">第 ${index + 1} 段</span>
      <span class="rule-modes">
        ${[['hidden', '隐形'], ['plain', '一张图'], ['switch', '按条件分']].map(([key, text]) =>
          `<button data-rule-mode="${key}" data-section="${index}"
            class="${mode === key ? 'primary' : ''}">${text}</button>`).join('')}
      </span>
    </div>`;
    let body;
    if (mode === 'hidden') {
      body = '<p class="hint">这一段不出图（生成器给 empty_sprites）。</p>';
    } else if (mode === 'plain') {
      const slot = registerSlot(card, root);
      body = `<div class="rule-case"><span class="rule-when">整段</span>
        <span class="rule-arrow">→</span>
        ${modelSelect(root, slot, basenames, '这一整段显示的模型')}</div>`;
    } else {
      body = switchBlock(card, root, registerSlot(card, root), true, basenames);
    }
    return `<div class="rule-section">${head}${body}</div>`;
  }

  /**
   * 把整棵编辑中的树登记成扁平表，控件用 data-slot 指回来。
   * 每次重画都会重新登记，所以控件拿到的永远是当前树里的节点。
   */
  function registerSlot(card, node) {
    const slots = card.__slots || (card.__slots = []);
    slots.push(node);
    return slots.length - 1;
  }

  function renderRuleEditor(card) {
    const host = card.querySelector('[data-rule-editor]');
    if (!host || card.__tree === undefined) return;
    card.__slots = [];
    const row = (state.fleet.liveries || []).find(
      (item) => item._index === Number(card.dataset.livery)) || {};
    const basenames = spriteRecords(row.id || (state.row && state.row.id) || '')
      .map((item) => item.basename);
    const sections = sectionCount();
    const tree = card.__tree;
    let html;
    if (tree === null) {
      html = `<div class="rule-empty">
        <p class="hint">这一行没有分节图像规则：只有车身段画涂装自己的整图，两端隐形。</p>
        <button data-rule-action="start" data-slot="-1">开始按段设置</button>
      </div>`;
    } else {
      html = tree.map((section, index) =>
        sectionEditor(card, tree, index, basenames)).join('');
    }
    if (card.__treeError) {
      html = `<div class="livery-error">${esc(card.__treeError)}</div>` + html;
    }
    host.innerHTML = html;
  }

  function sectionCount() {
    const parts = ((state.row && state.row.parts) || '').split(/[|,;]/)
      .map((piece) => piece.trim()).filter(Boolean);
    return parts.length || 3;
  }

  /** 把编辑中的树交给服务端写回单元格，再照它返回的规范树重画。 */
  async function flushRuleTree(card, rerender = true) {
    const tree = card.__tree;
    try {
      const report = await jsonFetch('/graphics-parts', {
        method: 'POST',
        body: JSON.stringify({
          parts: (state.row && state.row.parts) || '',
          sections: tree === null ? [] : tree,
        }),
      });
      if (report.error) {
        card.__treeError = report.error;
      } else {
        card.__treeError = '';
        const area = card.querySelector('[data-livery-field="graphics_parts"]');
        if (area) area.value = report.cell || '';
        const canonical = treeFromReport(report);
        if (canonical !== null) card.__tree = canonical;
      }
    } catch (error) {
      card.__treeError = error.message;
    }
    const preview = card.querySelector('[data-rule-preview]');
    if (preview && !card.__treeError) {
      const area = card.querySelector('[data-livery-field="graphics_parts"]');
      rulePreviewSerial += 1;
      preview.innerHTML = `<div class="hint">已写回：${mono((area && area.value) || '（空）')}</div>`;
    }
    if (rerender) renderRuleEditor(card);
  }

  function ruleEditorAction(card, button) {
    const action = button.dataset.ruleAction;
    const slot = Number(button.dataset.slot);
    const node = slot >= 0 ? (card.__slots || [])[slot] : null;
    const tree = card.__tree;
    const basenames = spriteRecords((state.row && state.row.id) || '')
      .map((item) => item.basename);
    const first = basenames[0] || '';
    if (action === 'start') {
      if (tree === null) {
        card.__tree = Array.from({ length: sectionCount() }, () => []);
        return flushRuleTree(card);
      }
      return undefined;
    }
    if (action === 'add-case' && node) {
      node.children.push({ ...newLeaf(first), case: nextFreeCase(node) });
    } else if (action === 'drop-case' && node) {
      node.children.splice(Number(button.dataset.index), 1);
    } else if (action === 'add-default' && node) {
      // 一段的开头只能有一个兜底；界面在没有兜底时才给这个按钮，这里再挡一次
      if (!node.children.some((child) => !child.case)) {
        node.children.push(newLeaf(first));
      }
    } else if (action === 'drop-default' && node) {
      node.children = node.children.filter((child) => child.case);
    } else if (action === 'fold' && node) {
      // 这一行的目标改成「再筛一层」：挂一个新的开关，先给一个区间加一个兜底
      node.basename = '';
      node.selector_below = 'position_in_consist';
      node.children = [{ ...newLeaf(first), case: caseOf('==', 0) }, newLeaf(first)];
    } else if (action === 'unfold' && node) {
      node.selector_below = '';
      node.children = [];
      node.basename = first;
    } else if (action === 'chain' && node) {
      // 最外层开关的兜底再挂一个开关，就是串联的下一层
      node.children.push(newSubSwitch('tailpos', first));
    } else {
      return undefined;
    }
    return flushRuleTree(card);
  }

  function ruleEditorField(card, field) {
    const slot = Number(field.dataset.slot);
    const node = (card.__slots || [])[slot];
    if (!node) return;
    if (field.dataset.ruleField === 'selector') {
      if (field.dataset.branch === '1') node.selector_below = field.value;
      else node.selector = field.value;
      // 换了变量，原来那些区间是按旧变量算的，清掉更安全
      if (node.children.length) node.children = node.children.filter((child) => child.case)
        .slice(0, 1);
    } else if (field.dataset.ruleField === 'operator') {
      const part = splitCase(node.case);
      if (field.value === '..') {
        // 「区间」 means bounded on *both* sides, so the ends have to leave the
        // anchors: `0..6` IS `<=6` and is written back as `<=`, which would leave
        // the author unable to reach range mode at all.  Widen to a real interval
        // and let them adjust it -- the two boxes show what happened.
        const low = Math.min(Math.max(1, part.low), 253);
        node.case = caseOf('..', low, Math.min(Math.max(part.high, low + 1), 254));
      } else {
        // the number the author can see stays put; the operator reinterprets it
        node.case = caseOf(field.value, part.value);
      }
      return flushRuleTree(card);
    } else if (field.dataset.ruleField === 'value'
               || field.dataset.ruleField === 'value-high') {
      const part = splitCase(node.case);
      if (part.operator === '..') {
        const low = field.dataset.ruleField === 'value' ? field.value : part.low;
        const high = field.dataset.ruleField === 'value-high' ? field.value : part.high;
        node.case = caseOf('..', low, high);
      } else {
        node.case = caseOf(part.operator || '<=', field.value);
      }
      // 回写之后服务端会把区间规范化，树被换成新的节点，所以必须重画一遍：
      // 否则后面点「删除」之类的按钮拿着的是旧节点，会点不动或点错地方。
      return flushRuleTree(card);
    } else if (field.dataset.ruleField === 'model') {
      node.basename = field.value;
    } else {
      return;
    }
    return flushRuleTree(card);
  }

  function ruleEditorMode(card, mode, index) {
    const basenames = spriteRecords((state.row && state.row.id) || '')
      .map((item) => item.basename);
    const first = basenames[0] || '';
    const tree = card.__tree;
    if (tree === null) return undefined;
    if (mode === 'hidden') tree[index] = [];
    else if (mode === 'plain') tree[index] = [newLeaf(first)];
    else if (!tree[index].length || !tree[index][0].selector) {
      // 一个能写回表格的起点：按整列节数分两次，两张图先用同一个模型占位。
      // 只有兜底、没有区间的开关写回表格会退化成「整段一张图」，那样这个模式
      // 一保存就没了，所以这里直接给出一个带区间的开关。
      tree[index] = [{ selector: 'num_vehs_in_consist', case: '', basename: '',
        selector_below: '',
        children: [{ ...newLeaf(first), case: caseOf('<=', 6) }, newLeaf(first)] }];
    }
    card.__tree = tree;
    return flushRuleTree(card);
  }


  function rulePreview(report) {
    if (!report || !report.set) {
      return `<span class="hint">未设置：只有车身段出图，两端隐形，整列同图。</span>`;
    }
    if (report.error) {
      return `<div class="livery-error">规则解析失败：${esc(report.error)}</div>`;
    }
    const sections = report.sections.map((section) => `
      <div class="section-rule">
        <span class="part">第 ${section.position + 1} 段</span>
        ${ruleTreeHtml(section)}
      </div>`).join('');
    return `<div class="rule-preview">${sections}</div>`;
  }

  /** Tier 3 shows one livery's model and rules, so tier 2 renders the editor. */
  function renderAux() {
    const container = $('liveryList');
    if (!container) return;
    if (!state.selected || !state.row) {
      container.innerHTML = `<div class="empty"><p>先在上面选一台车。</p>
        <p class="hint">涂装是某台车的一种模型，所以这一层跟着车辆属性走。</p></div>`;
      $('spriteTier').innerHTML = '<span class="hint">在上面的涂装表里选一行。</span>';
      return;
    }
    const vehicleId = state.row.id;
    const parts = (state.row.parts || '').split(/[|,;]/).map((piece) => piece.trim())
      .filter(Boolean);
    const sections = parts.length || 3;
    const rows = liveriesOf(vehicleId);
    if (state.liveryIndex == null || !rows.some((row) => row._index === state.liveryIndex)) {
      state.liveryIndex = rows.length ? rows[0]._index : null;
    }
    if (!rows.length) {
      container.innerHTML = `<div class="empty"><p><b>${esc(vehicleId)}</b> 还没有涂装行。</p>
        <p class="hint">没有任何行时生成器会造一个默认涂装，模型就是
        ${mono(`gfx/${esc(state.row.folder || '?')}/${esc(vehicleId)}.vox`)}。
        点「新增涂装」把它的名字、模型和分节规则写进 liveries.csv。</p></div>`;
      renderSpriteTier();
      return;
    }

    // one vehicle's rows are numbered from 0; the index is the refit menu order
    container.innerHTML = rows.map((row, ownIndex) => {
      const value = (name) => (row[name] ?? '');
      const selected = row._index === state.liveryIndex;
      const label = (row._constant || '').trim();
      const bad = label && !stringContent(label);
      const fields = state.schema.livery_fields.filter((field) => ![
        'id', 'sprite_suffix', 'string', 'graphics_parts', 'templates',
      ].includes(field.name));
      const report = row._graphics || { set: false, sections: [], error: '' };
      const shared = (row._label_used || 0) > 1;
      return `<div class="livery${selected ? ' sel' : ''}" data-livery="${row._index}">
        <div class="livery-head">
          <span class="livery-no"><b>#${ownIndex}</b> ${ownIndex === 0 ? '自动' : '可选'}</span>
          <span class="livery-model">
            <span class="hint">模型</span>
            ${mono(`${row._folder || '?'}/${row._basename || '—'}.vox`)}
            ${modelBadge(row)}
          </span>
          ${row._purchase ? `<span class="livery-model"
            title="车库购买列表里那台车的小图取本车第一行涂装；填「购买菜单小图后缀」可以让它借用另一张图">
            <span class="hint">菜单图</span>
            ${mono(`${row._folder || '?'}/${row._purchase_basename || '—'}.vox`)}
            ${row._purchase_png ? '<span class="tag ok">已渲染</span>'
              : '<span class="tag warn">缺这张图</span>'}
          </span>` : ''}
          ${shared ? `<span class="tag warn"
            title="涂装是靠这个字符串在改装菜单里区分的；同车多行共用一个字符串时，菜单里会显示成同一条">
            名称与另外 ${row._label_used - 1} 行重复</span>` : ''}
          <span class="livery-actions">
            <button data-livery-pick="${row._index}"
              class="${selected ? 'primary' : ''}">${selected ? '已选' : '查看图像'}</button>
            <button data-livery-move="up" title="上移一行（涂装序号跟着变）"
              ${ownIndex === 0 ? 'disabled' : ''}>&#9650;</button>
            <button data-livery-move="down" title="下移一行"
              ${ownIndex === rows.length - 1 ? 'disabled' : ''}>&#9660;</button>
            <button data-livery-copy="1" title="复制这一行为新涂装">复制</button>
            <button class="danger" data-livery-delete="1"
              title="从 liveries.csv 删除这一行">删除</button>
          </span>
        </div>

        <div class="livery-body">
          <div class="field">
            <label>精灵图后缀 <span class="unit">每行一个模型</span></label>
            <input data-livery-field="sprite_suffix" value="${esc(value('sprite_suffix'))}"
              placeholder="留空 = 直接用 ${esc(vehicleId)}">
          </div>

          <div class="field">
            <label>涂装名称 <span class="unit">LV_ 开头</span></label>
            <select data-livery-field="string" data-strings="1">${stringOptions(label)}</select>
            <div class="help" data-resolved="1">${bad
              ? '<span class="bad">这个常量不在字符串表里，编译会失败</span>'
              : (stringContent(label) || '<span class="hint">未命名：菜单里会显示常量本身</span>')}</div>
          </div>

          ${fields.map((field) => `<div class="field">
            <label>${esc(field.label)}</label>
            <input data-livery-field="${esc(field.name)}" value="${esc(value(field.name))}"
              placeholder="${esc(field.placeholder)}" title="${esc(field.help || '')}">
          </div>`).join('')}

          <div class="field livery-rules">
            <label>分节图像规则
              <span class="unit">${sections} 段，每一段一个开关</span></label>
            <div data-rule-editor="1"></div>
            <details class="rule-text">
              <summary>直接编辑文本（NML 语法）</summary>
              <textarea data-livery-field="graphics_parts"
                placeholder="第1段=…;第2段=…;第3段=…">${esc(value('graphics_parts'))}</textarea>
              <div class="help">用 <span class="mono">;</span> 分段（需与车辆的
                <span class="mono">parts</span> 段数一致，当前 ${sections} 段），
                段内用 <span class="mono">|</span> 分隔规则，写成
                <span class="mono">条件=…=基名</span> 或只写基名（兜底）。
                变量：<span class="mono">pos</span> /
                <span class="mono">tailpos</span> /
                <span class="mono">consist</span> /
                <span class="mono">unitpos</span>。留空则只有车身段出图、两端隐形。</div>
            </details>
            <div data-rule-preview="1">${rulePreview(report)}</div>
          </div>
        </div>

        <div class="livery-save">
          <button class="good" data-livery-save="1">保存本行</button>
          <span class="hint">保存后点「生成代码」，规则才会编译进 PNML。</span>
        </div>
      </div>`;
    }).join('');

    // the block editor starts from the tree the generator parsed for this row
    all('.livery', container).forEach((card) => {
      const row = (state.fleet.liveries || []).find(
        (item) => item._index === Number(card.dataset.livery));
      card.__tree = treeFromReport(row && row._graphics);
      card.__treeError = (row && row._graphics && row._graphics.error) || '';
      renderRuleEditor(card);
    });

    renderSpriteTier();
  }

  function selectedLivery() {
    if (state.liveryIndex == null) return null;
    return (state.fleet.liveries || []).find((row) => row._index === state.liveryIndex) || null;
  }

  /**
   * Preview the rule cell, and keep the switch blocks in step with it.
   *
   * The parse comes from the server, which runs the generator's own parser, so
   * the preview can never disagree with the NML the build produces.  A second
   * parser here would have to re-implement the path grammar, and the two would
   * drift apart the first time the grammar changed.  The same parse is what
   * fills the block editor, which is why editing either view updates the other.
   */
  function updateRulePreview(card, rebuildBlocks) {
    const area = card.querySelector('[data-livery-field="graphics_parts"]');
    const host = card.querySelector('[data-rule-preview]');
    if (!area || !host) return;
    const text = (area.value || '').trim();
    if (!text) {
      host.innerHTML = '<span class="hint">未设置：只有车身段出图，两端隐形，整列同图。</span>';
      if (rebuildBlocks) {
        card.__tree = null;
        card.__treeError = '';
        renderRuleEditor(card);
      }
      return;
    }
    const parts = ((state.row && state.row.parts) || '');
    const request = ++rulePreviewSerial;
    host.innerHTML = '<span class="hint">解析中…</span>';
    jsonFetch(`/rules?cell=${encodeURIComponent(text)}&parts=${encodeURIComponent(parts)}`)
      .then((report) => {
        // a later keystroke owns the box now, so drop this answer
        if (request !== rulePreviewSerial || !host.isConnected) return;
        host.innerHTML = rulePreview(report);
        if (rebuildBlocks) {
          const tree = treeFromReport(report);
          if (tree !== null) card.__tree = tree;
          card.__treeError = report.error || '';
          renderRuleEditor(card);
        }
      })
      .catch((error) => {
        if (request !== rulePreviewSerial) return;
        host.innerHTML = `<div class="livery-error">解析失败：${esc(error.message)}</div>`;
      });
  }

  function collectLiveryRow(container, row) {
    const out = stripRow(row);
    all('[data-livery-field]', container).forEach((input) => {
      out[input.dataset.liveryField] = input.value.trim();
    });
    return out;
  }

  async function saveLiveryRow(index) {
    const container = all('.livery').find((item) => Number(item.dataset.livery) === index);
    const original = (state.fleet.liveries || []).find((item) => item._index === index);
    if (!container || !original) return;
    // The block editor sends every change to the server and re-reads the cell it
    // renders to.  If that write-back failed, the blocks on screen are NOT what
    // the textarea holds, so saving the row would quietly discard the editor's
    // work -- the screen would look saved and the table would keep the old cell.
    if (container.__treeError) {
      setStatus('分节图像有改动没能写回表格：' + container.__treeError
        + '\n这一行的规则还是旧的，先处理上面的提示再保存（否则分节规则的改动会丢）。',
        'error');
      return;
    }
    const row = collectLiveryRow(container, original);
    try {
      const result = await jsonFetch('/save', {
        method: 'POST',
        body: JSON.stringify({ table: 'liveries.csv', original, row, index, create: false }),
      });
      if (!report(result, `已保存第 ${index + 1} 行涂装。`)) return;
      state.liveryIndex = index;
      applyState(result.state);
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function deleteLiveryRow(index) {
    const row = (state.fleet.liveries || []).find((item) => item._index === index);
    if (!row) return;
    try {
      const result = await jsonFetch('/delete', {
        method: 'POST',
        body: JSON.stringify({
          table: 'liveries.csv', index,
          key: [row.id, row.sprite_suffix, row.from_year, row.to_year],
        }),
      });
      state.liveryIndex = null;
      applyState(result.state);
      renderAux();
      setStatus(`已删除第 ${index + 1} 行涂装。`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function moveLiveryRow(index, direction) {
    try {
      const result = await jsonFetch('/move', {
        method: 'POST',
        body: JSON.stringify({ table: 'liveries.csv', index, direction }),
      });
      state.liveryIndex = result.moved ? result.index : index;
      applyState(result.state);
      renderAux();
      setStatus(result.moved ? '已调整行序，涂装序号随之改变。'
        : '不能移出这台车的涂装范围。', result.moved ? 'ok' : '');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  /** Prefill the new-livery dialog, suggesting a free sprite suffix. */
  function freeSuffix(vehicleId) {
    const taken = new Set(liveriesOf(vehicleId).map((row) => (row.sprite_suffix || '').trim()));
    if (!taken.has('')) return '';
    for (const candidate of ['a', 'b', 'c', 'green', 'blue', 'export']) {
      if (!taken.has(candidate)) return candidate;
    }
    let counter = 2;
    while (taken.has('v' + counter)) counter += 1;
    return 'v' + counter;
  }

  function addAuxRow(kind) {
    if (kind !== 'livery') {
      addVariantRow();
      return;
    }
    if (!state.selected || !state.row) {
      setStatus('先在「车队总览」里选一台车，再新增涂装。', 'error');
      return;
    }
    const vehicleId = state.row.id;
    const folder = state.row.folder || '?';
    const blank = {
      id: vehicleId,
      sprite_suffix: freeSuffix(vehicleId),
      string: 'STR_ORIGINAL',
      from_year: '0',
      to_year: '9999',
      purchase_suffix: '',
    };
    const fields = state.schema.livery_fields.filter((field) => field.name !== 'id');
    openModal(`为 ${vehicleId} 新增涂装`, `
      <p class="hint">每行涂装对应一个模型文件
        ${mono(`gfx/${esc(folder)}/${esc(vehicleId)}-&lt;后缀&gt;.vox`)}。
        后缀留空表示直接用 ${mono(`${esc(vehicleId)}.vox`)}。</p>
      <div class="grid2">${fields.map((field) => `<div class="field">
        <label>${esc(field.label)}</label>
        ${field.name === 'string'
          ? `<select id="a_${esc(field.name)}">${stringOptions(blank[field.name])}</select>`
          : `<input id="a_${esc(field.name)}" value="${esc(blank[field.name] ?? '')}"
              placeholder="${esc(field.placeholder)}">`}
        ${field.help ? `<div class="help">${esc(field.help)}</div>` : ''}</div>`).join('')}</div>
      <p class="hint">新增后把这一行的模型
        ${mono(`gfx/${esc(folder)}/${esc(vehicleId)}-&lt;后缀&gt;.vox`)}
        画好放进该目录，运行「生成代码」写出 PNML，再运行「渲染精灵图」就能看到它。</p>
    `, async () => {
      const row = { id: vehicleId };
      fields.forEach((field) => {
        const input = $('a_' + field.name);
        row[field.name] = input ? input.value.trim() : (blank[field.name] ?? '');
      });
      try {
        const result = await jsonFetch('/save', {
          method: 'POST',
          body: JSON.stringify({ table: 'liveries.csv', row, create: true }),
        });
        if (!report(result, `已为 ${vehicleId} 新增一行涂装。`)) return false;
        state.liveryIndex = result.index;
        applyState(result.state);
        renderAux();
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  function copyLiveryRow(index) {
    const row = (state.fleet.liveries || []).find((item) => item._index === index);
    if (!row || !state.row) return;
    const vehicleId = state.row.id;
    openModal(`复制涂装 #${index + 1}`, `
      <p class="hint">复制一行是为了做同车的另一种涂装，所以必须换一个模型后缀。</p>
      <div class="grid2">
        <div class="field"><label>精灵图后缀 <span class="req">*</span></label>
          <input id="cp_suffix" value="${esc(freeSuffix(vehicleId))}"></div>
        <div class="field"><label>涂装名称</label>
          <select id="cp_string">${stringOptions(row.string)}</select></div>
        <div class="field"><label>起始年份</label>
          <input id="cp_from" value="${esc(row.from_year || '0')}"></div>
        <div class="field"><label>结束年份</label>
          <input id="cp_to" value="${esc(row.to_year || '9999')}"></div>
      </div>
    `, async () => {
      const copy = { ...stripRow(row),
        sprite_suffix: ($('cp_suffix').value || '').trim(),
        string: $('cp_string').value,
        from_year: ($('cp_from').value || '').trim(),
        to_year: ($('cp_to').value || '').trim() };
      try {
        const result = await jsonFetch('/save', {
          method: 'POST',
          body: JSON.stringify({ table: 'liveries.csv', row: copy, create: true }),
        });
        if (!report(result, '已复制为新的涂装行。')) return false;
        state.liveryIndex = result.index;
        applyState(result.state);
        renderAux();
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  // ------------------------------------------- tier 4 helper: 货运外观表
  const VARIANT_AUX = {
    table: 'cargo_variants.csv',
    fields: () => state.schema.variant_fields,
    rows: () => state.fleet.variants || [],
    keys: (row) => [(row.id || '').trim(), (row.variant || '').trim()].join('\u0000'),
    blank: () => ({ id: '', variant: '', sprite_suffix: '', cargo_classes: 'bitmask(CC_BULK)',
      cargo_types: '', from_index: '0', to_index: '0', template: 'template_standard' }),
  };

  function renderVariants() {
    const container = $('variantList');
    if (!container) return;
    const rows = VARIANT_AUX.rows();
    if (!rows.length) {
      container.innerHTML = `<div class="empty"><p>cargo_variants.csv 还没有数据行。</p>
        <p class="hint">每一行是一种货物外观。</p></div>`;
      return;
    }
    const groups = new Map();
    for (const row of rows) {
      const key = (row.id || '').trim();
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    container.innerHTML = [...groups.entries()].map(([id, groupRows]) =>
      `<div class="aux-group"><div class="aux-head"><b>${esc(id)}</b>
        <span class="hint">${groupRows.length} 行</span></div>
        <div class="aux-rows">${groupRows.map((row) => `
          <div class="aux-row" data-table="cargo_variants.csv"
            data-key="${esc(VARIANT_AUX.keys(row))}" data-index="${row._index}">
            ${VARIANT_AUX.fields().filter((field) => field.name in row).map((field) =>
              `<div class="field"><label>${esc(field.label)}</label>
                <input data-field="${esc(field.name)}" value="${esc(row[field.name] ?? '')}"
                  placeholder="${esc(field.placeholder)}"
                  title="${esc(field.help || '')}"></div>`).join('')}
            <button class="danger" data-aux-delete="1">删除</button>
          </div>`).join('')}</div></div>`).join('');
  }

  async function saveVariantRow(container) {
    const row = {};
    all('[data-field]', container).forEach((input) => {
      row[input.dataset.field] = input.value.trim();
    });
    const index = Number(container.dataset.index);
    const original = VARIANT_AUX.rows().find((item) => item._index === index) || row;
    try {
      const result = await jsonFetch('/save', {
        method: 'POST',
        body: JSON.stringify({ table: 'cargo_variants.csv', original, row, index, create: false }),
      });
      if (!report(result, '已保存 cargo_variants.csv 的一行。')) return;
      applyState(result.state);
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function deleteVariantRow(index, key) {
    try {
      const result = await jsonFetch('/delete', {
        method: 'POST',
        body: JSON.stringify({ table: 'cargo_variants.csv', index, key: key.split('\u0000') }),
      });
      applyState(result.state);
      renderVariants();
      setStatus('已删除该行。', 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  function addVariantRow() {
    if (!state.fleet.counts['wagons.csv']) {
      setStatus('货运外观只能挂在货车上，wagons.csv 目前是空的。', 'error');
      return;
    }
    const blank = VARIANT_AUX.blank();
    openModal('新增货运外观行', `
      <div class="grid2">${VARIANT_AUX.fields().map((field) => `
        <div class="field"><label>${esc(field.label)}</label>
          <input id="a_${esc(field.name)}" value="${esc(blank[field.name] ?? '')}"
            placeholder="${esc(field.placeholder)}">
          ${field.help ? `<div class="help">${esc(field.help)}</div>` : ''}</div>`).join('')}</div>
    `, async () => {
      const row = {};
      VARIANT_AUX.fields().forEach((field) => {
        const input = $('a_' + field.name);
        row[field.name] = input ? input.value.trim() : (blank[field.name] ?? '');
      });
      try {
        const result = await jsonFetch('/save', {
          method: 'POST',
          body: JSON.stringify({ table: 'cargo_variants.csv', row, create: true }),
        });
        if (!report(result, '已新增一行到 cargo_variants.csv。')) return false;
        applyState(result.state);
        renderVariants();
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  // ------------------------------------------------ tier 3: 分节图像
  /** Every basename this vehicle's generator run needs, from the manifest. */
  function spriteRecords(vehicleId) {
    const vehicle = (state.fleet.vehicles || []).find((item) => item.id === vehicleId);
    return (vehicle && vehicle.sprites) || [];
  }

  function basenameStatus(vehicleId, basename) {
    const record = spriteRecords(vehicleId).find((item) => item.basename === basename);
    if (!record) return { known: false, vox: false, png: false, png_path: '' };
    return { known: true, vox: record.vox, png: record.png, png_path: record.png_path };
  }

  async function renderSpriteTier() {
    const host = $('spriteTier');
    if (!host) return;
    const row = state.row ? collectDetail() : null;
    if (!row) {
      host.innerHTML = '<span class="hint">先选择一台车。</span>';
      return;
    }
    const vehicleId = row.id;
    const livery = selectedLivery();
    const liveryBasename = livery ? livery._basename : vehicleId;
    const rules = (livery && livery._graphics) || { set: false, sections: [], error: '' };
    const order = liveriesOf(vehicleId).findIndex(
      (item) => livery && item._index === livery._index);

    // ---- which basenames does the generator actually need?
    const records = spriteRecords(vehicleId);
    const wanted = records.length ? records.map((item) => item.basename)
      : [liveryBasename].filter(Boolean);

    // ---- the rule table -------------------------------------------------
    let ruleHtml;
    if (rules.error) {
      ruleHtml = `<div class="livery-error">分节图像规则解析失败：${esc(rules.error)}</div>`;
    } else if (!rules.set) {
      ruleHtml = `<p class="hint">这一行没有设置分节图像规则，所以只出车身段的图，
        两端保持隐形；整列车用同一张图。要按整列位置换图（例如动车组头尾用不同模型），
        在<b>第 2 层</b>这一行的「分节图像规则」里填写。</p>`;
    } else {
      ruleHtml = `<div class="sections">${rules.sections.map((section) => `
        <div class="section-rule">
          <span class="part">第 ${section.position + 1} 段</span>
          ${ruleTreeHtml(section)}
        </div>`).join('')}</div>`;
    }

    // ---- the models -----------------------------------------------------
    const modelHtml = wanted.length ? wanted.map((basename) => {
      const status = basenameStatus(vehicleId, basename);
      const isLivery = basename === liveryBasename;
      const inRules = rules.set && rules.sections.some((section) =>
        (section.basenames || []).includes(basename));
      return `<div class="sprite-row${isLivery ? ' current' : ''}" data-basename="${esc(basename)}">
        <span class="name">${esc(basename)}</span>
        ${isLivery ? '<span class="tag cyan">这一行的模型</span>' : ''}
        ${inRules ? '<span class="tag">被本行规则引用</span>' : ''}
        <span>${status.vox
          ? '<span class="tag ok">.vox</span>'
          : `<span class="tag bad">缺 .vox</span>`}</span>
        <span>${status.png
          ? '<span class="tag ok">已渲染</span>'
          : '<span class="tag warn">未渲染</span>'}</span>
        ${status.png
          ? `<canvas data-sheet="${esc(status.png_path)}" width="96" height="96"></canvas>`
          : ''}
        <span class="hint">${mono(`gfx/${row.folder || '?'}/${basename}.vox`)}</span>
      </div>`;
    }).join('') : '<p class="hint">这台车还没有任何贴图基名。</p>';

    host.innerHTML = `
      <p class="hint">当前显示涂装 <b>#${order < 0 ? '?' : order} ·
        ${esc(livery ? livery._label || liveryBasename : liveryBasename)}</b> 的模型与规则。
        ${livery && livery._folder
          ? `文件位置：${mono(`gfx/${livery._folder}/`)}` : ''}</p>
      ${ruleHtml}
      <div class="sprites">${modelHtml}</div>
      <div class="row" style="margin-top:10px">
        <button data-action="render">渲染精灵图</button>
        <span class="hint">每个基名要有自己的 <span class="mono">.vox</span> 模型；
        缺少的会在上面标红。生成器不会替你造占位模型。</span>
      </div>`;
    all('#spriteTier canvas[data-sheet]').forEach((canvas) => {
      drawSheetCell(canvas, canvas.dataset.sheet, 4);
    });
  }

  /** Ask the server where each of the eight views sits inside the strip. */
  async function sheetLayout(path) {
    if (!state.sheets) state.sheets = {};
    if (!state.sheets[path]) {
      state.sheets[path] = jsonFetch('/sheet?path=' + encodeURIComponent(path))
        .catch(() => ({ views: [], error: '无法解析精灵图' }));
    }
    return state.sheets[path];
  }

  async function drawSheetCell(canvas, path, view) {
    const layout = await sheetLayout(path);
    const rect = (layout.views || [])[view]
      || (layout.views || [])[(layout.views || []).length - 1];
    const image = new Image();
    image.onload = () => {
      const context = canvas.getContext('2d');
      context.imageSmoothingEnabled = false;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = '#05080a';
      context.fillRect(0, 0, canvas.width, canvas.height);
      if (!rect) {
        context.fillStyle = '#4a1f1c';
        context.fillRect(0, 0, canvas.width, canvas.height);
        return;
      }
      const scale = Math.min(canvas.width / rect.width, canvas.height / rect.height);
      const drawWidth = rect.width * scale;
      const drawHeight = rect.height * scale;
      context.drawImage(image, rect.x, rect.y, rect.width, rect.height,
        (canvas.width - drawWidth) / 2, (canvas.height - drawHeight) / 2,
        drawWidth, drawHeight);
    };
    image.onerror = () => {
      const context = canvas.getContext('2d');
      context.fillStyle = '#4a1f1c';
      context.fillRect(0, 0, canvas.width, canvas.height);
    };
    image.src = API + '/file?path=' + encodeURIComponent(path);
  }

  function renderSpritePreview() {
    if (!state.selected || !state.row) {
      $('spritePreview').innerHTML = '<span class="hint">选择一台车后显示。</span>';
      $('viewTabs').classList.add('hidden');
      return;
    }
    const livery = selectedLivery();
    const basename = livery ? livery._basename : state.row.id;
    const record = spriteRecords(state.row.id).find((item) => item.basename === basename);
    const ready = record && record.png ? [record] : [];
    const preview = $('spritePreview');
    const tabs = $('viewTabs');
    if (!ready.length) {
      const any = spriteRecords(state.row.id).filter((sprite) => sprite.png);
      if (!any.length) {
        preview.innerHTML = '<span class="hint">这台车还没有渲染好的贴图，先运行「渲染精灵图」。</span>';
        tabs.classList.add('hidden');
        return;
      }
      state.spriteSheet = any[0].png_path;
    } else {
      state.spriteSheet = ready[0].png_path;
    }
    const allReady = spriteRecords(state.row.id).filter((sprite) => sprite.png);
    tabs.classList.remove('hidden');
    tabs.innerHTML = allReady.map((sprite) =>
      `<button data-sheet="${esc(sprite.png_path)}"
        class="${sprite.png_path === state.spriteSheet ? 'active' : ''}">${esc(sprite.basename)}</button>`).join('')
      + '<span class="hint">方向：</span>'
      + VIEW_NAMES.map((name, view) =>
        `<button data-view="${view}" class="${view === state.spriteView ? 'active' : ''
        }">${name}</button>`).join('');
    preview.innerHTML = `<canvas id="previewCanvas" width="${VIEW_PX * 2}"
      height="${VIEW_PX * 2}"></canvas>`;
    drawSheetCell($('previewCanvas'), state.spriteSheet, state.spriteView);
  }

  function onViewTabClick(event) {
    const button = event.target.closest('button');
    if (!button || !state.selected) return;
    if (button.dataset.sheet) state.spriteSheet = button.dataset.sheet;
    if (button.dataset.view !== undefined) state.spriteView = Number(button.dataset.view);
    all('#viewTabs button').forEach((item) => {
      if (item.dataset.sheet) item.classList.toggle('active', item.dataset.sheet === state.spriteSheet);
      else item.classList.toggle('active', Number(item.dataset.view) === state.spriteView);
    });
    const canvas = $('previewCanvas');
    if (canvas) drawSheetCell(canvas, state.spriteSheet, state.spriteView);
  }

  async function loadPnmlPreview() {
    if (!state.selected) return;
    const box = $('pnmlPreview');
    box.textContent = '读取中…';
    try {
      const data = await jsonFetch(`/pnml?table=${encodeURIComponent(state.selected.table)}`
        + `&id=${encodeURIComponent(state.selected.id)}`);
      if (data.text) {
        box.textContent = data.text;
      } else {
        box.innerHTML = `<span class="hint">${esc(data.note || '尚未生成。')}</span>
          <span class="hint">${esc(data.path || '')}</span>`;
      }
    } catch (error) {
      box.innerHTML = `<span class="hint">${esc(error.message)}</span>`;
    }
  }

  // ------------------------------------------------------- string table
  /** Strings the generated files and the hand written sources reference. */
  function usedConstants() {
    const used = new Set();
    for (const vehicle of state.fleet.vehicles || []) {
      // name_string is a plain display name, not a constant, so only a real
      // STR_ cell counts
      const name = (vehicle.name_string || '').trim();
      if (name.startsWith('STR_')) used.add(name);
    }
    for (const row of state.fleet.liveries || []) {
      // the server resolves the cell (LV_ -> STR_LV_, old names mapped across)
      if (row._constant) used.add(row._constant.trim());
    }
    return used;
  }

  const STRING_KINDS = [
    ['all', '全部'],
    ['livery', '涂装 LV_'],
    ['vehicle', '车辆名'],
    ['interface', '界面'],
  ];

  function renderStrings() {
    const container = $('stringList');
    if (!container) return;
    const rows = state.strings || [];
    const bar = $('stringFilters');
    if (bar) {
      const counts = { all: rows.length };
      for (const row of rows) counts[row.kind] = (counts[row.kind] || 0) + 1;
      bar.innerHTML = STRING_KINDS.map(([kind, label]) =>
        `<button data-string-kind="${kind}"
          class="${kind === state.stringFilter ? 'active' : ''}">${esc(label)}
          <span class="hint">${counts[kind] || 0}</span></button>`).join('')
        + `<span class="hint">涂装标签写成 <span class="mono">LV_名字</span>，
          代码里是 <span class="mono">STR_LV_名字</span>。</span>`;
    }

    const search = ($('stringSearch').value || '').trim().toLowerCase();
    const used = usedConstants();
    const shown = rows.filter((row) => {
      if (state.stringFilter !== 'all' && row.kind !== state.stringFilter) return false;
      if (!search) return true;
      return [row.constant, row.english, row.chinese].join(' ').toLowerCase().includes(search);
    });
    if (!shown.length) {
      const empty = state.stringFilter === 'livery' && !search
        ? `还没有 <span class="mono">LV_</span> 开头的涂装标签。点「新增字符串」建一个，
           或者在「车辆工作台」里新增涂装时直接填。`
        : '没有匹配的字符串。';
      container.innerHTML = `<div class="empty"><p>${empty}</p>
        <p class="hint">常量必须是 STR_ 开头的大写字母、数字与下划线（涂装标签写成 LV_名字）。</p></div>`;
      return;
    }
    container.innerHTML = shown.map((row) => {
      const constant = (row.constant || '').trim();
      const referenced = used.has(constant);
      const isLivery = row.kind === 'livery';
      const uses = row.livery_uses || 0;
      const duplicate = Boolean(row.livery_duplicate);
      const labelTag = uses
        ? `<span class="tag${duplicate ? ' warn' : ''}" title="${duplicate
          ? '同一台车有 ' + uses + ' 行涂装用这个标签；改装菜单里它们会显示成同一条，玩家分不出来'
          : '被 ' + uses + ' 行涂装使用'
            + (row.livery_vehicles > 1 ? '（分属 ' + row.livery_vehicles + ' 台车，各车菜单互不影响）' : '')}"
          >${uses} 个涂装${duplicate ? ' · 同车重名' : ''}</span>`
        : '';
      return `<div class="string-row ${referenced ? 'used' : 'unused'}"
          data-constant="${esc(constant)}" data-original="${esc(constant)}">
        <div class="field"><label>常量
            <span class="unit">${isLivery ? '涂装标签' : '代码里的引用名'}</span></label>
          <input data-string-field="constant" value="${esc(constant)}"
            class="constant"></div>
        <div class="field"><label>英文</label>
          <input data-string-field="english" value="${esc(row.english || '')}"></div>
        <div class="field"><label>中文</label>
          <input data-string-field="chinese" value="${esc(row.chinese || '')}"></div>
        <div class="livery-actions">
          ${isLivery ? labelTag : ''}
          <span class="tag${referenced ? ' ok' : ''}">${referenced ? '被引用' : '未引用'}</span>
          <button class="good" data-string-save="1">保存</button>
          <button class="danger" data-string-delete="1"
            ${referenced ? 'title="仍被引用，删除后编译会失败"' : ''}>删除</button>
        </div>
      </div>`;
    }).join('');
  }

  function collectStringRow(container) {
    const row = {};
    all('[data-string-field]', container).forEach((input) => {
      row[input.dataset.stringField] = input.value.trim();
    });
    row.original = container.dataset.original || '';
    return row;
  }

  async function saveStringRow(container) {
    const row = collectStringRow(container);
    try {
      const result = await jsonFetch('/string', { method: 'POST', body: JSON.stringify(row) });
      applyState(result.state);
      await reloadStrings();
      setStatus(`已保存 ${result.constant}。`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function deleteStringRow(container) {
    const constant = container.dataset.original || container.dataset.constant;
    try {
      const result = await jsonFetch('/string-delete', {
        method: 'POST', body: JSON.stringify({ constant }),
      });
      applyState(result.state);
      await reloadStrings();
      setStatus(`已删除 ${result.constant}。`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  function addStringRow() {
    openModal('新增字符串', `
      <p class="hint">常量是代码里的引用名，例如涂装写 <span class="mono">STR_EXPORT_BLUE</span>
      就会显示这里的文字。新增的行会被 ${'make gen'} 保留。</p>
      <div class="grid2">
        <div class="field"><label>常量 <span class="req">*</span></label>
          <input id="s_constant" placeholder="STR_EXPORT_BLUE"></div>
        <div class="field"><label>英文</label>
          <input id="s_english" placeholder="Export blue"></div>
        <div class="field"><label>中文</label>
          <input id="s_chinese" placeholder="出口蓝"></div>
      </div>
    `, async () => {
      const payload = {
        constant: ($('s_constant').value || '').trim().toUpperCase(),
        english: ($('s_english').value || '').trim(),
        chinese: ($('s_chinese').value || '').trim(),
      };
      try {
        const result = await jsonFetch('/string', { method: 'POST', body: JSON.stringify(payload) });
        applyState(result.state);
        await reloadStrings();
        setStatus(`已新增 ${result.constant}，现在可以在涂装里选它了。`, 'ok');
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  async function reloadStrings() {
    try {
      const table = await jsonFetch('/strings');
      // `strings` is the complete list, `kind` included; the kind filter needs
      // it, so this is the only copy the browser keeps
      state.strings = table.strings || [];

      state.stringComments = table.comments || [];
      renderStrings();
      if (state.selected) renderAux();
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  // ------------------------------------------------------------------ jobs
  function appendLines(job, lines) {
    for (const entry of lines) {
      const line = document.createElement('div');
      const text = entry.text || '';
      line.className = entry.stream === 'meta' ? 'l-meta'
        : /error|ERROR|错误|Traceback/i.test(text) ? 'l-err' : /ok|完成|success/i.test(text) ? 'l-ok' : '';
      line.textContent = text;
      job.append(line);
    }
    job.scrollTop = job.scrollHeight;
  }

  // ------------------------------------------------------------------ jobs
  async function runAction(action) {
    const buttons = all(`[data-action="${action}"]`);
    buttons.forEach((button) => { button.disabled = true; });
    const target = action === 'check' ? $('checkConsole') : $('buildConsole');
    const also = $('runConsole');
    const header = `$ ${action}\n`;
    if (target) target.textContent = header;
    also.textContent = header;
    setStatus(`正在执行：${action} …`, 'busy');
    try {
      const started = await jsonFetch('/run', {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      let cursor = 0;
      let done = false;
      while (!done) {
        const result = await jsonFetch(`/job?job=${started.job}&cursor=${cursor}`);
        cursor = result.cursor;
        if (target) appendLines(target, result.lines);
        appendLines(also, result.lines);
        if (result.status !== 'running') {
          done = true;
          const ok = result.status === 'ok';
          setStatus(`${started.label}：${ok ? '成功' : '失败'}（${result.elapsed}s）`,
            ok ? 'ok' : 'error');
          if (action === 'build') {
            $('buildResult').innerHTML = ok
              ? `<p class="tag ok">编译成功</p>` : `<p class="tag bad">编译失败，见下方日志</p>`;
          }
          await loadFleet();
          if (action === 'build') {
            const size = state.fleet.grf && state.fleet.grf.size;
            $('buildResult').innerHTML = `<p class="tag ${ok ? 'ok' : 'bad'}">`
              + `${ok ? '编译成功' : '编译失败'}</p>`
              + `<p class="hint">chinasettrainsexport.grf：${size ? size + ' 字节' : '不存在'}</p>`;
          }
          if (state.selected) { loadPnmlPreview(); renderSpritePreview(); }
        } else {
          await new Promise((resolve) => setTimeout(resolve, 600));
        }
      }
    } catch (error) {
      setStatus(error.message, 'error');
      if (target) appendLines(target, [{ stream: 'stderr', text: error.message }]);
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  // ---------------------------------------------------------------- stages
  const STAGE_META = {
    fleet: ['车队总览', '全车队的概览与入口。点一台车进入三层工作台。', []],
    vehicle: ['车辆工作台',
      '同一页三层：1 车辆属性 → 2 涂装管理 → 3 分节图像。', []],
    variant: ['货运外观', '货车按货物类别与装载量切换贴图。', []],
    strings: ['字符串表', '常量、英文与中文；新增的行会被生成器保留。',
      [['check', '运行一致性检查']]],
    check: ['一致性检查', '字符串表双向核对与贴图引用检查。', [['check', '运行检查']]],
    build: ['构建 GRF', '预处理、编译，产出可进游戏的 grf。', [['build', '编译 GRF']]],
    guide: ['指南', '仓库内文档的离线浏览。', []],
  };

  function setStage(stage) {
    // the vehicle workspace needs a vehicle: fall back to the fleet overview
    if (stage === 'vehicle' && !state.selected) {
      setStatus('先在「车队总览」里点一台车。');
      stage = 'fleet';
    }
    state.stage = stage;
    all('[data-panel]').forEach((panel) =>
      panel.classList.toggle('hidden', panel.dataset.panel !== stage));
    all('#stageNav button').forEach((button) =>
      button.classList.toggle('active', button.dataset.stage === stage));
    const meta = STAGE_META[stage];
    $('stageTitle').textContent = meta[0];
    $('stageDescription').textContent = meta[1];
    $('stageTools').innerHTML = meta[2].map(([action, label]) =>
      `<button class="primary" data-action="${action}">${esc(label)}</button>`).join('');
    if (stage === 'guide' && !state.doc) loadDoc('docs/guide-zh.md');
    if (stage === 'variant') renderVariants();
    if (stage === 'strings') renderStrings();
    if (stage === 'vehicle') renderSpritePreview();
  }

  // ----------------------------------------------------------------- guide
  async function loadDoc(path) {
    const view = $('docView');
    view.textContent = '读取中…';
    all('.doc-tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.doc === path));
    try {
      const data = await jsonFetch('/text?path=' + encodeURIComponent(path));
      state.doc = path;
      view.innerHTML = markdown(data.text);
    } catch (error) {
      view.innerHTML = `<span class="hint">${esc(error.message)}</span>`;
    }
  }

  function markdown(text) {
    const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
    const out = [];
    let index = 0;
    const inline = (value) => esc(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g,
        (match, label, href) => /^https?:/.test(href)
          ? `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>` : label);
    while (index < lines.length) {
      const line = lines[index];
      if (/^```/.test(line)) {
        const buffer = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index])) { buffer.push(lines[index]); index += 1; }
        index += 1;
        out.push('<pre><code>' + esc(buffer.join('\n')) + '</code></pre>');
        continue;
      }
      if (/^\s*$/.test(line)) { index += 1; continue; }
      const heading = /^(#{1,4})\s+(.*)$/.exec(line);
      if (heading) {
        const level = Math.min(4, heading[1].length);
        out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }
      if (/^>\s?/.test(line)) {
        const buffer = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          buffer.push(lines[index].replace(/^>\s?/, '')); index += 1;
        }
        out.push('<blockquote>' + inline(buffer.join(' ')) + '</blockquote>');
        continue;
      }
      if (/^\s*\|/.test(line)) {
        const rows = [];
        while (index < lines.length && /^\s*\|/.test(lines[index])) { rows.push(lines[index]); index += 1; }
        const cells = (row) => row.replace(/^\s*\|/, '').replace(/\|\s*$/, '')
          .split('|').map((cell) => cell.trim());
        const head = cells(rows[0]);
        const body = rows.slice(/^\s*\|[\s:|-]+\|\s*$/.test(rows[1] || '') ? 2 : 1);
        out.push('<table><thead><tr>' + head.map((cell) => `<th>${inline(cell)}</th>`).join('')
          + '</tr></thead><tbody>' + body.map((row) =>
            '<tr>' + cells(row).map((cell) => `<td>${inline(cell)}</td>`).join('') + '</tr>').join('')
          + '</tbody></table>');
        continue;
      }
      const list = /^\s*([-*]|\d+\.)\s+/.exec(line);
      if (list) {
        const ordered = /\d/.test(list[1]);
        const items = [];
        while (index < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*([-*]|\d+\.)\s+/, '')); index += 1;
        }
        out.push(`<${ordered ? 'ol' : 'ul'}>` + items.map((item) =>
          `<li>${inline(item)}</li>`).join('') + `</${ordered ? 'ol' : 'ul'}>`);
        continue;
      }
      const paragraph = [line];
      index += 1;
      while (index < lines.length && !/^\s*$/.test(lines[index])
        && !/^[#>|`]/.test(lines[index]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[index])) {
        paragraph.push(lines[index]); index += 1;
      }
      out.push('<p>' + inline(paragraph.join(' ')) + '</p>');
    }
    return out.join('\n');
  }

  /**
   * Whether a click inside a fleet card should open that vehicle.
   *
   * The whole card is a big "编辑这台车" target, but it carries controls of its
   * own -- the ▲▼ order buttons, 折叠到, 折叠项名称 -- and a click on one of them
   * has to work that control.  Without this the browser navigated to the vehicle
   * workbench the moment the dropdown was opened, so the value could not be
   * changed from the overview at all.
   */
  function fleetClickOpensCard(target) {
    if (!target || typeof target.closest !== 'function') return false;
    return !target.closest('select, input, textarea, button, a, label');
  }

  // ------------------------------------------------------------------ wire
  function wire() {
    $('stageNav').addEventListener('click', (event) => {
      const button = event.target.closest('button[data-stage]');
      if (button) setStage(button.dataset.stage);
    });
    $('fleetList').addEventListener('click', (event) => {
      if (!fleetClickOpensCard(event.target)) return;
      const card = event.target.closest('.vcard');
      if (card) openVehicle(card.dataset.table, card.dataset.id);
    });
    $('fleetSearch').addEventListener('input', renderFleet);
    $('fleetTable').addEventListener('change', renderFleet);
    $('refreshAll').addEventListener('click', () => loadFleet().then(
      () => setStatus('已重新读取仓库。', 'ok')).catch((error) => setStatus(error.message, 'error')));
    $('newVehicle').addEventListener('click', newVehicleDialog);
    $('quickGen').addEventListener('click', () => runAction('gen'));
    $('quickBuild').addEventListener('click', () => { setStage('build'); runAction('build'); });
    $('saveVehicle').addEventListener('click', saveVehicle);
    $('copyVehicle').addEventListener('click', copyVehicleDialog);
    $('deleteVehicle').addEventListener('click', deleteVehicleDialog);
    $('addLivery').addEventListener('click', () => addAuxRow('livery'));
    $('addVariant').addEventListener('click', addVariantRow);
    $('manageStrings').addEventListener('click', () => setStage('strings'));
    $('addString').addEventListener('click', addStringRow);
    $('stringSearch').addEventListener('input', renderStrings);
    $('reloadStrings').addEventListener('click', () => reloadStrings()
      .then(() => setStatus('已重新读取字符串表。', 'ok')));
    $('modalClose').addEventListener('click', closeModal);
    $('viewTabs').addEventListener('click', onViewTabClick);
    $('modal').addEventListener('click', (event) => { if (event.target === $('modal')) closeModal(); });

    document.addEventListener('click', (event) => {
      const action = event.target.closest('[data-action]');
      if (action) { runAction(action.dataset.action); return; }
      const doc = event.target.closest('.doc-tab');
      if (doc) { loadDoc(doc.dataset.doc); return; }

      // ---- tier 2: liveries
      const pick = event.target.closest('[data-livery-pick]');
      if (pick) {
        state.liveryIndex = Number(pick.dataset.liveryPick);
        renderAux();
        renderSpritePreview();
        return;
      }
      // ---- fleet overview: purchase menu order and grouping
      const fleetMove = event.target.closest('[data-fleet-move]');
      if (fleetMove) {
        const card = fleetMove.closest('.vcard');
        const vehicle = (state.fleet.vehicles || []).find(
          (item) => item.table === card.dataset.table && item.id === card.dataset.id);
        if (vehicle) moveFleet(vehicle, Number(fleetMove.dataset.fleetMove));
        return;
      }

      const save = event.target.closest('[data-livery-save]');
      if (save) {
        saveLiveryRow(Number(save.closest('.livery').dataset.livery));
        return;
      }
      const del = event.target.closest('[data-livery-delete]');
      if (del) {
        deleteLiveryRow(Number(del.closest('.livery').dataset.livery));
        return;
      }
      const move = event.target.closest('[data-livery-move]');
      if (move) {
        const card = move.closest('.livery');
        moveLiveryRow(Number(card.dataset.livery), move.dataset.liveryMove);
        return;
      }
      const copy = event.target.closest('[data-livery-copy]');
      if (copy) {
        copyLiveryRow(Number(copy.closest('.livery').dataset.livery));
        return;
      }

      // ---- string table filters
      const kind = event.target.closest('[data-string-kind]');
      if (kind) {
        state.stringFilter = kind.dataset.stringKind;
        renderStrings();
        return;
      }

      // ---- cargo variant rows
      const vdel = event.target.closest('.aux-row [data-aux-delete]');
      if (vdel) {
        const row = vdel.closest('.aux-row');
        deleteVariantRow(Number(row.dataset.index), row.dataset.key);
        return;
      }

      // ---- string table
      const ssave = event.target.closest('[data-string-save]');
      if (ssave) { saveStringRow(ssave.closest('.string-row')); return; }
      const sdel = event.target.closest('[data-string-delete]');
      if (sdel) { deleteStringRow(sdel.closest('.string-row')); return; }

      // ---- the switch-block editor (tier 2, one card per paint scheme)
      const ruleAction = event.target.closest('[data-rule-action]');
      if (ruleAction) {
        const card = ruleAction.closest('.livery');
        if (card) ruleEditorAction(card, ruleAction);
        return;
      }
      const ruleMode = event.target.closest('[data-rule-mode]');
      if (ruleMode) {
        const card = ruleMode.closest('.livery');
        if (card) ruleEditorMode(card, ruleMode.dataset.ruleMode, Number(ruleMode.dataset.section));
        return;
      }
      if (event.target.closest('[data-rule-field]')) return;   // handled on change
    });

    // the rule preview is a round trip to the server, so typing is collected
    // before it asks: one request per pause instead of one per keystroke
    let rulePreviewTimer = 0;
    document.addEventListener('input', (event) => {
      // the rule preview follows what is typed, before anything is saved
      const input = event.target.closest('.livery [data-livery-field="graphics_parts"]');
      if (!input) return;
      const card = input.closest('.livery');
      clearTimeout(rulePreviewTimer);
      rulePreviewTimer = setTimeout(() => updateRulePreview(card), 250);
    });

    // selects and number boxes in the block editor commit on change/blur: each
    // one is a tree edit that has to be rendered back into the cell
    document.addEventListener('change', (event) => {
      // ---- fleet overview: the purchase menu's grouping and group label
      const group = event.target.closest('[data-fleet-group]');
      if (group) {
        const card = group.closest('.vcard');
        saveFleetMenu([{ table: card.dataset.table, id: card.dataset.id,
          variant_group: group.value }], '已更新购买菜单分组。');
        return;
      }
      const series = event.target.closest('[data-fleet-series]');
      if (series) {
        const card = series.closest('.vcard');
        saveFleetMenu([{ table: card.dataset.table, id: card.dataset.id,
          series_string: series.value.trim() }], '已更新折叠项名称。');
        return;
      }

      const field = event.target.closest('.livery [data-rule-field]');
      if (field) {
        const card = field.closest('.livery');
        if (card) ruleEditorField(card, field);
        return;
      }
      const input = event.target.closest('.livery [data-livery-field="graphics_parts"]');
      if (input) {
        // the text was edited by hand, so the blocks are rebuilt from the
        // server's parse of it rather than from the previous tree
        const card = input.closest('.livery');
        if (card) updateRulePreview(card, true);
      }
    });

    document.addEventListener('change', (event) => {
      // a livery's name selector updates its resolved text in place
      const liveryInput = event.target.closest('.livery [data-strings]');
      if (liveryInput) {
        const row = liveryInput.closest('.livery');
        const note = row.querySelector('[data-resolved]');
        if (note) {
          note.innerHTML = stringContent(liveryInput.value)
            || '<span class="bad">这个常量不在字符串表里，编译会失败</span>';
        }
        return;
      }
      const variantInput = event.target.closest('.aux-row [data-field]');
      if (variantInput) saveVariantRow(variantInput.closest('.aux-row'));
    });
  }

  async function boot() {
    try {
      state.schema = await jsonFetch('/schema');
    } catch (error) {
      setStatus('无法读取 schema：' + error.message, 'error');
      return;
    }
    $('fleetTable').innerHTML = '<option value="">全部表</option>'
      + state.schema.tables.map((table) =>
        `<option value="${esc(table.id)}">${esc(table.label)}</option>`).join('');
    wire();
    await reloadStrings();
    try {
      await loadFleet();
    } catch (error) {
      setStatus('无法读取仓库状态：' + error.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
