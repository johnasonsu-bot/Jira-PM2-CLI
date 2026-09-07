"""Losslessness, atomicity and versioned analysis use the real Store and API."""
import copy
import json
import threading

import pytest

from cli_anything.devops.store import Store, DomainError
from cli_anything.devops.server import make_server
from cli_anything.devops.backend import Backend


@pytest.fixture
def bundle():
    raw = dict(req_code='P1-TAX-001', project_code='P1', req_name='税务原始需求',
               req_desc='长' * 13010, system_name='税务', module_path='税务 / 申报',
               chapter='五、业务需求', req_type='功能需求', priority=None,
               workload_md=None, acceptance_criteria=None, deliverable=None,
               status='待评估', source_file='doc1', source_line=2, is_common=1,
               unknown_future_field={'keep': [None, 0, '原样']})
    return dict(source_id='changan-test', projects=[{'project_code':'P1', 'project_name':'税务包'}],
                requirements=[raw], scenarios=[dict(req_code=raw['req_code'], scenario_code='P1-TAX-001-S01',
                    title='申报', given_text='已登录', when_text='提交', then_text='校验通过',
                    status='待复核', derived=1, seq=1, scenario_type='主流程', source_clause='原始子句')],
                original_requirements=[{**raw, 'chapter':'原章节'}],
                documents={'doc1':'标题\n原始正文\n后续行'}, field_rules=[{'custom':'完整保留'}],
                import_batches=[{'row_count':1}], schema={'requirements':['all columns']})


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / 'forge.sqlite3')
    result.call('project.create', {'key':'APP','name':'原项目'})
    result.call('issue.create', {'project':'APP','title':'原工作'})
    return result


def imported(store, bundle):
    return store.call('requirement.import', {'bundle':bundle}, 'Import/Test')


def test_lossless_roundtrip_and_existing_issues_untouched(store, bundle):
    before = store.call('issue.get', {'key':'APP-1'})
    result = imported(store, bundle)
    assert (result['requirements'], result['scenarios'], result['projects']) == (1, 1, ['P1'])
    item = store.call('issue.get', {'key':'P1-1'})
    assert item['description'] == '长' * 13010
    assert item['status'] == 'backlog' and item['assignee'] == '' and item['points'] == 0
    detail = item['requirement']
    assert detail['raw'] == bundle['requirements'][0]
    assert detail['original'] == bundle['original_requirements'][0]
    assert detail['current']['workload_md'] is None
    assert detail['scenarios'][0]['raw'] == bundle['scenarios'][0]
    assert '原始正文' in detail['source']['excerpt']
    assert detail['missing'] == ['priority', 'acceptance_criteria', 'deliverable', 'workload_md']
    exported = store.call('requirement.export', {'source_id':bundle['source_id']})
    assert exported['snapshot'] == bundle
    assert exported['requirements'][0]['raw'] == bundle['requirements'][0]
    assert exported['requirements'][0]['original'] == bundle['original_requirements'][0]
    assert exported['scenarios'][0]['raw'] == bundle['scenarios'][0]
    assert Store(store.path).call('requirement.get', {'key':'P1-1'})['raw'] == bundle['requirements'][0]
    assert store.call('issue.get', {'key':'APP-1'}) == before


def test_source_priority_does_not_claim_delivery_scheduling(store,bundle):
    bundle['requirements'][0]['priority']='P0'
    imported(store,bundle)
    item=store.call('issue.get',{'key':'P1-1'})
    assert item['requirement']['raw']['priority']=='P0'
    assert item['priority']=='medium'


def test_identical_retry_preserves_edits_and_changed_source_is_rejected(store, bundle):
    imported(store, bundle)
    store.call('issue.update', {'key':'P1-1','assignee':'User','status':'in_progress'})
    store.call('requirement.update', {'key':'P1-1','version':1,'fields':{'deliverable':'交付文档'}})
    before = store.call('activity.list', {'project':'P1'})
    assert imported(store, bundle)['reused'] is True
    assert store.call('activity.list', {'project':'P1'}) == before
    assert store.call('requirement.get', {'key':'P1-1'})['current']['deliverable'] == '交付文档'
    changed = copy.deepcopy(bundle)
    changed['requirements'][0]['req_desc'] = 'changed'
    with pytest.raises(DomainError, match='快照'):
        imported(store, changed)


