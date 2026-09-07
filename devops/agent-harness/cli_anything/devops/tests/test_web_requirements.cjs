const {test} = require('node:test');
const assert = require('node:assert/strict');

const ForgeRequirements = require('../web/requirements.js');

const requirementIssue = (overrides = {}) => ({
  key: 'P1-42',
  title: '开票申请',
  description: '普通工作项描述',
  type: 'story',
  priority: 'medium',
  status: 'backlog',
  requirement: {
    req_code: 'REQ-TAX-0042',
    system_name: '税务平台',
    chapter: '发票管理',
    module_path: '财务/税务/开票',
    req_type: '业务需求',
    priority: null,
    status: '待评估',
    missing: ['deliverable', 'biz_owner'],
    filled: 9,
    need: 11,
    scenario_count: 2,
    confirmed_scenario_count: 1,
    ...overrides,
  },
});

test('requirement filters match source code, system, chapter, type and missing fields', () => {
  const issue = requirementIssue();
  assert.equal(ForgeRequirements.matches(issue, {query: 'REQ-TAX-0042'}), true);
  assert.equal(ForgeRequirements.matches(issue, {query: '税务平台'}), true);
  assert.equal(ForgeRequirements.matches(issue, {system: '税务平台', chapter: '发票管理', reqType: '业务需求', missing: 'deliverable'}), true);
  assert.equal(ForgeRequirements.matches(issue, {system: '采购平台'}), false);
  assert.equal(ForgeRequirements.matches(issue, {missing: 'acceptance_criteria'}), false);
});

test('ordinary issues keep using ordinary filters and are not mistaken for requirements', () => {
  const ordinary = {key: 'APP-1', title: '登录修复', description: '认证模块', type: 'bug', priority: 'high', sprint_id: null};
  assert.equal(ForgeRequirements.matches(ordinary, {query: '登录', issueType: 'bug', priority: 'high', sprint: 'none'}), true);
  assert.equal(ForgeRequirements.matches(ordinary, {system: '税务平台'}), false);
  assert.equal(ForgeRequirements.cardMeta(ordinary), '');
  assert.equal(ForgeRequirements.listCells(ordinary), '');
});

test('missing source priority is explicit and requirement status stays separate from issue status', () => {
  const issue = requirementIssue();
  const meta = ForgeRequirements.cardMeta(issue);
  assert.match(meta, /原优先级：未提供/);
  assert.match(meta, /需求评估：待评估/);
  assert.doesNotMatch(meta, /原优先级：中/);
  assert.doesNotMatch(meta, /待办池/);
});

test('detail safely exposes long raw and original fields, source excerpt, and every GWT value', () => {
  const longText = '甲'.repeat(10050) + '<script>alert("raw")</script>';
  const detail = {
    ...requirementIssue().requirement,
    source_id: 'source-1',
    raw: {description: longText, unknown_field: '<img src=x onerror=alert(1)>', nullable: null},
    original: {description: '原始 <b>正文</b>'},
    current: {priority: null, acceptance_criteria: '<svg onload=alert(1)>', deliverable: null, workload_md: null, related_systems: '', biz_owner: '', owner_side: '', status: '待评估', remark: ''},
    version: 7,
    source: {file: '需求<总表>.xlsx', line: 88, excerpt: '来源 <script>bad()</script> 摘要'},
    scenarios: [{
      scenario_code: 'GWT-1',
      raw: {title: '危险 <img src=x>', given_text: '假如 <script>1</script>', when_text: '当点击', then_text: '那么成功'},
      current: {title: '修订标题', given_text: '<b>前置</b>', when_text: '操作', then_text: '结果', scenario_type: '主流程', status: '待复核', remark: '<iframe>备注</iframe>'},
      version: 3,
    }],
  };

  const html = ForgeRequirements.renderDetail(detail);
  assert.ok(html.length > 10050, 'long source text remains inspectable');
  for (const unsafe of ['<script>', '<img', '<svg', '<iframe', '<b>']) assert.equal(html.includes(unsafe), false);
  assert.match(html, /&lt;script&gt;alert\(&quot;raw&quot;\)&lt;\/script&gt;/);
  assert.match(html, /unknown_field/);
  assert.match(html, /nullable/);
  assert.match(html, /需求&lt;总表&gt;\.xlsx/);
  assert.match(html, /来源 &lt;script&gt;bad\(\)&lt;\/script&gt; 摘要/);
  assert.match(html, /GWT-1/);
  assert.match(html, /name="given_text"/);
  assert.match(html, /data-version="3"/);
  assert.match(html, /原始快照（只读）/);
});

test('50-row pagination reaches all 1472 requirements without silent truncation', () => {
  const items = Array.from({length: 1472}, (_, index) => ({key: `P1-${index + 1}`}));
  const first = ForgeRequirements.paginate(items, 1, 50);
  assert.deepEqual({page: first.page, pages: first.pages, from: first.from, to: first.to, count: first.items.length, hasPrev: first.hasPrev, hasNext: first.hasNext},
    {page: 1, pages: 30, from: 1, to: 50, count: 50, hasPrev: false, hasNext: true});
  const last = ForgeRequirements.paginate(items, 30, 50);
  assert.deepEqual({page: last.page, pages: last.pages, from: last.from, to: last.to, count: last.items.length, hasPrev: last.hasPrev, hasNext: last.hasNext},
    {page: 30, pages: 30, from: 1451, to: 1472, count: 22, hasPrev: true, hasNext: false});
  assert.equal(ForgeRequirements.paginate(items, 31, 50).page, 30);
});

test('board columns reveal 30 at a time and can expose every matching card', () => {
  const items = Array.from({length: 74}, (_, index) => ({key: `P1-${index + 1}`}));
  const initial = ForgeRequirements.boardSlice(items, 30);
  assert.equal(initial.items.length, 30);
  assert.equal(initial.remaining, 44);
  assert.equal(initial.hasMore, true);
  const next = ForgeRequirements.boardSlice(items, 60);
  assert.equal(next.items.length, 60);
  assert.equal(next.remaining, 14);
  const all = ForgeRequirements.boardSlice(items, 90);
  assert.equal(all.items.length, 74);
  assert.equal(all.remaining, 0);
  assert.equal(all.hasMore, false);
});

test('partial update payloads preserve optimistic-lock versions and only editable fields', () => {
  const payload = ForgeRequirements.updatePayload('P1-42', 7, {
    priority: 'P1',
    deliverable: '验收文档',
    req_code: 'must-not-write',
    workload_md: '',
  });
  assert.deepEqual(payload, {key: 'P1-42', version: 7, fields: {priority: 'P1', deliverable: '验收文档', workload_md: null}});
});
