from datetime import date, timedelta, datetime, timezone
import pytest
from cli_anything.devops.store import Store, DomainError

@pytest.fixture
def sample(tmp_path):
    store = Store(tmp_path/'analytics.sqlite3')
    store.call('project.create', {'key':'APP','name':'项目'})
    store.call('project.create', {'key':'OPS','name':'其他项目'})
    today = date.today()
    sprint = store.call('sprint.create', {'project':'APP','name':'当前迭代',
        'start_date':(today-timedelta(days=4)).isoformat(),'end_date':(today+timedelta(days=6)).isoformat()})
    store.call('sprint.start', {'id':sprint['id']})
    data = [
        {'status':'done','points':3,'assignee':'A','due_date':(today-timedelta(days=1)).isoformat()},
        {'status':'review','points':5,'assignee':'A','type':'bug','priority':'high','due_date':(today-timedelta(days=1)).isoformat()},
        {'status':'in_progress','points':0,'type':'bug','priority':'critical','due_date':(today+timedelta(days=1)).isoformat()},
        {'status':'todo','points':2,'assignee':'B'},
    ]
    for i, fields in enumerate(data):
        store.call('issue.create', {'project':'APP','title':f'工作{i}','sprint_id':sprint['id'],**fields})
    store.call('issue.create', {'project':'APP','title':'范围外','points':13,'priority':'high'})
    store.call('issue.create', {'project':'OPS','title':'其他项目','points':99})
    old = (datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
    with store.connect() as db:
        db.execute('UPDATE issues SET updated_at=? WHERE key=?',(old,'APP-2'))
    store.call('release.create', {'project':'APP','name':'可发布','issue_keys':['APP-1']})
    store.call('release.create', {'project':'APP','name':'门禁未通过','issue_keys':['APP-2']})
    return store, sprint

def test_active_scope_metrics_exclude_other_projects_and_backlog(sample):
    store, sprint = sample
    report = store.call('report.analytics', {'project':'APP','scope':'active'})
    assert report['sprint']['id'] == sprint['id']
    m = report['metrics']
    assert (m['total'],m['points'],m['done'],m['done_pct'],m['points_done_pct']) == (4,10,1,25,30)
    assert (m['open'],m['remaining_points'],m['review'],m['in_progress']) == (3,7,1,1)
    assert (m['high_open'],m['critical_open'],m['open_bugs']) == (2,1,2)
    assert (m['overdue'],m['due_soon'],m['undated_open'],m['unassigned_open'],m['zero_points_open'],m['stale_open']) == (1,1,1,1,1,1)
    assert m['due_date_coverage_pct'] == 75
    assert report['timeline']['days_to_end'] == 6
    assert report['timeline']['elapsed_pct'] == 40
    assert {i['key'] for i in report['risks']} == {'APP-2','APP-3','APP-4'}
    assert store.call('report.analytics', {'project':'APP','scope':'project'})['metrics']['points'] == 23

def test_workload_and_project_level_release_gate(sample):
    store, _ = sample
    report = store.call('report.analytics', {'project':'APP','scope':'active'})
    a = next(row for row in report['workload'] if row['assignee']=='A')
    assert (a['total'],a['points'],a['open_points'],a['done_points'],a['overdue']) == (2,8,5,3,1)
    assert report['release_scope'] == 'project'
    assert {r['name']:r['ready'] for r in report['releases']} == {'可发布':True,'门禁未通过':False}
    assert report['unavailable']['velocity']
    assert report['unavailable']['blocked']

def test_empty_scope_and_zero_estimate_do_not_report_fake_completion(sample):
    store, _ = sample
    planned = store.call('sprint.create', {'project':'APP','name':'还未排工作'})
    report = store.call('report.analytics', {'project':'APP','scope':f"sprint:{planned['id']}"})
    assert report['metrics']['total'] == 0
    assert report['metrics']['done_pct'] is None
    assert report['metrics']['points_done_pct'] is None
    assert report['timeline'] is None
    report = store.call('report.analytics', {'project':'OPS','scope':'active'})
    assert report['sprint'] is None and report['metrics']['total'] == 0
    all_scopes = store.call('report.analytics', {'project':'APP','scope':'all'})
    assert all_scopes['active']['metrics']['total'] == 4
    assert all_scopes[f"sprint:{planned['id']}"]['metrics']['total'] == 0

@pytest.mark.parametrize('scope',['bad','sprint:no','sprint:999','sprint:-1'])
def test_invalid_scope_rejected(sample,scope):
    store, _ = sample
    with pytest.raises(DomainError):
        store.call('report.analytics', {'project':'APP','scope':scope})
