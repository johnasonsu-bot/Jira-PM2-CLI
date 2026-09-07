"""Contract tests: real analytics, real HTTP and actual stdio MCP transport."""
import asyncio
import copy
import socket
import sys
import threading
from datetime import date, timedelta

import pytest

from cli_anything.devops.backend import Backend
from cli_anything.devops.server import make_server


@pytest.fixture
def api(tmp_path):
    server = make_server(tmp_path / 'mcp.sqlite3', port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = Backend(f'http://127.0.0.1:{server.server_port}')
    backend.call('project.create', {'key': 'DEMO', 'name': '排名演示'})
    backend.call('project.create', {'key': 'EMPTY', 'name': '空项目'})
    for assignee, points, status in [
        ('A', 5, 'in_progress'), ('A', 100, 'done'),
        ('B', 3, 'review'), ('B', 2, 'todo'),
        ('C', 3, 'review'), ('C', 2, 'todo'),
        ('D', 50, 'done'), ('', 13, 'backlog'),
    ]:
        backend.call('issue.create', {'project': 'DEMO', 'title': 'fixture',
            'assignee': assignee, 'points': points, 'status': status,
            'due_date': (date.today() - timedelta(days=1)).isoformat()})
    yield backend
    server.shutdown()
    server.server_close()
    thread.join()


def test_ranking_uses_pending_points_ties_and_separate_unassigned(api):
    from cli_anything.devops.workload import rank_report
    report = api.call('report.analytics', {'project': 'DEMO', 'scope': 'project'})
    before = copy.deepcopy(report)
    ranked = rank_report(report)
    assert [(r['rank'], r['assignee'], r['open_points'], r['open'])
            for r in ranked['ranking']] == [(1, 'B', 5, 2), (1, 'C', 5, 2), (3, 'A', 5, 1)]
    assert ranked['unassigned']['open_points'] == 13
    assert ranked['excluded_completed_only'] == 1
    assert ranked['ranking'][2]['in_progress'] == 1
    assert ranked['ranking'][0]['overdue'] == 2
    assert ranked['coverage']['undated_open'] == 0
    assert report == before


def test_ranking_empty_scope_and_sort_validation(api):
    from cli_anything.devops.workload import rank_report
    report = api.call('report.analytics', {'project': 'DEMO', 'scope': 'active'})
    assert rank_report(report)['ranking'] == []
    assert rank_report(report)['coverage']['positive_points_pct'] is None
    report = api.call('report.analytics', {'project': 'DEMO', 'scope': 'project'})
    assert rank_report(report, 'in_progress')['ranking'][0]['assignee'] == 'A'
    with pytest.raises(ValueError):
        rank_report(report, 'performance')


def test_zero_points_are_not_missing_people(api):
    from cli_anything.devops.workload import rank_report
    api.call('issue.create', {'project': 'EMPTY', 'title': 'unestimated', 'assignee': 'Zero'})
    report = api.call('report.analytics', {'project': 'EMPTY', 'scope': 'project'})
    result = rank_report(report)
    assert result['ranking'][0]['assignee'] == 'Zero'
    assert result['ranking'][0]['open_points'] == 0
    assert result['coverage']['zero_points_open'] == 1


def test_open_coverage_does_not_hide_unestimated_work_behind_done_items(api):
    from cli_anything.devops.workload import rank_report
    for status, points, owner in [('done', 3, ''), ('done', 5, ''), ('todo', 0, 'A')]:
        api.call('issue.create', {'project': 'EMPTY', 'title': 'coverage',
                                'status': status, 'points': points, 'assignee': owner})
    result = rank_report(api.call('report.analytics', {'project': 'EMPTY', 'scope': 'project'}))
    assert result['coverage']['positive_points_pct'] == 66.7
    assert result['coverage']['open_positive_points_pct'] == 0
    assert result['coverage']['open_assignee_coverage_pct'] == 100
    assert result['coverage']['open_due_date_coverage_pct'] == 0
    empty = rank_report(api.call('report.analytics', {'project': 'EMPTY', 'scope': 'active'}))
    assert empty['coverage']['open_positive_points_pct'] is None


def test_stdio_tools_use_live_api_and_cannot_mutate(api):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    before = api.call('activity.list', {'project': 'DEMO'})
    issues_before = api.call('issue.list', {'project': 'DEMO'})

    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'cli_anything.devops.mcp_server', '--url', api.url])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                catalog = await session.list_tools()
                assert {t.name for t in catalog.tools} == {
                    'health', 'list_projects', 'get_analytics', 'rank_workload', 'get_issue',
                    'list_requirements', 'get_requirement', 'get_requirement_report'}
                assert all(t.annotations.readOnlyHint for t in catalog.tools)
                health = await session.call_tool('health', {})
                assert not health.isError and health.structuredContent['ok']
                projects = await session.call_tool('list_projects', {})
                assert len(projects.structuredContent['projects']) == 2
                result = await session.call_tool('rank_workload', {'project': 'DEMO'})
                assert not result.isError
                assert result.structuredContent['ranking'][0]['assignee'] == 'B'
                assert result.structuredContent['is_demo'] is True
                assert result.structuredContent['project_info']['key'] == 'DEMO'
                analytics = await session.call_tool('get_analytics', {'project': 'DEMO', 'scope': 'active'})
                assert analytics.structuredContent['metrics']['total'] == 0
                item = await session.call_tool('get_issue', {'key': 'DEMO-1'})
                assert item.structuredContent['assignee'] == 'A'
                for name, args in [
                    ('rank_workload', {'project': 'MISSING'}),
                    ('rank_workload', {'project': 'DEMO', 'scope': 'all'}),
                    ('rank_workload', {'project': 'DEMO', 'scope': 'sprint:999'}),
                    ('rank_workload', {'project': 'DEMO', 'sort_by': 'performance'}),
                    ('issue.create', {'project': 'DEMO', 'title': 'not allowed'}),
                ]:
                    result = await session.call_tool(name, args)
                    assert result.isError
    asyncio.run(asyncio.wait_for(run(), timeout=20))
    assert api.call('activity.list', {'project': 'DEMO'}) == before
    assert api.call('issue.list', {'project': 'DEMO'}) == issues_before


def test_mcp_rejects_remote_backend():
    from cli_anything.devops.mcp_server import create_mcp
    with pytest.raises(ValueError):
        create_mcp('https://example.com')


def test_offline_backend_returns_mcp_error_without_starting_service():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    # Reserve a non-listening local port to make connection refusal deterministic.
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{reserved.getsockname()[1]}'

        async def run():
            params = StdioServerParameters(command=sys.executable,
                args=['-m', 'cli_anything.devops.mcp_server', '--url', url])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool('health', {})
                    assert result.isError
                    assert any('无法连接' in block.text for block in result.content if block.type == 'text')
        asyncio.run(asyncio.wait_for(run(), timeout=10))
