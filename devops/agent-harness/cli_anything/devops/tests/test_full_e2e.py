import json
import os
import shutil
import subprocess
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest
from cli_anything.devops.server import make_server

@pytest.fixture
def server(tmp_path):
    srv = make_server(tmp_path / 'live.sqlite3', port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join()

def base(server):
    return f'http://127.0.0.1:{server.server_port}'

def call(server, action, data, **headers):
    req = Request(base(server) + '/api/call', data=json.dumps({'action': action, 'data': data}).encode(),
                  headers={'Content-Type': 'application/json', 'X-Forge-Client': '1', **headers})
    with urlopen(req, timeout=5) as r:
        return json.load(r)['data']

def _resolve_cli(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} must be installed and on PATH')
    return path

def cli(server, *args, check=True):
    result = subprocess.run([_resolve_cli('cli-anything-devops'), '--url', base(server), '--json', '--actor', 'Codex验收', *args],
                            capture_output=True, text=True, timeout=10)
    if check:
        assert result.returncode == 0, result.stderr
    return result

def test_installed_cli_to_real_api_roundtrip(server):
    project = json.loads(cli(server, 'project', 'create', '--key', 'APP', '--name', '验收项目').stdout)
    assert project['key'] == 'APP'
    sprint = json.loads(cli(server, 'sprint', 'create', '--project', 'APP', '--name', 'Sprint 1').stdout)
    result = cli(server, 'issue', 'create', '--project', 'APP', '--title', '修复登录错误', '--type', 'bug', '--sprint', str(sprint['id']))
    key = json.loads(result.stdout)['key']
    assert call(server, 'issue.get', {'key': key})['title'] == '修复登录错误'
    call(server, 'issue.update', {'key': key, 'status': 'in_progress'})
    assert json.loads(cli(server, 'issue', 'get', key).stdout)['status'] == 'in_progress'
    cli(server, 'issue', 'move', key, 'done')
    cli(server, 'issue', 'comment', key, '--body', '已通过端到端验证')
    detail = call(server, 'issue.get', {'key': key})
    assert detail['comments'][0]['actor'] == 'Codex验收'
    release = json.loads(cli(server, 'release', 'create', '--project', 'APP', '--name', 'v1', '--issue', key).stdout)
    revised = json.loads(cli(server, 'release', 'update', str(release['id']), '--notes', '验收通过', '--issue', key).stdout)
    assert revised['notes'] == '验收通过' and revised['issue_keys'] == [key]
    cli(server, 'release', 'promote', str(release['id']), 'released')
    assert call(server, 'release.list', {'project': 'APP'})[0]['status'] == 'released'
    assert json.loads(cli(server, 'report', '--project', 'APP').stdout)['done'] == 1
    assert json.loads(cli(server, 'issue', 'list', '--project', 'APP', '--status', 'done').stdout)[0]['key'] == key

def test_cli_errors_are_json_and_nonzero(server):
    result = cli(server, 'issue', 'get', 'MISSING-1', check=False)
    assert result.returncode != 0
    assert 'error' in json.loads(result.stderr)

@pytest.mark.parametrize('headers', [
    {'Origin': 'https://attacker.example'}, {'Host': 'attacker.example'},
    {'Content-Type': 'text/plain'}, {'X-Forge-Client': ''},
])
def test_reject_foreign_browser_mutations(server, headers):
    with pytest.raises(HTTPError) as err:
        call(server, 'project.create', {'key': 'BAD', 'name': 'bad'}, **headers)
    assert err.value.code in (403, 415)
    assert call(server, 'project.list', {}) == []

def test_bad_json_and_oversize_are_rejected(server):
    for body, code in [(b'{', 400), (b'x' * 70000, 413), (b'[]', 400)]:
        req = Request(base(server) + '/api/call', data=body, headers={'Content-Type':'application/json', 'X-Forge-Client':'1'})
        with pytest.raises(HTTPError) as err:
            urlopen(req, timeout=5)
        assert err.value.code == code

def test_health_and_export_state(server):
    with urlopen(base(server) + '/api/health') as r:
        assert json.load(r)['ok'] is True
    call(server, 'project.create', {'key':'APP', 'name':'应用'})
    call(server, 'issue.create', {'project':'APP', 'title':'页面同步'})
    with urlopen(base(server) + '/api/state?project=APP') as r:
        state = json.load(r)
    assert state['summary']['total'] == 1
    assert state['issues'][0]['title'] == '页面同步'

def test_management_cli_matches_browser_and_never_mutates(server):
    call(server,'project.create',{'key':'APP','name':'项目'})
    sprint = call(server,'sprint.create',{'project':'APP','name':'当前迭代'})
    call(server,'sprint.start',{'id':sprint['id']})
    call(server,'issue.create',{'project':'APP','title':'待验收','status':'review','priority':'high','points':5,'sprint_id':sprint['id']})
    before = call(server,'activity.list',{'project':'APP'})
    report = json.loads(cli(server,'analytics','--project','APP','--scope','active').stdout)
    with urlopen(base(server)+'/api/state?project=APP') as r:
        state = json.load(r)
    assert report['metrics']['review'] == 1
    assert report['metrics'] == state['analytics']['active']['metrics']
    assert call(server,'activity.list',{'project':'APP'}) == before
