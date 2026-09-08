"""Unified writes exercise actual transactions and persisted domain records."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.client import HTTPConnection
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from cli_anything.devops.store import Store, DomainError
from cli_anything.devops.server import make_server


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'objects.sqlite3')


def create(store, kind, fields, request_id=None):
    return store.call('object.create', dict(kind=kind, fields=fields,
        request_id=request_id or f'create-{kind}-' + hashlib.sha256(json.dumps(fields,ensure_ascii=False).encode()).hexdigest()))


def update(store, item, fields, request_id='update'):
    return store.call('object.update', dict(kind=item['kind'], id=item['id'],
        revision=item['revision'], fields=fields, request_id=request_id))


def delete(store, item, request_id='delete'):
    preview = store.call('object.delete.preview', dict(kind=item['kind'], id=item['id']))
    return store.call('object.delete', dict(kind=item['kind'], id=item['id'],
        confirmation=preview['confirmation'], request_id=request_id))


def restore(store, item, request_id='restore'):
    return store.call('object.restore', dict(kind=item['kind'], id=item['id'],
        revision=item['revision'], request_id=request_id))


def family(store):
    project = create(store, 'project', {'key':'AB', 'name':'项目'})
    issue = create(store, 'issue', {'project':'AB', 'title':'工作项'})
    requirement = create(store, 'requirement', {'project':'AB', 'req_code':'REQ-1',
        'req_name':'手工需求', 'req_desc':'原文' * 15000, 'workload_md':0})
    scenario = create(store, 'scenario', {'issue_key':requirement['id'], 'scenario_code':'S::1',
        'title':'原场景', 'given_text':'前提', 'when_text':'动作', 'then_text':'结果'})
    sprint = create(store, 'sprint', {'project':'AB', 'name':'迭代'})
    release = create(store, 'release', {'project':'AB', 'name':'v1', 'issue_keys':[issue['id']]})
    comment = create(store, 'comment', {'issue_key':requirement['id'], 'body':'评论'})
    return {i['kind']:i for i in (project, issue, requirement, scenario, sprint, release, comment)}


@pytest.mark.parametrize('kind,fields', [('project',{'name':'新项目'}), ('issue',{'title':'新工作项'}),
    ('requirement',{'req_name':'新需求','req_desc':'长' * 30000,'system_name':'新系统','module_path':'模块','req_type':'功能需求'}),
    ('scenario',{'title':'新场景'}), ('sprint',{'name':'新迭代','goal':'目标'}),
    ('release',{'notes':'新说明'}), ('comment',{'body':'新评论'})])
def test_seven_kind_crud(store, kind, fields):
    items = family(store)
    item = store.call('object.get', {'kind':kind,'id':items[kind]['id']})
    changed = update(store, item, fields)
    assert changed['revision'] != item['revision']
    assert changed['deleted'] is False
    if kind == 'issue':
        delete(store, items['release'], 'delete-release')
    removed = delete(store, changed)
    assert removed['deleted'] is True
    with pytest.raises(DomainError): store.call('object.get', {'kind':kind,'id':item['id']})
    assert item['id'] not in [r['id'] for r in store.call('object.list', {'kind':kind})['items']]
    archived = store.call('object.get', {'kind':kind,'id':item['id'],'include_deleted':True})
    assert archived == removed
    assert restore(store, archived)['deleted'] is False


def test_idempotency_atomic_concurrent_replay_and_collision(store):
    fields = {'key':'AB','name':'项目'}
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _:create(store,'project',fields,'same'), range(10)))
    assert all(r == results[0] for r in results)
    assert len(store.call('activity.list')) == 1
    with pytest.raises(DomainError, match='冲突'): create(store,'project',{'key':'CD','name':'其他'},'same')
    removed = delete(store, results[0])
    assert create(store,'project',fields,'same') == results[0]
    assert store.call('project.list') == []
    assert removed['deleted']


def test_invalid_requests_do_not_consume_id(store):
    with pytest.raises(DomainError): create(store,'project',{'key':'AB','name':''},'retry')
    assert create(store,'project',{'key':'AB','name':'有效'},'retry')['id'] == 'AB'
    for kind in ('snapshot','activity','raw','projects'):
        with pytest.raises(DomainError): store.call('object.list', {'kind':kind})
    for data in ({'kind':'project','id':True}, {'kind':'comment','id':True},
                 {'kind':'project','id':'AB','include_deleted':'true'}):
        with pytest.raises(DomainError): store.call('object.get',data)
    for fields in ({'key':'CD'}, {'raw':{}}, {'original':{}}, {'snapshot':{}}, {'next_number':20}):
        with pytest.raises(DomainError): update(store,store.call('object.get',{'kind':'project','id':'AB'}),fields)
    with pytest.raises(DomainError): store.call('object.update',{'kind':'project','id':'AB','revision':True,'fields':{'name':'X'},'request_id':'bad-version'})


def test_legacy_write_invalidates_revision_and_preserves_archive(store):
    items = family(store)
    req = items['requirement']
    old = store.call('requirement.export', {'source_id':req['data']['source_id']})
    store.call('issue.update', {'key':req['id'],'description':'legacy'})
    with pytest.raises(DomainError, match='冲突'): update(store,req,{'req_name':'stale'})
    req = store.call('object.get', {'kind':'requirement','id':req['id']})
    updated = update(store,req,{'req_name':'当前名称','req_desc':'长' * 30000,'workload_md':0},'valid')
    assert updated['data']['current']['workload_md'] == 0
    issue = store.call('issue.get',{'key':req['id']})
    assert issue['title'] == '当前名称' and issue['description'] == '长' * 30000
    new = store.call('requirement.export', {'source_id':req['data']['source_id']})
    assert new['snapshot'] == old['snapshot']
    assert new['requirements'][0]['raw'] == old['requirements'][0]['raw']
    assert new['requirements'][0]['original'] == old['requirements'][0]['original']


def test_preview_detects_new_dependents_and_blockers(store):
    items = family(store)
    before = store.call('object.delete.preview',{'kind':'project','id':'AB'})
    store.call('issue.comment',{'key':items['issue']['id'],'body':'新增'})
    with pytest.raises(DomainError, match='冲突'):
        store.call('object.delete',{'kind':'project','id':'AB','confirmation':before['confirmation'],'request_id':'stale'})
    before = store.call('object.delete.preview',{'kind':'project','id':'AB'})
    store.call('issue.create',{'project':'AB','title':'新后代'})
    with pytest.raises(DomainError, match='冲突'):
        store.call('object.delete',{'kind':'project','id':'AB','confirmation':before['confirmation'],'request_id':'stale'})
    assert store.call('object.delete.preview',{'kind':'issue','id':items['issue']['id']})['blockers']
    assert not store.call('object.delete.preview',{'kind':'project','id':'AB'})['blockers']
    sid = int(items['sprint']['id'])
    store.call('sprint.start',{'id':sid})
    assert store.call('object.delete.preview',{'kind':'sprint','id':str(sid)})['blockers']
    store.call('sprint.complete',{'id':sid})
    assert not store.call('object.delete.preview',{'kind':'sprint','id':str(sid)})['blockers']


def test_http_object_create_and_hidden_project_fallback(tmp_path):
    server = make_server(tmp_path/'http.sqlite3',0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    def call(action,data):
        req = Request(root+'/api/call',data=json.dumps({'action':action,'data':data}).encode(),
                      headers={'Content-Type':'application/json','X-Forge-Client':'1'})
        with urlopen(req) as response: return json.load(response)['data']
    try:
        call('object.create',{'kind':'project','fields':{'key':'AB','name':'HTTP'},'request_id':'http'})
        preview=call('object.delete.preview',{'kind':'project','id':'AB'})
        call('object.delete',{'kind':'project','id':'AB','confirmation':preview['confirmation'],'request_id':'delete'})
        with urlopen(root+'/api/state?project=AB') as response: state=json.load(response)
        assert state['project'] == '' and state['issues'] == [] and state['projects'] == []
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_http_long_requirement_update_and_known_hidden_fallback(tmp_path):
    server=make_server(tmp_path/'long.sqlite3',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    root=f'http://127.0.0.1:{server.server_port}'
    def call(action,data):
        req=Request(root+'/api/call',data=json.dumps({'action':action,'data':data},ensure_ascii=False).encode(),
                    headers={'Content-Type':'application/json','X-Forge-Client':'1'})
        with urlopen(req) as response: return json.load(response)['data']
    try:
        call('object.create',{'kind':'project','fields':{'key':'AB','name':'P'},'request_id':'p'})
        req=call('object.create',{'kind':'requirement','fields':{'project':'AB','req_code':'R','req_name':'需求','req_desc':'长'*100000},'request_id':'r'})
        changed=call('object.update',{'kind':'requirement','id':req['id'],'revision':req['revision'],
            'fields':{'req_desc':'新'*100000},'request_id':'u'})
        assert changed['data']['current']['req_desc']=='新'*100000
        call('object.create',{'kind':'project','fields':{'key':'CD','name':'Q'},'request_id':'q'})
        preview=call('object.delete.preview',{'kind':'project','id':'AB'})
        call('object.delete',{'kind':'project','id':'AB','confirmation':preview['confirmation'],'request_id':'d'})
        with urlopen(root+'/api/state?project=AB') as response: assert json.load(response)['project']=='CD'
        with pytest.raises(HTTPError) as err: urlopen(root+'/api/state?project=NO')
        assert err.value.code==404
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_ids_cannot_bypass_tombstone_using_whitespace(store):
    item=create(store,'project',{'key':'AB','name':'项目'})
    delete(store,item)
    for ident in (' AB','AB ',' AB '):
        with pytest.raises(DomainError): store.call('object.get',{'kind':'project','id':ident})


def test_deleted_comments_disappear_from_activity_including_legacy_rows(store):
    items=family(store)
    # Simulate an audit record created before the additive migration.
    with store.connect() as db:
        db.execute("UPDATE activity SET changes=? WHERE action='issue.comment'",(json.dumps({'body':'评论'}),))
    delete(store,items['comment'])
    assert all('评论' not in str(r['changes']) for r in store.call('activity.list',{'target':items['requirement']['id']}))


def test_edited_legacy_comment_keeps_hidden_original_audit_private(store):
    items=family(store)
    with store.connect() as db:
        db.execute("UPDATE activity SET changes=? WHERE action='issue.comment'",(json.dumps({'body':'评论'}),))
    item=store.call('object.get',{'kind':'comment','id':items['comment']['id']})
    item=update(store,item,{'body':'修改后的评论'})
    delete(store,item)
    assert all('评论' not in str(r['changes']) for r in store.call('activity.list',{'target':items['requirement']['id']}))


def test_legacy_requirement_overlay_sync_and_version_validation(store):
    items=family(store)
    key=items['requirement']['id']
    result=store.call('requirement.update',{'key':key,'version':1,'fields':{'req_name':'旧接口的新名称','req_desc':'新正文','system_name':'系统'}})
    assert result['current']['req_name']=='旧接口的新名称'
    issue=store.call('issue.get',{'key':key})
    assert issue['title']=='旧接口的新名称' and issue['description']=='新正文'
    for action,data in [('requirement.update',{'key':key,'version':True,'fields':{'req_name':'非法'}}),
        ('requirement.scenario.update',{'key':key,'scenario_code':'S::1','version':True,'fields':{'title':'非法'}})]:
        with pytest.raises(DomainError): store.call(action,data)


def test_all_write_replays_do_not_reapply_and_actor_namespace_isolated(store):
    item=create(store,'project',{'key':'AB','name':'初始'},'same')
    assert store.call('object.create',{'kind':'project','fields':{'key':'CD','name':'另一个操作者'},'request_id':'same'},'other')['id']=='CD'
    payload=dict(kind='project',id='AB',revision=item['revision'],fields={'name':'第一次'},request_id='u')
    changed=store.call('object.update',payload)
    removed=delete(store,changed)
    assert store.call('object.update',payload)==changed
    assert store.call('object.get',{'kind':'project','id':'AB','include_deleted':True})==removed
    restored=restore(store,removed)
    again=delete(store,restored,'delete-again')
    assert restore(store,removed)==restored
    assert store.call('object.get',{'kind':'project','id':'AB','include_deleted':True})==again


def test_validation_whitelists_and_pagination(store):
    items=family(store)
    assert store.call('object.list',{'kind':'issue','project':'AB','limit':1,'offset':1})['total']==2
    for kind,item in items.items():
        fresh=store.call('object.get',{'kind':kind,'id':item['id']})
        for fields in ({'raw':{}},{'snapshot':{}},{'original':{}},{'project':'CD'},{'id':'123'},{'version':True}):
            with pytest.raises(DomainError): update(store,fresh,fields)
    for kind in ('issue','requirement','scenario','sprint','release','comment'):
        with pytest.raises(DomainError): create(store,kind,{'raw':{'untrusted':'data'}})
    for key,value in [('limit',True),('offset',True),('include_deleted',1)]:
        with pytest.raises(DomainError): store.call('object.list',{'kind':'project',key:value})


def test_http_bounded_large_writes_do_not_bypass_dispatch_bulk_or_origin(tmp_path):
    server=make_server(tmp_path/'limits.sqlite3',0)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    root=f'http://127.0.0.1:{server.server_port}'
    headers={'Content-Type':'application/json','X-Forge-Client':'1'}
    def post(body,path='/api/call',extra=None):
        req=Request(root+path,data=json.dumps(body).encode(),headers={**headers,**(extra or {})})
        return urlopen(req)
    try:
        for action in ('arbitrary.sql','object.list','requirement.import'):
            with pytest.raises(HTTPError) as err:
                post({'action':action,'data':{'padding':'x'*70000}})
            assert err.value.code==413
        for path,size in [('/api/call',2*1024*1024+1),('/api/requirements/import',32*1024*1024+1)]:
            conn=HTTPConnection('127.0.0.1',server.server_port)
            conn.request('POST',path,headers={**headers,'Content-Length':str(size)})
            assert conn.getresponse().status==413
            conn.close()
        for extra in ({'Origin':'https://attacker.example'},{'X-Forge-Client':''},{'Content-Type':'text/plain'}):
            with pytest.raises(HTTPError) as err:
                post({'action':'object.create','data':{'kind':'project','fields':{'key':'NO','name':'不可写'},'request_id':'bad'}},extra=extra)
            assert err.value.code in (403,415)
        bundle={'source_id':'large','projects':[{'project_code':'AB','project_name':'项目'}],
            'requirements':[{'req_code':'R','project_code':'AB','req_name':'需求','req_desc':'正文'}],
            'documents':{'large':'x'*(2*1024*1024+1)}}
        with post({'action':'requirement.import','data':{'bundle':bundle}},'/api/requirements/import') as response:
            assert json.load(response)['data']['requirements']==1
        with post({'action':'object.list','data':{'kind':'project'}}) as response:
            assert [r['id'] for r in json.load(response)['data']['items']]==['AB']
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('kind,action,fields,legacy',[
    ('project','issue.create',{'name':'新名称'},{'project':'AB','title':'后代'}),
    ('issue','issue.update',{'title':'新名称'},{'key':'AB-1','title':'旧写入'}),
    ('requirement','requirement.update',{'req_name':'新名称'},{'key':'AB-2','version':1,'fields':{'req_name':'旧写入'}}),
    ('scenario','requirement.scenario.update',{'title':'新名称'},{'key':'AB-2','scenario_code':'S::1','version':1,'fields':{'title':'旧写入'}}),
    ('sprint','sprint.start',{'name':'新名称'},{'id':1}),
    ('release','release.update',{'name':'新名称'},{'id':1,'notes':'旧写入'})])
def test_revision_detects_each_legacy_writer(store,kind,action,fields,legacy):
    items=family(store)
    before=store.call('object.get',{'kind':kind,'id':items[kind]['id']})
    store.call(action,legacy)
    with pytest.raises(DomainError,match='冲突'): update(store,before,fields)
