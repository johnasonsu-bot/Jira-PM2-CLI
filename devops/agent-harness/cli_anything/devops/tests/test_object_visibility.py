"""Tombstones protect legacy queries, writers and restorative integrity."""
import pytest
from cli_anything.devops.store import DomainError
from test_objects import store, family, create, delete, restore
from test_requirements import bundle


def test_parent_restore_keeps_child_tombstones_and_shared_delivery_identity(store):
    items=family(store)
    delete(store,items['scenario'],'remove-scenario')
    removed=delete(store,items['requirement'],'remove-req')
    assert store.call('issue.list',{'project':'AB'})[0]['key']==items['issue']['id']
    assert store.call('object.list',{'kind':'comment'})['total']==0
    restore(store,removed,'restore-req')
    assert store.call('requirement.get',{'key':items['requirement']['id']})['scenarios']==[]
    assert store.call('object.list',{'kind':'comment'})['total']==1
    removed=delete(store,items['project'],'remove-project')
    for action in ('project.list','issue.list','sprint.list','release.list','activity.list'):
        assert store.call(action)==[]
    assert store.call('report.summary',{'project':'AB'})['total']==0
    for kind in items:
        assert store.call('object.list',{'kind':kind})['items']==[]
    restore(store,removed,'restore-project')
    assert store.call('object.list',{'kind':'scenario'})['total']==0


def test_hidden_ancestors_block_all_legacy_writes_and_reads(store):
    items=family(store)
    req=items['requirement']['id']
    delete(store,items['project'])
    actions=[('issue.get',{'key':req}), ('requirement.get',{'key':req}),
        ('requirement.list',{'project':'AB'}), ('requirement.report',{'project':'AB'}),
        ('report.analytics',{'project':'AB'}), ('issue.create',{'project':'AB','title':'绕过'}),
        ('issue.update',{'key':req,'title':'绕过'}), ('issue.comment',{'key':req,'body':'绕过'}),
        ('sprint.create',{'project':'AB','name':'绕过'}), ('sprint.start',{'id':int(items['sprint']['id'])}),
        ('release.create',{'project':'AB','name':'绕过','issue_keys':[req]}),
        ('release.update',{'id':int(items['release']['id']),'notes':'绕过'}),
        ('requirement.update',{'key':req,'version':1,'fields':{'deliverable':'绕过'}}),
        ('requirement.scenario.update',{'key':req,'scenario_code':'S::1','version':1,'fields':{'title':'绕过'}})]
    for action,data in actions:
        with pytest.raises(DomainError): store.call(action,data)
    archived=store.call('requirement.export',{'source_id':items['requirement']['data']['source_id']})
    assert archived['requirements'][0]['deleted'] is True
    assert archived['scenarios'][0]['deleted'] is True


def test_sprint_reference_blocks_delete_and_unavailable_parent_blocks_restore(store):
    items=family(store)
    store.call('issue.update',{'key':items['requirement']['id'],'sprint_id':int(items['sprint']['id'])})
    with pytest.raises(DomainError): delete(store,items['sprint'],'blocked')
    removed=delete(store,items['requirement'],'remove-req')
    sprint=delete(store,items['sprint'],'remove-sprint')
    with pytest.raises(DomainError): restore(store,removed,'restore-req')
    restore(store,sprint,'restore-sprint')
    restore(store,removed,'restore-req')
    removed=delete(store,items['comment'],'remove-comment')
    delete(store,items['requirement'],'remove-req-again')
    with pytest.raises(DomainError): restore(store,removed,'restore-comment')


def test_released_version_is_immutable_but_can_archive_and_restore(store):
    items=family(store)
    store.call('issue.update',{'key':items['issue']['id'],'status':'done'})
    store.call('release.update',{'id':int(items['release']['id']),'status':'released'})
    item=store.call('object.get',{'kind':'release','id':items['release']['id']})
    with pytest.raises(DomainError):
        store.call('object.update',{'kind':'release','id':item['id'],'revision':item['revision'],
            'fields':{'notes':'篡改'},'request_id':'bad'})
    removed=delete(store,item)
    assert restore(store,removed)['data']['status']=='released'


def test_imported_archive_is_immutable_and_child_deletes_guard_legacy_scenario_update(store,bundle):
    store.call('requirement.import',{'bundle':bundle})
    before=store.call('requirement.export',{'source_id':bundle['source_id']})
    scenario=store.call('object.get',{'kind':'scenario','id':'P1-1::P1-TAX-001-S01'})
    delete(store,scenario)
    with pytest.raises(DomainError):
        store.call('requirement.scenario.update',{'key':'P1-1','scenario_code':'P1-TAX-001-S01','version':1,'fields':{'title':'绕过'}})
    assert store.call('requirement.report',{'project':'P1'})['scenario_count']==0
    req=store.call('object.get',{'kind':'requirement','id':'P1-1'})
    delete(store,req,'delete-requirement')
    assert store.call('requirement.list',{'project':'P1'})['total']==0
    assert store.call('requirement.report',{'project':'P1'})['total']==0
    after=store.call('requirement.export',{'source_id':bundle['source_id']})
    assert after['snapshot']==before['snapshot'] and after['digest']==before['digest']
    assert after['requirements'][0]['raw']==before['requirements'][0]['raw']
    assert after['requirements'][0]['original']==before['requirements'][0]['original']
    assert after['scenarios'][0]['raw']==before['scenarios'][0]['raw']
    assert after['requirements'][0]['deleted'] and after['scenarios'][0]['deleted']


