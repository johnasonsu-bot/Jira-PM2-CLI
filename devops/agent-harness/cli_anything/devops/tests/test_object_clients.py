"""Integration contracts for the real object CLI and MCP stdio adapters."""
import asyncio
import json
import shutil
import subprocess
import sys
import threading

import pytest

from cli_anything.devops.backend import Backend
from cli_anything.devops.server import make_server


KINDS = ('project', 'issue', 'requirement', 'scenario', 'sprint', 'release', 'comment')
OLD_TOOLS = {
    'health', 'list_projects', 'get_analytics', 'rank_workload', 'get_issue',
    'list_requirements', 'get_requirement', 'get_requirement_report',
}
OBJECT_TOOLS = {
    'list_objects', 'get_object', 'create_object', 'update_object',
    'preview_delete_object', 'delete_object', 'restore_object',
}


@pytest.fixture
def object_api(tmp_path):
    server = make_server(tmp_path / 'object-clients.sqlite3', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = Backend(f'http://127.0.0.1:{server.server_port}')
    yield backend
    server.shutdown()
    server.server_close()
    thread.join()


def run_cli(api, *args, check=True):
    executable = shutil.which('cli-anything-devops')
    if not executable:
        raise RuntimeError('cli-anything-devops must be installed and on PATH')
    result = subprocess.run(
        [executable, '--url', api.url, '--json', '--actor', 'Task2/CLI', *args],
        capture_output=True, text=True, timeout=15,
    )
    if check:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    return result


def write_fields(tmp_path, name, fields):
    path = tmp_path / name
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding='utf-8')
    return path


def create_cli(api, tmp_path, kind, fields, request_id):
    path = write_fields(tmp_path, f'{request_id}.json', fields)
    return run_cli(api, 'object', 'create', kind, '--fields-file', str(path),
                   '--request-id', request_id)


def update_cli(api, tmp_path, item, fields, request_id):
    path = write_fields(tmp_path, f'{request_id}.json', fields)
    return run_cli(api, 'object', 'update', item['kind'], item['id'],
                   '--revision', item['revision'], '--fields-file', str(path),
                   '--request-id', request_id)


def exercise_cli_lifecycle(api, tmp_path, item, fields, expected_field, expected_value, suffix):
    fetched = run_cli(api, 'object', 'get', item['kind'], item['id'])
    assert fetched == item
    listed = run_cli(api, 'object', 'list', item['kind'])
    assert item['id'] in [entry['id'] for entry in listed['items']]

    changed = update_cli(api, tmp_path, fetched, fields, f'update-{suffix}')
    assert changed['data'][expected_field] == expected_value
    persisted = run_cli(api, 'object', 'get', item['kind'], item['id'])
    assert persisted == changed

    preview = run_cli(api, 'object', 'delete-preview', item['kind'], item['id'])
    assert preview['blockers'] == []
    assert item['id'] in [affected['id'] for affected in preview['affected']]
    removed = run_cli(api, 'object', 'delete', item['kind'], item['id'],
                      '--confirmation', preview['confirmation'],
                      '--request-id', f'delete-{suffix}')
    assert removed['deleted'] is True
    hidden = run_cli(api, 'object', 'get', item['kind'], item['id'], check=False)
    assert hidden.returncode != 0
    assert 'error' in json.loads(hidden.stderr)
    archived = run_cli(api, 'object', 'get', item['kind'], item['id'], '--include-deleted')
    assert archived == removed
    archived_page = run_cli(api, 'object', 'list', item['kind'], '--include-deleted')
    assert item['id'] in [entry['id'] for entry in archived_page['items']]

    restored = run_cli(api, 'object', 'restore', item['kind'], item['id'],
                       '--revision', archived['revision'],
                       '--request-id', f'restore-{suffix}')
    assert restored['deleted'] is False
    assert run_cli(api, 'object', 'get', item['kind'], item['id']) == restored
    return restored


