from concurrent.futures import ThreadPoolExecutor
import pytest
from cli_anything.devops.store import Store, DomainError

@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / 'data.sqlite3')
    db.call('project.create', {'key': 'APP', 'name': '应用研发'})
    return db

def issue(store, **kwargs):
    return store.call('issue.create', {'project': 'APP', 'title': '登录错误', **kwargs})

def test_persistence_and_audit(store):
    item = issue(store)
    store.call('issue.update', {'key': item['key'], 'status': 'in_progress'}, 'Codex')
    store.call('issue.comment', {'key': item['key'], 'body': '已定位问题'}, 'Codex')
    reopened = Store(store.path)
    detail = reopened.call('issue.get', {'key': 'APP-1'})
    assert detail['status'] == 'in_progress'
    assert detail['comments'][0]['body'] == '已定位问题'
    assert detail['activity'][0]['actor'] == 'Codex'

@pytest.mark.parametrize('change', [{'status': 'fake'}, {'points': -1}, {'priority': 'urgent'}, {'type': 'fake'}, {'title': '  '}, {'points': True}, {'owner': 'me'}])
def test_reject_invalid_issue_fields(store, change):
    item = issue(store)
    with pytest.raises(DomainError):
        store.call('issue.update', {'key': item['key'], **change})
    assert store.call('issue.get', {'key': item['key']})['version'] == 1

def test_concurrent_unique_issue_numbers(store):
    with ThreadPoolExecutor(max_workers=5) as pool:
        items = list(pool.map(lambda i: issue(store, title=f'任务 {i}'), range(15)))
    assert len({i['key'] for i in items}) == 15
    assert store.call('report.summary', {'project': 'APP'})['total'] == 15

def test_stale_update_conflicts(store):
    item = issue(store)
    store.call('issue.update', {'key': item['key'], 'title': '新标题', 'version': 1})
    with pytest.raises(DomainError, match='冲突'):
        store.call('issue.update', {'key': item['key'], 'title': '旧覆盖', 'version': 1})

def test_sprint_project_boundaries_and_complete(store):
    store.call('project.create', {'key': 'OPS', 'name': '运维'})
    sprint = store.call('sprint.create', {'project': 'APP', 'name': '第一期'})
    with pytest.raises(DomainError):
        store.call('issue.create', {'project': 'OPS', 'title': '跨项目', 'sprint_id': sprint['id']})
    item = issue(store, sprint_id=sprint['id'])
    store.call('sprint.start', {'id': sprint['id']})
    other = store.call('sprint.create', {'project': 'APP', 'name': '第二期'})
    with pytest.raises(DomainError):
        store.call('sprint.start', {'id': other['id']})
    store.call('sprint.complete', {'id': sprint['id']})
    assert store.call('issue.get', {'key': item['key']})['sprint_id'] is None
    with pytest.raises(DomainError):
        issue(store, sprint_id=sprint['id'])

def test_release_requires_done_issues_and_same_project(store):
    item = issue(store)
    release = store.call('release.create', {'project': 'APP', 'name': 'v1.0', 'issue_keys': [item['key']]})
    with pytest.raises(DomainError):
        store.call('release.update', {'id': release['id'], 'status': 'released'})
    store.call('issue.update', {'key': item['key'], 'status': 'done'})
    assert store.call('release.update', {'id': release['id'], 'status': 'released'})['status'] == 'released'
    with pytest.raises(DomainError):
        store.call('release.create', {'project': 'APP', 'name': 'duplicate', 'issue_keys': ['NO-1']})

def test_filters_report_and_unknown_action(store):
    issue(store, type='bug', priority='high', assignee='Sushi')
    issue(store, title='文档', status='done', points=3)
    assert len(store.call('issue.list', {'project': 'APP', 'q': '登录', 'assignee': 'Sushi'})) == 1
    report = store.call('report.summary', {'project': 'APP'})
    assert report['done'] == 1 and report['total'] == 2 and report['done_points'] == 3
    with pytest.raises(DomainError):
        store.call('arbitrary.command', {})

def test_release_rejects_empty_issue_links(store):
    with pytest.raises(DomainError, match='至少'):
        store.call('release.create', {'project': 'APP', 'name': 'empty', 'issue_keys': []})
    assert store.call('release.list', {'project': 'APP'}) == []

def test_release_normalizes_and_deduplicates_links(store):
    item = issue(store, status='done')
    release = store.call('release.create', {'project': 'APP', 'name': 'normalized',
                                          'issue_keys': [' APP-1 ', item['key']]})
    assert release['issue_keys'] == ['APP-1']
    assert store.call('release.update', {'id': release['id'], 'status': 'released'})['status'] == 'released'

def test_edit_release_links_notes_and_immutable_published(store):
    first = issue(store, status='done')
    second = issue(store, status='done')
    release = store.call('release.create', {'project': 'APP', 'name': 'before', 'issue_keys': [first['key']]})
    updated = store.call('release.update', {'id': release['id'], 'name': 'after', 'notes': 'updated',
                                          'issue_keys': [' APP-2 ', 'APP-2']})
    assert updated['name'] == 'after' and updated['notes'] == 'updated'
    assert updated['issue_keys'] == [second['key']] and updated['status'] == 'planned'
    with pytest.raises(DomainError):
        store.call('release.update', {'id': release['id'], 'issue_keys': []})
    store.call('project.create', {'key': 'OPS', 'name': '运维'})
    store.call('issue.create', {'project': 'OPS', 'title': 'other'})
    with pytest.raises(DomainError):
        store.call('release.update', {'id': release['id'], 'issue_keys': ['OPS-1']})
    store.call('release.update', {'id': release['id'], 'status': 'released'})
    with pytest.raises(DomainError):
        store.call('release.update', {'id': release['id'], 'notes': 'rewrite history'})
