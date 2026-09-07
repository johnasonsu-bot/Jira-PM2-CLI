#!/usr/bin/env python3
"""Verify a real API import byte-for-value, with existing-project preservation.

Without --import this is read-only. With --staging-db it starts a temporary local
server on an ephemeral port, isolated from the user's running application.
"""
import argparse
import hashlib
import json
import threading
from pathlib import Path

from cli_anything.devops.backend import Backend
from cli_anything.devops.server import make_server


def verify(backend, bundle, do_import=False):
    existing = backend.call('project.list',{})
    incoming = {p['project_code'] for p in bundle['projects']}
    protected = {p['key']:backend.request('/api/state?project='+p['key'])
                 for p in existing if p['key'] not in incoming}
    result = backend.call('requirement.import',{'bundle':bundle}) if do_import else None
    exported = backend.call('requirement.export',{'source_id':bundle['source_id']})
    assert exported['snapshot']==bundle, 'Source snapshot changed'
    expected = {r['req_code']:r for r in bundle['requirements']}
    imported = {r['req_code']:r for r in exported['requirements']}
    assert len(imported)==len(expected)==len(exported['requirements'])
    originals = {r['req_code']:r for r in bundle['original_requirements']}
    for code,row in expected.items():
        assert imported[code]['raw']==row, 'Requirement lost source fields: '+code
        assert imported[code]['original']==originals.get(code), 'Initial JSON changed: '+code
    scenarios = {r['scenario_code']:r for r in bundle['scenarios']}
    actual_scenarios = {r['scenario_code']:r for r in exported['scenarios']}
    assert len(actual_scenarios)==len(scenarios)==len(exported['scenarios'])
    for code,row in scenarios.items():
        target = actual_scenarios[code]
        assert target['raw']==row, 'Scenario lost source fields: '+code
        assert target['key']==imported[row['req_code']]['key'], 'Scenario linked to wrong requirement'
    counts = {}
    for project in sorted(incoming):
        state = backend.request('/api/state?project='+project)
        project_rows = {r['req_code']:r for r in bundle['requirements'] if r['project_code']==project}
        issues = {i['requirement']['req_code']:i for i in state['issues'] if i.get('requirement')}
        assert len(issues)==len(project_rows)
        for code,raw in project_rows.items():
            assert issues[code]['key']==imported[code]['key']
            assert issues[code]['description']==(raw.get('req_desc') or '').strip()
        report = backend.call('requirement.report',{'project':project})
        assert report['total']==len(project_rows)
        counts[project] = {'requirements':len(project_rows),'scenarios':report['scenario_count'],
                           'confirmed_scenarios':report['confirmed_scenario_count']}
    unchanged = []
    for key,before in protected.items():
        after = backend.request('/api/state?project='+key)
        # The global selector necessarily gains imported projects; project data must not change.
        assert {k:v for k,v in before.items() if k!='projects'} == {k:v for k,v in after.items() if k!='projects'}, key+' data changed'
        unchanged.append(key)
    return {'success':True,'source_id':bundle['source_id'],'snapshot_digest':exported['digest'],
            'import_result':result,'counts':counts,'requirements_verified':len(imported),
            'scenarios_verified':len(actual_scenarios),'original_json_verified':len(originals),
            'documents_verified':len(bundle['documents']),'existing_projects_unchanged':unchanged,
            'snapshot_json_sha256':hashlib.sha256(json.dumps(bundle,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:8766')
    parser.add_argument('--import',dest='do_import',action='store_true')
    parser.add_argument('--staging-db',type=Path)
    parser.add_argument('--result',required=True,type=Path)
    args = parser.parse_args()
    with args.bundle.open(encoding='utf-8') as stream: bundle = json.load(stream)
    server = thread = None
    if args.staging_db:
        if args.staging_db.exists(): parser.error('试导入数据库已存在，拒绝覆盖')
        server = make_server(args.staging_db,0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        args.url = f'http://127.0.0.1:{server.server_port}'
    try:
        result = verify(Backend(args.url,actor='Codex/RequirementsImport'),bundle,args.do_import)
        with args.result.open('x',encoding='utf-8') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False))
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__=='__main__':
    main()