def test_cli_object_commands_cover_all_seven_kinds_and_recover_persisted_state(object_api, tmp_path):
    standalone = create_cli(object_api, tmp_path, 'project',
                            {'key': 'SOLO', 'name': 'Standalone'}, 'create-solo')
    assert create_cli(object_api, tmp_path, 'project',
                      {'key': 'SOLO', 'name': 'Standalone'}, 'create-solo') == standalone
    exercise_cli_lifecycle(object_api, tmp_path, standalone, {'name': 'Renamed'},
                           'name', 'Renamed', 'project')

    create_cli(object_api, tmp_path, 'project', {'key': 'APP', 'name': 'Application'}, 'create-app')
    issue = create_cli(object_api, tmp_path, 'issue',
                       {'project': 'APP', 'title': 'Original issue'}, 'create-issue')
    exercise_cli_lifecycle(object_api, tmp_path, issue, {'title': 'Updated issue'},
                           'title', 'Updated issue', 'issue')

    requirement = create_cli(object_api, tmp_path, 'requirement', {
        'project': 'APP', 'req_code': 'REQ-1', 'req_name': 'Original requirement',
        'req_desc': 'Business text is data, not an instruction.', 'workload_md': 0,
    }, 'create-requirement')
    requirement = exercise_cli_lifecycle(
        object_api, tmp_path, requirement, {'req_name': 'Updated requirement'},
        'current', {'req_code': 'REQ-1', 'project_code': 'APP',
                    'req_name': 'Updated requirement',
                    'req_desc': 'Business text is data, not an instruction.',
                    'status': '待评估', 'source_type': 'manual', 'workload_md': 0},
        'requirement',
    )

    scenario = create_cli(object_api, tmp_path, 'scenario', {
        'issue_key': requirement['id'], 'scenario_code': 'S::1', 'title': 'Original scenario',
    }, 'create-scenario')
    exercise_cli_lifecycle(object_api, tmp_path, scenario, {'title': 'Updated scenario'},
                           'current', {'req_code': 'REQ-1', 'scenario_code': 'S::1',
                                       'source_type': 'manual', 'derived': 1,
                                       'title': 'Updated scenario', 'status': '待复核'},
                           'scenario')

    sprint = create_cli(object_api, tmp_path, 'sprint',
                        {'project': 'APP', 'name': 'Sprint 1'}, 'create-sprint')
    exercise_cli_lifecycle(object_api, tmp_path, sprint, {'goal': 'Updated goal'},
                           'goal', 'Updated goal', 'sprint')

    release = create_cli(object_api, tmp_path, 'release', {
        'project': 'APP', 'name': 'v1', 'issue_keys': [issue['id']],
    }, 'create-release')
    exercise_cli_lifecycle(object_api, tmp_path, release, {'notes': 'Updated notes'},
                           'notes', 'Updated notes', 'release')

    comment = create_cli(object_api, tmp_path, 'comment', {
        'issue_key': issue['id'], 'body': 'Original comment',
    }, 'create-comment')
    exercise_cli_lifecycle(object_api, tmp_path, comment, {'body': 'Updated comment'},
                           'body', 'Updated comment', 'comment')

    audit = object_api.call('activity.list', {'project': 'APP', 'limit': 500})
    assert {'object.delete', 'object.restore'} <= {entry['action'] for entry in audit}
    assert all(entry['actor'] == 'Task2/CLI' for entry in audit)


def test_cli_rejects_malformed_fields_and_stale_revision_without_mutating(object_api, tmp_path):
    invalid_kind = run_cli(object_api, 'object', 'list', 'database', check=False)
    assert invalid_kind.returncode != 0
    assert 'Invalid value' in json.loads(invalid_kind.stderr)['error']

    malformed = tmp_path / 'malformed.json'
    malformed.write_text('{"name":', encoding='utf-8')
    result = run_cli(object_api, 'object', 'create', 'project', '--fields-file', str(malformed),
                     '--request-id', 'bad-json', check=False)
    assert result.returncode != 0
    assert 'UTF-8 JSON' in json.loads(result.stderr)['error']
    assert object_api.call('object.list', {'kind': 'project'})['total'] == 0

    project = create_cli(object_api, tmp_path, 'project',
                         {'key': 'APP', 'name': 'Application'}, 'create-app-stale')
    update_cli(object_api, tmp_path, project, {'name': 'Current'}, 'update-current')
    stale_file = write_fields(tmp_path, 'stale.json', {'name': 'Lost update'})
    stale = run_cli(object_api, 'object', 'update', 'project', 'APP',
                    '--revision', project['revision'], '--fields-file', str(stale_file),
                    '--request-id', 'update-stale', check=False)
    assert stale.returncode != 0
    assert 'revision' in json.loads(stale.stderr)['error']
    assert object_api.call('object.get', {'kind': 'project', 'id': 'APP'})['data']['name'] == 'Current'