@pytest.mark.parametrize('problem', ['duplicate','orphan','collision','invalid_project','non_object','invalid_doc'])
def test_import_rejects_invalid_bundles_atomically(store, bundle, problem):
    if problem == 'duplicate': bundle['requirements'] *= 2
    if problem == 'orphan': bundle['scenarios'][0]['req_code'] = 'MISSING'
    if problem == 'collision': store.call('project.create', {'key':'P1','name':'Unrelated'})
    if problem == 'invalid_project': bundle['projects'][0]['project_code'] = '../P1'
    if problem == 'non_object': bundle['requirements'][0] = 'bad'
    if problem == 'invalid_doc': bundle['documents']['doc1'] = ['bad']
    before = store.call('project.list')
    with pytest.raises(DomainError): imported(store, bundle)
    assert store.call('project.list') == before
    assert len(store.call('issue.list')) == 1


@pytest.mark.parametrize('scenario_code', [' P1-TAX-001-S01', 'P1-TAX-001-S01 '])
def test_import_rejects_scenario_code_with_surrounding_whitespace_atomically(store, bundle, scenario_code):
    bundle['scenarios'][0]['scenario_code'] = scenario_code
    before_projects = store.call('project.list')
    before_issue = store.call('issue.get', {'key':'APP-1'})
    with pytest.raises(DomainError, match='场景编号'):
        imported(store, bundle)
    assert store.call('project.list') == before_projects
    assert store.call('issue.get', {'key':'APP-1'}) == before_issue
    assert len(store.call('issue.list')) == 1


def test_analysis_updates_are_separate_from_raw_and_have_optimistic_lock(store, bundle):
    imported(store, bundle)
    updated = store.call('requirement.update', {'key':'P1-1','version':1,'fields':{
        'priority':'P0','acceptance_criteria':'可复核的验收标准','deliverable':'报告','workload_md':0,'status':'已确认'}})
    assert updated['missing'] == [] and updated['version'] == 2
    assert updated['raw']['priority'] is None and updated['current']['priority'] == 'P0'
    assert store.call('issue.get', {'key':'P1-1'})['status'] == 'backlog'
    with pytest.raises(DomainError, match='冲突'):
        store.call('requirement.update', {'key':'P1-1','version':1,'fields':{'remark':'stale'}})
    for fields in [{'workload_md':-1},{'workload_md':True},{'workload_md':'NaN'},{'priority':'critical'},
                   {'req_code':'rename'},{'status':'done'},{}]:
        with pytest.raises(DomainError):
            store.call('requirement.update', {'key':'P1-1','version':2,'fields':fields})
    assert store.call('requirement.export', {'source_id':'changan-test'})['snapshot'] == bundle


def test_scenario_confirmation_and_revision_never_changes_source(store, bundle):
    imported(store, bundle)
    data = dict(key='P1-1', scenario_code='P1-TAX-001-S01', version=1, fields={'status':'已确认'})
    item = store.call('requirement.scenario.update', data)
    assert item['current']['derived'] == 0 and item['current']['status'] == '已确认'
    assert item['raw']['status'] == '待复核'
    with pytest.raises(DomainError, match='冲突'): store.call('requirement.scenario.update', data)
    data.update(version=2, fields={'then_text':'新断言'})
    revised = store.call('requirement.scenario.update', data)
    assert revised['current']['status'] == '待复核' and revised['current']['derived'] == 1
    with pytest.raises(DomainError):
        store.call('requirement.scenario.update', {**data, 'version':3, 'fields':{'given_text':''}})
    with pytest.raises(DomainError):
        store.call('requirement.scenario.update', {**data,'key':'APP-1'})