def test_restoring_release_rejects_hidden_issue_without_partial_changes(store):
    items=family(store)
    removed=delete(store,items['release'],'remove-release')
    delete(store,items['issue'],'remove-issue')
    with pytest.raises(DomainError): restore(store,removed)
    assert store.call('object.get',{'kind':'release','id':removed['id'],'include_deleted':True})==removed


def test_project_archive_preserves_active_sprint_state_and_unique_gate(store):
    items=family(store)
    sid=int(items['sprint']['id'])
    store.call('sprint.start',{'id':sid})
    removed=delete(store,items['project'])
    assert store.call('sprint.list')==[]
    restore(store,removed)
    assert store.call('sprint.list')[0]['status']=='active'
    second=store.call('sprint.create',{'project':'AB','name':'第二个'})
    with pytest.raises(DomainError): store.call('sprint.start',{'id':second['id']})


@pytest.mark.parametrize('layout',['adjacent','same_line','unverified','prefix_only','duplicate','multiline'])
def test_visible_requirement_source_does_not_reveal_deleted_neighbor(store,layout):
    visible=('当前需求要求预算编制审批记录完整留存并提供审计查询能力。'
             '所有已审批的预算项目必须记录负责人和审批日期，用户可以按项目编号检索完整历史，'
             '并查看本条需求的最终审核结论。')
    hidden='隐藏需求专属正文：相邻项目的内部核算秘密字段。'
    document={'adjacent':visible+'\n'+hidden,'same_line':visible+' '+hidden,
              'unverified':'无关标题\n'+hidden,'prefix_only':visible[:60]+hidden,
              'duplicate':visible+'\n'+hidden+'\n'+visible,
              'multiline':visible.replace('所有已审批','\n所有已审批')+'\n'+hidden}[layout]
    bundle={'source_id':'neighbor-source','projects':[{'project_code':'CD','project_name':'来源项目'}],
        'requirements':[
            {'req_code':'R1','project_code':'CD','req_name':'可见需求','req_desc':visible,'source_file':'doc','source_line':1},
            {'req_code':'R2','project_code':'CD','req_name':'隐藏需求','req_desc':hidden,'source_file':'doc','source_line':2}],
        'documents':{'doc':document}}
    store.call('requirement.import',{'bundle':bundle})
    before=store.call('requirement.export',{'source_id':'neighbor-source'})
    delete(store,store.call('object.get',{'kind':'requirement','id':'CD-2'}))
    for detail in (store.call('requirement.get',{'key':'CD-1'}),
                   store.call('issue.get',{'key':'CD-1'})['requirement']):
        assert hidden not in detail['source']['excerpt']
        if layout in ('unverified','prefix_only','duplicate'):
            assert detail['source']['match']=='unverified'
            assert detail['source']['resolved_line'] is None
            assert '无关标题' not in detail['source']['excerpt']
            assert visible[:60] not in detail['source']['excerpt']
        elif layout=='multiline':
            assert detail['source']['match']=='body'
            assert detail['source']['resolved_line']==1
            assert '当前需求要求预算编制审批记录完整留存并提供审计查询能力。' in detail['source']['excerpt']
            assert '并查看本条需求的最终审核结论。' in detail['source']['excerpt']
        else:
            assert visible in detail['source']['excerpt']
    after=store.call('requirement.export',{'source_id':'neighbor-source'})
    assert after['snapshot']==before['snapshot'] and after['digest']==before['digest']
    assert [r['raw'] for r in after['requirements']]==[r['raw'] for r in before['requirements']]


@pytest.mark.parametrize('kind',['issue','requirement'])
def test_restore_rejects_unfinished_issue_in_completed_sprint_atomically(store,kind):
    items=family(store)
    key=items['requirement']['id']
    sid=int(items['sprint']['id'])
    store.call('sprint.start',{'id':sid})
    store.call('issue.update',{'key':key,'sprint_id':sid,'status':'in_progress'})
    removed=delete(store,store.call('object.get',{'kind':kind,'id':key}))
    store.call('sprint.complete',{'id':sid})
    with store.connect() as db:
        audit_before=[dict(r) for r in db.execute('SELECT * FROM activity ORDER BY id')]
        tombstones_before=[dict(r) for r in db.execute('SELECT * FROM object_tombstones ORDER BY kind,object_id')]
    with pytest.raises(DomainError,match='恢复冲突'): restore(store,removed)
    with store.connect() as db:
        assert [dict(r) for r in db.execute('SELECT * FROM activity ORDER BY id')]==audit_before
        assert [dict(r) for r in db.execute('SELECT * FROM object_tombstones ORDER BY kind,object_id')]==tombstones_before
    assert store.call('object.get',{'kind':kind,'id':key,'include_deleted':True})==removed
    assert store.call('object.list',{'kind':'comment'})['total']==0


def test_restore_done_issue_preserves_completed_sprint_history(store):
    items=family(store)
    key=items['requirement']['id']
    sid=int(items['sprint']['id'])
    store.call('sprint.start',{'id':sid})
    store.call('issue.update',{'key':key,'sprint_id':sid,'status':'done'})
    removed=delete(store,store.call('object.get',{'kind':'requirement','id':key}))
    store.call('sprint.complete',{'id':sid})
    restored=restore(store,removed)
    assert restored['deleted'] is False
    issue=store.call('issue.get',{'key':key})
    assert issue['status']=='done' and issue['sprint_id']==sid