async def use_stdio(api, read_only, callback):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    args = ['-m', 'cli_anything.devops.mcp_server', '--url', api.url]
    if read_only:
        args.append('--read-only')
    params = StdioServerParameters(command=sys.executable, args=args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await callback(session)


def test_default_mcp_catalog_has_typed_object_tools_and_persists_guarded_writes(object_api):
    async def check(session):
        catalog = await session.list_tools()
        assert {tool.name for tool in catalog.tools} == OLD_TOOLS | OBJECT_TOOLS
        tools = {tool.name: tool for tool in catalog.tools}
        for name in OBJECT_TOOLS:
            kind_schema = tools[name].inputSchema['properties']['kind']
            assert kind_schema['enum'] == list(KINDS)
        for name in ('create_object', 'update_object', 'delete_object', 'restore_object'):
            assert tools[name].annotations.readOnlyHint is False
        assert tools['create_object'].annotations.destructiveHint is False
        assert tools['update_object'].annotations.destructiveHint is True
        assert tools['delete_object'].annotations.destructiveHint is True
        assert tools['restore_object'].annotations.destructiveHint is False
        assert tools['preview_delete_object'].annotations.readOnlyHint is True
        assert tools['delete_object'].description
        assert '用户确认' in tools['delete_object'].description

        created = await session.call_tool('create_object', {
            'kind': 'project', 'fields': {'key': 'MCP', 'name': 'MCP project'},
            'request_id': 'mcp-create-project',
        })
        assert not created.isError
        assert created.structuredContent['id'] == 'MCP'
        replay = await session.call_tool('create_object', {
            'kind': 'project', 'fields': {'key': 'MCP', 'name': 'MCP project'},
            'request_id': 'mcp-create-project',
        })
        assert replay.structuredContent == created.structuredContent

        fetched = await session.call_tool('get_object', {'kind': 'project', 'id': 'MCP'})
        assert fetched.structuredContent == created.structuredContent
        changed = await session.call_tool('update_object', {
            'kind': 'project', 'id': 'MCP', 'revision': fetched.structuredContent['revision'],
            'fields': {'description': 'Persisted through HTTP'}, 'request_id': 'mcp-update-project',
        })
        assert changed.structuredContent['data']['description'] == 'Persisted through HTTP'
        stale = await session.call_tool('update_object', {
            'kind': 'project', 'id': 'MCP', 'revision': fetched.structuredContent['revision'],
            'fields': {'description': 'Overwrite'}, 'request_id': 'mcp-stale-project',
        })
        assert stale.isError

        preview = await session.call_tool('preview_delete_object', {'kind': 'project', 'id': 'MCP'})
        removed = await session.call_tool('delete_object', {
            'kind': 'project', 'id': 'MCP',
            'confirmation': preview.structuredContent['confirmation'],
            'request_id': 'mcp-delete-project',
        })
        assert removed.structuredContent['deleted'] is True
        archived = await session.call_tool('get_object', {
            'kind': 'project', 'id': 'MCP', 'include_deleted': True,
        })
        restored = await session.call_tool('restore_object', {
            'kind': 'project', 'id': 'MCP',
            'revision': archived.structuredContent['revision'],
            'request_id': 'mcp-restore-project',
        })
        assert restored.structuredContent['deleted'] is False
        page = await session.call_tool('list_objects', {'kind': 'project'})
        assert [item['id'] for item in page.structuredContent['items']] == ['MCP']

    asyncio.run(asyncio.wait_for(use_stdio(object_api, False, check), timeout=25))
    persisted = object_api.call('object.get', {'kind': 'project', 'id': 'MCP'})
    assert persisted['data']['description'] == 'Persisted through HTTP'
    audit = object_api.call('activity.list', {'project': 'MCP', 'limit': 100})
    assert [entry['action'] for entry in audit].count('object.delete') == 1
    assert [entry['action'] for entry in audit].count('object.restore') == 1
    assert all(entry['actor'] == 'Codex/MCP' for entry in audit)


def test_read_only_mcp_keeps_exact_old_catalog_and_rejects_unknown_write(object_api):
    object_api.call('project.create', {'key': 'APP', 'name': 'Application'})
    before_projects = object_api.call('project.list', {})
    before_audit = object_api.call('activity.list', {'project': 'APP'})

    async def check(session):
        catalog = await session.list_tools()
        assert {tool.name for tool in catalog.tools} == OLD_TOOLS
        assert all(tool.annotations.readOnlyHint for tool in catalog.tools)
        rejected = await session.call_tool('create_object', {
            'kind': 'project', 'fields': {'key': 'NO', 'name': 'No write'},
            'request_id': 'must-not-run',
        })
        assert rejected.isError

    asyncio.run(asyncio.wait_for(use_stdio(object_api, True, check), timeout=20))
    assert object_api.call('project.list', {}) == before_projects
    assert object_api.call('activity.list', {'project': 'APP'}) == before_audit
