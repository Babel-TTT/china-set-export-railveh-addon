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
    stage: 'fleet',
    selected: null,        // { table, id }
    row: null,             // the unmodified row as loaded
    dirty: false,
    doc: null,
    job: null,
    spriteView: 4,
  };

  const $ = (id) => document.getElementById(id);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  function setStatus(message, kind = '') {
    const box = $('status');
    box.textContent = message;
    box.className = 'status ' + kind;
  }

  async function jsonFetch(path, options = {}) {
    const response = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body.error) throw new Error(body.error || ('HTTP ' + response.status));
    return body;
  }

  // ---------------------------------------------------------------- fleet
  async function loadFleet() {
    const data = await jsonFetch('/state');
    state.fleet = data;
    state.sheets = {};   // the sprite sheets may have just been re-rendered
    $('repoRev').textContent = (data.git && data.git.describe) || 'no git';
    $('repoRev').className = 'pill' + (data.git && data.git.dirty ? ' tag warn' : '');
    const counts = $('counts');
    counts.innerHTML = [
      ['机车', data.counts['locomotives.csv'] || 0],
      ['客车', data.counts['coaches.csv'] || 0],
      ['货车', data.counts['wagons.csv'] || 0],
      ['拖车', data.counts['unit_wagons.csv'] || 0],
      ['涂装行', (data.liveries || []).length],
      ['外观行', (data.variants || []).length],
      ['字符串', data.strings],
      ['GRF 字节', data.grf && data.grf.exists ? data.grf.size : '无'],
    ].map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('');
    renderFleet();
    renderAux();
    renderSprites();
    if (data.total === 0) {
      setStatus('车队为空。用「新建车辆」添加第一台车，保存后点「生成代码」。');
    } else {
      setStatus(`${data.total} 台车已登记。`, 'ok');
    }
  }

  function renderFleet() {
    const search = ($('fleetSearch').value || '').trim().toLowerCase();
    const tableFilter = $('fleetTable').value;
    const list = $('fleetList');
    const vehicles = (state.fleet.vehicles || []).filter((vehicle) => {
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

    list.innerHTML = vehicles.map((vehicle) => {
      const selected = state.selected && state.selected.id === vehicle.id
        && state.selected.table === vehicle.table;
      const tags = [
        `<span class="tag cyan">${esc(vehicle.category || '—')}</span>`,
        vehicle.vehicle_id != null ? `<span class="tag">ID ${vehicle.vehicle_id}</span>` : '',
        vehicle.track_type ? `<span class="tag">${esc(vehicle.track_type)}</span>` : '',
        vehicle.sprites_ready
          ? '<span class="tag ok">精灵图就绪</span>'
          : `<span class="tag bad">缺 ${(vehicle.sprites_missing || []).length || '?'} 张贴图</span>`,
        vehicle.ac_supply === '1' ? '<span class="tag">供电</span>' : '',
        vehicle.mu === '1' ? '<span class="tag">动车组</span>' : '',
      ].filter(Boolean).join('');
      return `<div class="vcard${selected ? ' sel' : ''}" data-table="${esc(vehicle.table)}" data-id="${esc(vehicle.id)}">
        <div>
          <div class="vid">${esc(vehicle.id)} <span class="vname">${esc(vehicle.name_string || '')}</span></div>
          <div class="tags">${tags}</div>
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
      // genpnml.py's _bool() treats 1/y/yes/true/t/on as true and anything
      // else as false, so offer the readable spellings as well.
      const truthy = ['0', '1', 'yes', 'true', 'no', 'off'];
      const options = [`<option value=""${value === '' ? ' selected' : ''}>（留空 / 用默认）</option>`]
        .concat(truthy.map((choice) =>
          `<option value="${choice}"${choice === value ? ' selected' : ''}>${choice}</option>`));
      if (value && !truthy.includes(value)) {
        options.push(`<option value="${esc(value)}" selected>${esc(value)}</option>`);
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
    $('detailId').textContent = row.id || '(未命名)';
    const vehicle = (state.fleet.vehicles || []).find((item) => item.id === row.id
      && item.table === table);
    $('detailMeta').textContent = [
      vehicle && vehicle.vehicle_id != null ? `ID ${vehicle.vehicle_id}` : '',
      vehicle && vehicle.band ? `段 ${vehicle.band}` : '',
      table,
    ].filter(Boolean).join(' · ');

    const wide = new Set(['additional_text', 'comment', 'parts', 'capacity_by_cargo',
      'train_flags', 'refittable_cargo_classes', 'cargo_allow_refit', 'cargo_disallow_refit']);
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
    renderSpritePreview();
  }

  function collectDetail() {
    const row = { ...state.row };
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
      renderFleet();
      renderDetail();
      renderAux();
      renderSprites();
      setStage('detail');
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
      if (!result.ok) {
        setStatus('校验未通过：\n' + result.errors.join('\n'), 'error');
        return;
      }
      state.row = row;
      state.selected.id = row.id;
      state.dirty = false;
      applyState(result.state);
      setStatus(`已保存 ${state.selected.table} 中的 ${row.id}。下一步：生成车辆代码。`, 'ok');
      renderDetail();
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  function applyState(data) {
    if (!data) return;
    state.fleet = data;
    $('repoRev').textContent = (data.git && data.git.describe) || 'no git';
    const counts = $('counts');
    counts.innerHTML = [
      ['机车', data.counts['locomotives.csv'] || 0],
      ['客车', data.counts['coaches.csv'] || 0],
      ['货车', data.counts['wagons.csv'] || 0],
      ['拖车', data.counts['unit_wagons.csv'] || 0],
      ['涂装行', (data.liveries || []).length],
      ['外观行', (data.variants || []).length],
      ['字符串', data.strings],
      ['GRF 字节', data.grf && data.grf.exists ? data.grf.size : '无'],
    ].map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('');
    renderFleet();
    renderAux();
    renderSprites();
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
          <input id="n_folder" placeholder="diesel" list="n_folders">
          <datalist id="n_folders">${folders.map((folder) =>
            `<option value="${esc(folder)}"></option>`).join('')}</datalist></div>
        <div class="field"><label>类别（仅机车表生效）</label>
          <select id="n_category">${categories.map((category) =>
            `<option value="${esc(category)}"${category === 'diesel' ? ' selected' : ''}>${esc(category)}</option>`).join('')}</select></div>
        <div class="field"><label>模型类型</label>
          <select id="n_model"><option value="triple" selected>triple（前-身-后）</option>
            <option value="single">single（一体）</option></select></div>
      </div>
      <p class="hint">创建后可在「车辆明细」里补齐其余列。ID 段由所在表与类别决定，不用手填。</p>
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
      row.model = $('n_model').value;
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
        setStatus(`已新建 ${id}。点「生成代码」写出它的 PNML 与占位模型。`, 'ok');
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

  // ------------------------------------------------------------ aux tables
  const AUX = {
    livery: {
      table: 'liveries.csv',
      fields: () => state.schema.livery_fields,
      rows: () => state.fleet.liveries || [],
      keys: (row) => [(row.id || '').trim(), (row.sprite_suffix || '').trim(),
        (row.from_year || '').trim(), (row.to_year || '').trim()].join('\u0000'),
      blank: () => ({ id: state.selected ? state.selected.id : '',
        sprite_suffix: '', string: 'STR_BUILD_YEAR', from_year: '0', to_year: '9999',
        purchase_suffix: '', templates: '' }),
      note: '行序即涂装索引。',
    },
    variant: {
      table: 'cargo_variants.csv',
      fields: () => state.schema.variant_fields,
      rows: () => state.fleet.variants || [],
      keys: (row) => [(row.id || '').trim(), (row.variant || '').trim()].join('\u0000'),
      blank: () => ({ id: '', variant: '', sprite_suffix: '', cargo_classes: 'bitmask(CC_BULK)',
        cargo_types: '', from_index: '0', to_index: '0', template: 'template_standard' }),
      note: '每一行是一种货物外观。',
    },
  };

  function renderAux() {
    for (const [kind, config] of Object.entries(AUX)) {
      const container = $(kind + 'List');
      if (!container) continue;
      const rows = config.rows();
      if (!rows.length) {
        container.innerHTML = `<div class="empty"><p>${esc(config.table)} 还没有数据行。</p>
          <p class="hint">${esc(config.note)}</p></div>`;
        continue;
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
          <div class="aux-rows">${groupRows.map((row, index) =>
            `<div class="aux-row" data-table="${esc(config.table)}"
                data-key="${esc(config.keys(row))}">
              <span class="idx">#${index}</span>
              ${config.fields().filter((field) => field.name in row).map((field) =>
                `<div class="field"><label>${esc(field.label)}</label>
                  <input data-field="${esc(field.name)}" value="${esc(row[field.name] ?? '')}"
                    placeholder="${esc(field.placeholder)}"
                    title="${esc(field.help || '')}"></div>`).join('')}
              <button class="danger" data-aux-delete="1">删除</button>
            </div>`).join('')}</div></div>`).join('');
    }
  }

  async function saveAuxRow(table, key, container) {
    const row = {};
    all('[data-field]', container).forEach((input) => {
      row[input.dataset.field] = input.value.trim();
    });
    const original = AUX[table === 'liveries.csv' ? 'livery' : 'variant'].rows()
      .find((item) => AUX[table === 'liveries.csv' ? 'livery' : 'variant'].keys(item) === key) || row;
    try {
      const result = await jsonFetch('/save', {
        method: 'POST',
        body: JSON.stringify({ table, original, row, create: false }),
      });
      if (!result.ok) {
        setStatus('校验未通过：\n' + result.errors.join('\n'), 'error');
        return;
      }
      applyState(result.state);
      setStatus(`已保存 ${table} 的一行。`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  async function deleteAuxRow(table, key) {
    try {
      const result = await jsonFetch('/delete', {
        method: 'POST',
        body: JSON.stringify({ table, key: key.split('\u0000') }),
      });
      applyState(result.state);
      setStatus('已删除该行。', 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
    }
  }

  function addAuxRow(kind) {
    const config = AUX[kind];
    const blank = config.blank();
    const fields = config.fields();
    if (kind === 'variant' && !(state.fleet.counts['wagons.csv'])) {
      setStatus('货运外观只能挂在货车上， wagons.csv 目前是空的。', 'error');
      return;
    }
    openModal(kind === 'livery' ? '新增涂装行' : '新增货运外观行', `
      <div class="grid2">${fields.filter((field) => field.name !== 'templates').map((field) =>
        `<div class="field"><label>${esc(field.label)}</label>
          <input id="a_${esc(field.name)}" value="${esc(blank[field.name] ?? '')}"
            placeholder="${esc(field.placeholder)}">
          ${field.help ? `<div class="help">${esc(field.help)}</div>` : ''}</div>`).join('')}</div>
    `, async () => {
      const row = {};
      fields.forEach((field) => {
        const input = $('a_' + field.name);
        row[field.name] = input ? input.value.trim() : (blank[field.name] ?? '');
      });
      try {
        const result = await jsonFetch('/save', {
          method: 'POST',
          body: JSON.stringify({ table: config.table, row, create: true }),
        });
        if (!result.ok) {
          setStatus('校验未通过：\n' + result.errors.join('\n'), 'error');
          return false;
        }
        applyState(result.state);
        setStatus(`已新增一行到 ${config.table}。`, 'ok');
        return true;
      } catch (error) {
        setStatus(error.message, 'error');
        return false;
      }
    });
  }

  // --------------------------------------------------------------- sprites
  function renderSprites() {
    const container = $('spriteList');
    const vehicles = (state.fleet.vehicles || []).filter((vehicle) => (vehicle.sprites || []).length);
    if (!vehicles.length) {
      container.innerHTML = `<div class="empty"><p>还没有任何模型。</p>
        <p class="hint">先添加车辆并运行「生成车辆代码」，它会为每个需要的贴图写出占位 .vox，
        再运行「渲染精灵图」把它变成 _32bpp.png。</p></div>`;
      return;
    }
    container.innerHTML = vehicles.map((vehicle) => `
      <div class="sprite-card"><div class="sprite-head"><b>${esc(vehicle.id)}</b>
        <span class="hint">${esc(vehicle.name_string || '')} · gfx/${esc(vehicle.folder)}/</span>
        <span class="tag ${vehicle.sprites_ready ? 'ok' : 'bad'}">
          ${vehicle.sprites_ready ? '全部就绪' : '缺 ' + (vehicle.sprites_missing || []).length + ' 张'}</span>
      </div>
      <div class="sprite-views">${(vehicle.sprites || []).map((sprite) => `
        <div class="view"><span>${esc(sprite.basename)}</span>
          ${sprite.png
            ? `<canvas data-sheet="${esc(sprite.png_path)}" width="${VIEW_PX}" height="${VIEW_PX}"></canvas>`
            : `<span class="tag bad">未渲染</span>`}
          <span>${sprite.vox ? '.vox 已存在' : '缺 .vox'}</span></div>`).join('')}</div>
      </div>`).join('');
    all('#spriteList canvas[data-sheet]').forEach((canvas) => {
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
    const vehicle = (state.fleet.vehicles || []).find((item) => item.id === state.row.id
      && item.table === state.selected.table);
    const ready = ((vehicle && vehicle.sprites) || []).filter((sprite) => sprite.png);
    const preview = $('spritePreview');
    const tabs = $('viewTabs');
    if (!ready.length) {
      preview.innerHTML = '<span class="hint">这台车还没有渲染好的贴图，先运行「渲染精灵图」。</span>';
      tabs.classList.add('hidden');
      return;
    }
    state.spriteSheet = state.spriteSheet && ready.some((s) => s.png_path === state.spriteSheet)
      ? state.spriteSheet : ready[0].png_path;
    tabs.classList.remove('hidden');
    tabs.innerHTML = ready.map((sprite) =>
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
    fleet: ['车队账本', '全车队的概览与入口。', []],
    detail: ['车辆明细', '逐列编辑一台车，右侧实时显示它会生成的 PNML。', []],
    livery: ['涂装方案', '同一台车的多种涂装，行序决定涂装索引。', []],
    variant: ['货运外观', '货车按货物类别与装载量切换贴图。', []],
    sprite: ['模型与精灵图', '每个 basename 的 .vox 与 8 方向渲染结果。', []],
    check: ['一致性检查', '字符串表双向核对与贴图引用检查。', [['check', '运行检查']]],
    build: ['构建 GRF', '预处理、编译，产出可进游戏的 grf。', [['build', '编译 GRF']]],
    guide: ['指南', '仓库内文档的离线浏览。', []],
  };

  function setStage(stage) {
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
    if (stage === 'sprite') renderSprites();
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

  // ------------------------------------------------------------------ wire
  function wire() {
    $('stageNav').addEventListener('click', (event) => {
      const button = event.target.closest('button[data-stage]');
      if (button) setStage(button.dataset.stage);
    });
    $('fleetList').addEventListener('click', (event) => {
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
    $('addVariant').addEventListener('click', () => addAuxRow('variant'));
    $('modalClose').addEventListener('click', closeModal);
    $('viewTabs').addEventListener('click', onViewTabClick);
    $('modal').addEventListener('click', (event) => { if (event.target === $('modal')) closeModal(); });

    document.addEventListener('click', (event) => {
      const action = event.target.closest('[data-action]');
      if (action) { runAction(action.dataset.action); return; }
      const doc = event.target.closest('.doc-tab');
      if (doc) { loadDoc(doc.dataset.doc); return; }
      const del = event.target.closest('[data-aux-delete]');
      if (del) {
        const row = del.closest('.aux-row');
        deleteAuxRow(row.dataset.table, row.dataset.key);
        return;
      }
      const add = event.target.closest('[data-aux-add]');
      if (add) addAuxRow(add.dataset.auxAdd);
    });

    document.addEventListener('change', (event) => {
      const input = event.target.closest('.aux-row [data-field]');
      if (input) {
        const row = input.closest('.aux-row');
        saveAuxRow(row.dataset.table, row.dataset.key, row);
      }
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
    try {
      await loadFleet();
    } catch (error) {
      setStatus('无法读取仓库状态：' + error.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
