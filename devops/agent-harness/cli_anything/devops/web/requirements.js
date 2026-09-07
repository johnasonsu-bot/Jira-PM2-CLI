'use strict';

(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.ForgeRequirements = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const EDITABLE_FIELDS = [
    'priority', 'acceptance_criteria', 'deliverable', 'workload_md',
    'related_systems', 'biz_owner', 'owner_side', 'status', 'remark',
  ];
  const SCENARIO_FIELDS = [
    'title', 'given_text', 'when_text', 'then_text', 'scenario_type', 'status', 'remark',
  ];
  const FIELD_LABELS = {
    priority: '需求优先级（当前）', acceptance_criteria: '验收标准', deliverable: '交付物',
    workload_md: '工作量（人天）', related_systems: '关联系统', biz_owner: '业务负责人',
    owner_side: '责任方', status: '需求评估状态', remark: '备注',
  };
  const REQUIRED_FIELD_LABELS = {
    req_code: '需求编号', req_name: '需求名称', req_desc: '需求描述', project_code: '所属项目',
    system_name: '归属系统', module_path: '所属模块', req_type: '需求类型', priority: '优先级',
    acceptance_criteria: '验收标准', deliverable: '交付物', workload_md: '工作量（人天）',
  };
  const SCENARIO_LABELS = {
    title: '场景标题', given_text: '假如（Given）', when_text: '当（When）',
    then_text: '那么（Then）', scenario_type: '场景类型', status: '复核状态', remark: '备注',
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]);
  }

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object || {}, key);
  }

  function matches(issue, filters = {}) {
    const req = issue?.requirement;
    const query = String(filters.query ?? '').trim().toLocaleLowerCase('zh-CN');
    const searchValues = [
      issue?.key, issue?.title, issue?.description, issue?.assignee,
      req?.req_code, req?.system_name, req?.chapter, req?.module_path, req?.req_type,
    ];
    if (query && !searchValues.some(value => String(value ?? '').toLocaleLowerCase('zh-CN').includes(query))) return false;
    if (filters.issueType && issue?.type !== filters.issueType) return false;
    if (filters.priority && issue?.priority !== filters.priority) return false;
    if (filters.sprint) {
      const sprintMatches = filters.sprint === 'none'
        ? issue?.sprint_id == null
        : String(issue?.sprint_id) === String(filters.sprint);
      if (!sprintMatches) return false;
    }
    if (filters.system && (!req || String(req.system_name ?? '') !== String(filters.system))) return false;
    if (filters.chapter && (!req || String(req.chapter ?? '') !== String(filters.chapter))) return false;
    if (filters.reqType && (!req || String(req.req_type ?? '') !== String(filters.reqType))) return false;
    if (filters.missing && (!req || !Array.isArray(req.missing) || !req.missing.includes(filters.missing))) return false;
    return true;
  }

  function filterValues(items, field) {
    const values = new Set();
    for (const item of items || []) {
      const value = item?.requirement?.[field];
      if (value !== null && value !== undefined && String(value).trim()) values.add(String(value));
    }
    return [...values].sort((a, b) => a.localeCompare(b, 'zh-CN', {numeric: true}));
  }

  function paginate(items, requestedPage = 1, pageSize = 50) {
    const source = Array.isArray(items) ? items : [];
    const size = Math.max(1, Math.floor(Number(pageSize) || 50));
    const pages = Math.max(1, Math.ceil(source.length / size));
    const page = Math.min(pages, Math.max(1, Math.floor(Number(requestedPage) || 1)));
    const start = (page - 1) * size;
    const pageItems = source.slice(start, start + size);
    return {
      items: pageItems, total: source.length, page, pages,
      from: source.length ? start + 1 : 0,
      to: source.length ? start + pageItems.length : 0,
      hasPrev: page > 1, hasNext: page < pages,
    };
  }

  function boardSlice(items, visible = 30) {
    const source = Array.isArray(items) ? items : [];
    const count = Math.max(0, Math.floor(Number(visible) || 0));
    const selected = source.slice(0, count);
    return {items: selected, remaining: source.length - selected.length, hasMore: selected.length < source.length};
  }

  function priorityText(requirement) {
    const value = requirement?.priority;
    return value === null || value === undefined || String(value).trim() === '' ? '未提供' : String(value);
  }

  function missingLabel(key) {
    return REQUIRED_FIELD_LABELS[key] || String(key ?? '');
  }

  function cardMeta(issue) {
    const req = issue?.requirement;
    if (!req) return '';
    const completeness = Number.isFinite(Number(req.filled)) && Number.isFinite(Number(req.need))
      ? `${Number(req.filled)}/${Number(req.need)}` : '—';
    return `<div class="requirement-card-meta"><span class="req-code">${escapeHtml(req.req_code || '未编号')}</span><span>${escapeHtml(req.system_name || '未提供系统')}</span><span>需求优先级（当前）：${escapeHtml(priorityText(req))}</span><span>需求评估：${escapeHtml(req.status || '未提供')}</span><span>字段 ${escapeHtml(completeness)}</span></div>`;
  }

  function listCells(issue) {
    const req = issue?.requirement;
    if (!req) return '';
    return `<td class="req-code">${escapeHtml(req.req_code || '未编号')}</td><td>${escapeHtml(req.system_name || '未提供')}</td><td>需求评估：${escapeHtml(req.status || '未提供')}</td>`;
  }

  function display(value) {
    if (value === null) return 'NULL（未填写）';
    if (value === undefined) return '未定义';
    if (value === '') return '空字符串';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }

  function textArea(name, label, value) {
    return `<label>${escapeHtml(label)}<textarea name="${escapeHtml(name)}" data-original="${escapeHtml(value ?? '')}">${escapeHtml(value ?? '')}</textarea></label>`;
  }

  function textInput(name, label, value, type = 'text', attributes = '') {
    return `<label>${escapeHtml(label)}<input name="${escapeHtml(name)}" type="${escapeHtml(type)}" value="${escapeHtml(value ?? '')}" data-original="${escapeHtml(value ?? '')}" ${attributes}></label>`;
  }

  function selectInput(name, label, value, values, allowEmpty = false) {
    const empty = allowEmpty ? `<option value="" ${value == null || value === '' ? 'selected' : ''}>未提供</option>` : '';
    const options = values.map(option => `<option value="${escapeHtml(option)}" ${String(value ?? '') === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('');
    return `<label>${escapeHtml(label)}<select name="${escapeHtml(name)}" data-original="${escapeHtml(value ?? '')}">${empty}${options}</select></label>`;
  }

  function analysisForm(requirement, key) {
    const current = requirement?.current || {};
    return `<form class="requirement-analysis-form" data-requirement-form data-key="${escapeHtml(key || requirement?.key || '')}" data-version="${escapeHtml(requirement?.version ?? 0)}">
      <div class="requirement-form-grid">
        ${selectInput('priority', FIELD_LABELS.priority, current.priority, ['P0', 'P1', 'P2'], true)}
        ${textInput('workload_md', FIELD_LABELS.workload_md, current.workload_md, 'number', 'min="0" step="0.01"')}
        ${selectInput('status', FIELD_LABELS.status, current.status || '待评估', ['待评估', '已确认', '开发中', '已验收', '已否决'])}
        ${textInput('biz_owner', FIELD_LABELS.biz_owner, current.biz_owner)}
        ${textInput('owner_side', FIELD_LABELS.owner_side, current.owner_side)}
        ${textInput('related_systems', FIELD_LABELS.related_systems, current.related_systems)}
        ${textArea('acceptance_criteria', FIELD_LABELS.acceptance_criteria, current.acceptance_criteria)}
        ${textArea('deliverable', FIELD_LABELS.deliverable, current.deliverable)}
        ${textArea('remark', FIELD_LABELS.remark, current.remark)}
      </div>
      <p class="requirement-form-error" role="alert"></p>
      <button class="primary" type="submit">保存需求分析</button>
    </form>`;
  }

  function recordTable(record) {
    if (record === null || record === undefined) return '<p class="requirement-empty">未保留该层数据</p>';
    if (typeof record !== 'object' || Array.isArray(record)) return `<pre class="source-plain">${escapeHtml(display(record))}</pre>`;
    const rows = Object.keys(record).sort((a, b) => a.localeCompare(b, 'zh-CN')).map(key =>
      `<tr><th>${escapeHtml(key)}</th><td><pre>${escapeHtml(display(record[key]))}</pre></td></tr>`).join('');
    return `<div class="requirement-record"><table><tbody>${rows}</tbody></table></div>`;
  }

  function scenarioForm(scenario, requirementKey) {
    const current = scenario?.current || {};
    const raw = scenario?.raw || {};
    const code = scenario?.scenario_code || raw.scenario_code || '未编号';
    return `<section class="scenario-card">
      <div class="scenario-heading"><h4>${escapeHtml(code)}</h4><span>${escapeHtml(current.status || raw.status || '待复核')}</span></div>
      <form data-scenario-form data-key="${escapeHtml(requirementKey || '')}" data-scenario-code="${escapeHtml(code)}" data-version="${escapeHtml(scenario?.version ?? 0)}">
        <div class="requirement-form-grid scenario-grid">
          ${textInput('title', SCENARIO_LABELS.title, current.title ?? raw.title)}
          ${textInput('scenario_type', SCENARIO_LABELS.scenario_type, current.scenario_type ?? raw.scenario_type)}
          ${selectInput('status', SCENARIO_LABELS.status, current.status || '待复核', ['待复核', '已确认', '已废弃'])}
          ${textArea('given_text', SCENARIO_LABELS.given_text, current.given_text ?? raw.given_text)}
          ${textArea('when_text', SCENARIO_LABELS.when_text, current.when_text ?? raw.when_text)}
          ${textArea('then_text', SCENARIO_LABELS.then_text, current.then_text ?? raw.then_text)}
          ${textArea('remark', SCENARIO_LABELS.remark, current.remark ?? raw.remark)}
        </div>
        <details><summary>查看原始场景字段</summary>${recordTable(raw)}</details>
        <p class="requirement-form-error" role="alert"></p>
        <button class="secondary" type="submit">保存场景</button>
      </form>
    </section>`;
  }

  function renderDetail(requirement, key = '') {
    if (!requirement) return '';
    const missing = Array.isArray(requirement.missing) ? requirement.missing : [];
    const source = requirement.source || {};
    const requirementKey = key || requirement.key || '';
    const scenarioCount = Array.isArray(requirement.scenarios) ? requirement.scenarios.length : 0;
    const resolvedLine = source.resolved_line === null || source.resolved_line === undefined ? '' : `<dt>正文定位行</dt><dd>${escapeHtml(source.resolved_line)}</dd>`;
    const matchNames = {body: '需求正文匹配', unverified: '未验证（使用原始档案行）'};
    const match = source.match === null || source.match === undefined || source.match === '' ? '' : `<dt>定位方式</dt><dd>${escapeHtml(matchNames[source.match] || source.match)}</dd>`;
    return `<section class="requirement-detail" data-source-id="${escapeHtml(requirement.source_id || '')}">
      <div class="requirement-summary">
        <div><small>原需求编号</small><strong>${escapeHtml(requirement.req_code || '未编号')}</strong></div>
        <div><small>系统</small><strong>${escapeHtml(requirement.system_name || '未提供')}</strong></div>
        <div><small>章节</small><strong>${escapeHtml(requirement.chapter || '未提供')}</strong></div>
        <div><small>需求类型</small><strong>${escapeHtml(requirement.req_type || '未提供')}</strong></div>
        <div><small>需求优先级（当前）</small><strong>${escapeHtml(priorityText(requirement))}</strong></div>
        <div><small>需求评估状态</small><strong>${escapeHtml(requirement.status || requirement.current?.status || '未提供')}</strong></div>
      </div>
      <div class="requirement-completeness"><span>源字段完整度 ${escapeHtml(requirement.filled ?? '—')}/${escapeHtml(requirement.need ?? 11)}</span>${missing.length ? `<span class="missing-fields">缺失：${missing.map(field => escapeHtml(missingLabel(field))).join('、')}</span>` : '<span>必备字段完整</span>'}</div>
      <section class="requirement-section"><h3>来源上下文</h3><dl class="source-context"><dt>文件</dt><dd>${escapeHtml(source.file || '未提供')}</dd><dt>原始档案行</dt><dd>${escapeHtml(source.line ?? '未提供')}</dd>${resolvedLine}${match}</dl><pre class="source-plain">${escapeHtml(source.excerpt || '未提供来源摘录')}</pre></section>
      <section class="requirement-section"><div class="requirement-section-heading"><h3>补充分析（可编辑）</h3><span>版本 ${escapeHtml(requirement.version ?? 0)}</span></div>${analysisForm(requirement, requirementKey)}</section>
      <section class="requirement-section"><div class="requirement-section-heading"><h3>GWT 场景 · ${scenarioCount}</h3><span>原场景始终保留</span></div>${scenarioCount ? requirement.scenarios.map(item => scenarioForm(item, requirementKey)).join('') : '<p class="requirement-empty">暂无场景</p>'}</section>
      <section class="requirement-section source-inspection"><h3>原始档案（只读，不随补充分析修改）</h3><details open><summary>原数据库原始字段（含原始 priority）</summary>${recordTable(requirement.raw)}</details><details><summary>压缩包原始完整字段</summary>${recordTable(requirement.original)}</details></section>
      <div class="requirement-export"><button type="button" class="secondary" data-action="export-requirement" data-source-id="${escapeHtml(requirement.source_id || '')}">导出完整来源 JSON</button><small>仅点击时获取原始快照与全部覆盖层，可能较大。</small></div>
    </section>`;
  }

  function updatePayload(key, version, values) {
    const fields = {};
    for (const name of EDITABLE_FIELDS) {
      if (!hasOwn(values, name)) continue;
      let value = values[name];
      if (name === 'priority') value = value === '' ? null : value;
      if (name === 'workload_md') value = value === '' || value === null || value === undefined ? null : Number(value);
      fields[name] = value;
    }
    return {key, version: Number(version), fields};
  }

  function scenarioUpdatePayload(key, scenarioCode, version, values) {
    const fields = {};
    for (const name of SCENARIO_FIELDS) if (hasOwn(values, name)) fields[name] = values[name];
    return {key, scenario_code: scenarioCode, version: Number(version), fields};
  }

  function pager(pageData) {
    if (!pageData || pageData.total === 0) return '';
    return `<nav class="requirements-pager" aria-label="工作项分页"><span>显示 ${pageData.from}–${pageData.to} / ${pageData.total}</span><button class="secondary" data-action="requirements-page" data-page="${pageData.page - 1}" ${pageData.hasPrev ? '' : 'disabled'}>上一页</button><span>第 ${pageData.page} / ${pageData.pages} 页</span><button class="secondary" data-action="requirements-page" data-page="${pageData.page + 1}" ${pageData.hasNext ? '' : 'disabled'}>下一页</button></nav>`;
  }

  return {
    EDITABLE_FIELDS, SCENARIO_FIELDS, escapeHtml, matches, filterValues, paginate,
    boardSlice, cardMeta, listCells, renderDetail, updatePayload, scenarioUpdatePayload,
    pager, priorityText, missingLabel,
  };
});