def test_summary_filters_and_report_use_current_fields_not_derived_coverage(store, bundle):
    imported(store, bundle)
    report = store.call('requirement.report', {'project':'P1'})
    assert report['total'] == 1 and report['scenario_count'] == 1 and report['confirmed_scenario_count'] == 0
    assert len(report['fields']) == 11
    assert next(f for f in report['fields'] if f['key']=='priority')['filled'] == 0
    listing = store.call('requirement.list', {'project':'P1','q':'P1-TAX','limit':1})
    assert listing['total'] == 1 and listing['items'][0]['key'] == 'P1-1'
    assert listing['items'][0]['requirement']['scenario_count'] == 1
    assert store.call('requirement.list', {'project':'P1','q':'missing'})['total'] == 0
    assert store.call('requirement.report', {'project':'APP'})['total'] == 0


def test_source_context_locates_body_without_rewriting_original_line(store, bundle):
    bundle['requirements'][0]['req_desc'] = '中国长安财务数智化系统支持预算编制并进行审核流程的管理。'
    bundle['documents']['doc1'] = '目录\n预算章节\n\n\n中国长安财务数智化系统支持预算编制并进行审核流程的管理。\n下一条'
    imported(store,bundle)
    detail = store.call('requirement.get',{'key':'P1-1'})
    assert detail['raw']['source_line'] == detail['source']['line'] == 2
    assert detail['source']['resolved_line'] == 5
    assert detail['source']['match'] == 'body'
    assert '5: 中国长安' in detail['source']['excerpt']


@pytest.mark.parametrize('field,value', [('project_code',[]),('priority',{}),('source_line','bad')])
def test_malformed_source_fields_produce_domain_errors(store,bundle,field,value):
    bundle['requirements'][0][field]=value
    with pytest.raises(DomainError): imported(store,bundle)
    assert store.call('issue.list',{'project':'P1'}) == []


def test_large_import_route_and_real_cli_transport(tmp_path, bundle):
    from click.testing import CliRunner
    from cli_anything.devops.devops_cli import cli
    server = make_server(tmp_path/'http.sqlite3', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = Backend(f'http://127.0.0.1:{server.server_port}')
    # Unicode long source exceeds the ordinary 64 KiB endpoint but must be retained.
    bundle['documents']['doc1'] = '原文' * 20000
    try:
        result = backend.call('requirement.import', {'bundle':bundle})
        assert result['requirements'] == 1
        runner = CliRunner()
        get = runner.invoke(cli, ['--url',backend.url,'--json','requirement','get','P1-1'])
        assert get.exit_code == 0, get.output
        assert json.loads(get.output)['raw']['req_desc'] == '长'*13010
        export = backend.call('requirement.export', {'source_id':'changan-test'})
        assert export['snapshot'] == bundle
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_mcp_reads_real_imported_requirements_and_is_read_only(tmp_path, bundle):
    import asyncio
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    server = make_server(tmp_path/'mcp-requirements.sqlite3',0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    backend = Backend(f'http://127.0.0.1:{server.server_port}')
    backend.call('requirement.import', {'bundle':bundle})
    before = backend.call('requirement.export', {'source_id':bundle['source_id']})

    async def check():
        params = StdioServerParameters(command=sys.executable,
            args=['-m','cli_anything.devops.mcp_server','--url',backend.url])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                page = await session.call_tool('list_requirements',{'project':'P1','search':'P1-TAX'})
                assert page.structuredContent['total'] == 1
                result = await session.call_tool('get_requirement',{'key':'P1-1'})
                assert result.structuredContent['raw'] == bundle['requirements'][0]
                assert result.structuredContent['scenarios'][0]['raw'] == bundle['scenarios'][0]
                report = await session.call_tool('get_requirement_report',{'project':'P1'})
                assert report.structuredContent['scenario_count'] == 1
                rejected = await session.call_tool('requirement.import',{'bundle':bundle})
                assert rejected.isError
    try:
        asyncio.run(check())
        assert backend.call('requirement.export',{'source_id':bundle['source_id']}) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
