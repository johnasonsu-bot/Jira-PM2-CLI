#!/usr/bin/env python3
"""Independent CLI acceptance; always creates and retains an isolated database.

Run with the Python environment that has cli-anything-devops installed.
There is deliberately no option to select an existing database or server.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from cli_anything.devops.server import make_server


def main():
    workspace = Path(tempfile.mkdtemp(prefix='forge-cli-acceptance-'))
    db_path = workspace / 'isolated.sqlite3'
    counter = 0
    server = make_server(db_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def cli(*args, fails=False):
        result = subprocess.run(
            [sys.executable, '-m', 'cli_anything.devops.devops_cli',
             '--url', f'http://127.0.0.1:{server.server_port}',
             '--actor', 'Isolated acceptance', '--json', *args],
            capture_output=True, text=True, timeout=20)
        if fails:
            assert result.returncode != 0, result.stdout
            assert json.loads(result.stderr)['error'], result.stderr
            return None
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def fields_file(fields):
        nonlocal counter
        counter += 1
        path = workspace / f'fields-{counter}.json'
        path.write_text(json.dumps(fields, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def get(item, deleted=False):
        flags = ['--include-deleted'] if deleted else []
        return cli('object', 'get', item['kind'], item['id'], *flags)

    def create(kind, fields):
        args = ['object', 'create', kind, '--fields-file', fields_file(fields),
                '--request-id', f'create-{kind}']
        item = cli(*args)
        assert cli(*args) == item, 'Retry must replay the original result'
        assert get(item) == item
        return item

    def update(item, fields):
        args = ['object', 'update', item['kind'], item['id'],
                '--revision', get(item)['revision'], '--fields-file', fields_file(fields),
                '--request-id', f'update-{item["kind"]}']
        changed = cli(*args)
        assert changed['revision'] != item['revision']
        assert cli(*args) == changed
        assert get(item) == changed
        # A different request must not reuse the revision of the old object.
        cli(*args[:-1], f'stale-{item["kind"]}', fails=True)
        return changed

    def delete(item, suffix=''):
        preview = cli('object', 'delete-preview', item['kind'], item['id'])
        assert not preview['blockers'], preview
        removed = cli('object', 'delete', item['kind'], item['id'],
                      '--confirmation', preview['confirmation'],
                      '--request-id', f'delete-{item["kind"]}{suffix}')
        assert removed['deleted'] is True
        cli('object', 'get', item['kind'], item['id'], fails=True)
        assert get(item, deleted=True) == removed
        listed = cli('object', 'list', item['kind'])
        assert item['id'] not in [row['id'] for row in listed['items']]
        return removed

    def restore(item, suffix=''):
        current = get(item, deleted=True)
        restored = cli('object', 'restore', item['kind'], item['id'],
                       '--revision', current['revision'],
                       '--request-id', f'restore-{item["kind"]}{suffix}')
        assert restored['deleted'] is False
        assert get(item) == restored
        return restored

    report = {'database': str(db_path), 'formal_database_used': False}
    try:
        items = {}
        items['project'] = create('project', {'key': 'QA', 'name': '隔离验收'})
        items['issue'] = create('issue', {'project': 'QA', 'title': '测试工作项'})
        items['requirement'] = create('requirement', {'project': 'QA', 'req_code': 'QA-R1',
            'req_name': '测试需求', 'req_desc': '保留的原文', 'workload_md': 0})
        req = items['requirement']
        items['scenario'] = create('scenario', {'issue_key': req['id'],
            'scenario_code': 'QA::1', 'title': '测试场景'})
        items['sprint'] = create('sprint', {'project': 'QA', 'name': '测试迭代'})
        items['release'] = create('release', {'project': 'QA', 'name': 'qa-v1',
            'issue_keys': [items['issue']['id']]})
        items['comment'] = create('comment', {'issue_key': req['id'], 'body': '测试评论'})
        changes = {'project': {'name': '已验证项目'}, 'issue': {'title': '已验证工作项'},
            'requirement': {'req_name': '已验证需求', 'req_desc': '仅修改覆盖层'},
            'scenario': {'title': '已验证场景'}, 'sprint': {'name': '已验证迭代'},
            'release': {'notes': '已验证版本'}, 'comment': {'body': '已验证评论'}}
        for kind, fields in changes.items():
            items[kind] = update(items[kind], fields)
        current_req = items['requirement']['data']
        assert current_req['raw'] == req['data']['raw']
        assert current_req['original'] == req['data']['original']
        assert current_req['current']['req_desc'] == '仅修改覆盖层'

        # A visible release blocks deletion of its linked issue. Archive it first.
        blocked = cli('object', 'delete-preview', 'issue', items['issue']['id'])
        assert blocked['blockers']
        archived_release = delete(items['release'])
        for kind in ('comment', 'scenario', 'sprint', 'issue', 'requirement'):
            restore(delete(items[kind]))
        restore(archived_release)

        # Parent restoration must not undo a child's separate deletion.
        archived_scene = delete(items['scenario'], '-separate')
        restore(delete(items['project']))
        assert get(archived_scene, deleted=True)['deleted'] is True
        restore(archived_scene, '-separate')
        expected = {kind: get(item) for kind, item in items.items()}
        server.shutdown()
        server.server_close()
        thread.join()
        server = make_server(db_path, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        for kind, item in items.items():
            assert get(item) == expected[kind], f'{kind} did not survive server reopen'
        report.update(passed=True, kinds=list(items),
            checks=['CLI seven-kind create/update/delete/restore/readback',
                    'creation and update idempotence', 'stale revision rejected',
                    'release dependency guard', 'child tombstone retained',
                    'requirement raw/original preserved', 'persistence after reopen'])
        (workspace / 'report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        print(f'Isolated artifacts retained: {workspace}', file=sys.stderr)


if __name__ == '__main__':
    main()
