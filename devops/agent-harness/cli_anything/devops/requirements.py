"""Lossless source snapshots and versioned requirement analysis, in Forge's DB.

Imported text is evidence, never executable instructions. Snapshots are immutable;
analysis and scenario revisions live in overlays and never rewrite that evidence.
"""
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from .store import DomainError, integer, now, only, text

REQUIRED = {
    'req_code':'需求编号', 'req_name':'需求名称', 'req_desc':'需求描述',
    'project_code':'所属项目', 'system_name':'归属系统', 'module_path':'所属模块',
    'req_type':'需求类型', 'priority':'优先级', 'acceptance_criteria':'验收标准',
    'deliverable':'交付物', 'workload_md':'工作量（人天）',
}
ANALYSIS_FIELDS = ('priority', 'acceptance_criteria', 'deliverable', 'workload_md',
                   'related_systems', 'biz_owner', 'owner_side', 'status', 'remark',
                   'req_name', 'req_desc', 'system_name', 'module_path', 'req_type')
SCENARIO_FIELDS = ('title','given_text','when_text','then_text','scenario_type','status','remark')
REVIEW_STATUSES = ('待评估', '已确认', '开发中', '已验收', '已否决')
SCENARIO_STATUSES = ('待复核', '已确认', '已废弃')


def encoded(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError):
        raise DomainError('需要有效 JSON，不能包含 NaN 或 Infinity') from None


def missing_fields(row):
    def filled(key):
        value = row.get(key)
        if key == 'priority': return value in ('P0','P1','P2')
        if key == 'workload_md': return value is not None and value != ''
        if key in ('req_name','req_desc'):
            return isinstance(value, str) and len(value) >= (4 if key=='req_name' else 25)
        return value is not None and str(value).strip() != ''
    return [key for key in REQUIRED if not filled(key)]


def source_context(raw, documents):
    filename = raw.get('source_file') or raw.get('src_file') or ''
    recorded = raw.get('source_line') or raw.get('src_line')
    document = documents.get(filename, '')
    description = re.sub(r'\s+', '', raw.get('req_desc') or '')
    normalized = re.sub(r'\s+', '', document)
    start = normalized.find(description) if len(description)>=16 else -1
    unique = start>=0 and normalized.find(description,start+1)<0
    # A prefix match or extractor row number cannot establish ownership of nearby
    # document text. Only a unique, full-body match may supply an excerpt, and even
    # then adjacent text on that same line can belong to another hidden requirement.
    resolved, excerpt = None, ''
    if unique:
        first = 0
        # Map just the matched bounds back to the source, without allocating an
        # index per character for a potentially large imported document.
        for index,character in enumerate(re.finditer(r'\S',document)):
            if index==start: first=character.start()
            if index==start+len(description)-1:
                owned = document[first:character.end()]
                resolved = document.count('\n',0,first)+1
                excerpt = '\n'.join(f'{resolved+n}: {line}' for n,line in enumerate(owned.splitlines()))
                break
    note = (f'按需求完整正文唯一匹配到文档第 {resolved} 行；原来源记录行号仍保留为 {recorded}。'
            if resolved else '未唯一定位完整需求正文；不展示无法确认归属的文档摘录。完整文档可通过档案导出读取。')
    return {'file':filename,'line':recorded,'resolved_line':resolved,
            'match':'body' if resolved else 'unverified','excerpt':note+('\n'+excerpt if excerpt else '')}


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS requirement_imports (
            source_id TEXT PRIMARY KEY, digest TEXT NOT NULL, snapshot TEXT NOT NULL,
            result TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requirement_links (
            issue_key TEXT PRIMARY KEY REFERENCES issues(key),
            source_id TEXT NOT NULL REFERENCES requirement_imports(source_id),
            req_code TEXT NOT NULL, raw TEXT NOT NULL, original TEXT,
            fields TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
            UNIQUE(source_id,req_code));
        CREATE TABLE IF NOT EXISTS requirement_scenarios (
            issue_key TEXT NOT NULL REFERENCES requirement_links(issue_key),
            scenario_code TEXT NOT NULL, raw TEXT NOT NULL,
            fields TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL, PRIMARY KEY(issue_key,scenario_code));
    ''')


class Requirements:
    def __init__(self, store):
        self.store = store

    def handlers(self):
        return {'requirement.import':self.import_bundle, 'requirement.get':self.get,
                'requirement.update':self.update, 'requirement.scenario.update':self.update_scenario,
                'requirement.report':self.report, 'requirement.export':self.export,
                'requirement.list':self.list}

    def link(self, db, key):
        text(key, '工作项标识', True, 40)
        self.store.row(db,'issues',key)
        row = db.execute('SELECT * FROM requirement_links WHERE issue_key=?', (key,)).fetchone()
        if row is None: raise DomainError('该工作项没有关联需求', 404)
        return dict(row)

    def validate_bundle(self, bundle):
        if not isinstance(bundle, dict): raise DomainError('bundle 必须是对象')
        source = text(bundle.get('source_id'), '来源标识', True, 100)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', source): raise DomainError('来源标识格式无效')
        for key, maximum in [('projects',100),('requirements',10000),('scenarios',100000),
                             ('original_requirements',10000),('field_rules',1000),('import_batches',10000)]:
            rows = bundle.get(key, [])
            if not isinstance(rows, list) or len(rows)>maximum or any(not isinstance(r,dict) for r in rows):
                raise DomainError(f'{key} 必须是对象数组且不超过 {maximum} 项')
        if not bundle.get('projects') or not bundle.get('requirements'):
            raise DomainError('导入包必须包含项目和需求')
        docs = bundle.get('documents', {})
        if not isinstance(docs,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in docs.items()):
            raise DomainError('documents 必须是文档标识到完整正文的映射')
        projects, codes, scenario_codes = set(), set(), set()
        for row in bundle['projects']:
            code = row.get('project_code')
            if not isinstance(code,str) or not re.fullmatch(r'[A-Z][A-Z0-9]{1,9}', code) or code in projects:
                raise DomainError('项目编号无效或重复')
            text(row.get('project_name'), '项目名称', True, 120)
            projects.add(code)
        for row in bundle['requirements']:
            code = text(row.get('req_code'), '原需求编号', True, 100)
            if code != row['req_code'] or code in codes: raise DomainError('原需求编号重复或含首尾空格')
            if not isinstance(row.get('project_code'),str) or row['project_code'] not in projects:
                raise DomainError('需求所属项目不在导入包内')
            text(row.get('req_name'), '需求名称', True, 240)
            text(row.get('req_desc') or '', '需求正文', limit=100000)
            for field in ('system_name','system_abbr','chapter','module_path','req_type','priority','status',
                          'source_file','src_file','acceptance_criteria','deliverable','biz_owner','owner_side'):
                if row.get(field) is not None and not isinstance(row[field],str):
                    raise DomainError(f'原字段 {field} 应为文本或 null')
            for field in ('source_line','src_line'):
                if row.get(field) is not None: integer(row[field],field,0,1000000)
            codes.add(code)
        original_codes = set()
        for row in bundle.get('original_requirements', []):
            code = row.get('req_code')
            if not isinstance(code,str) or code in original_codes:
                raise DomainError('初始需求编号无效或重复')
            original_codes.add(code)
        for row in bundle.get('scenarios', []):
            code = text(row.get('scenario_code'), '场景编号', True, 140)
            if code != row['scenario_code'] or code in scenario_codes:
                raise DomainError('场景编号重复或含首尾空格')
            if not isinstance(row.get('req_code'),str) or row['req_code'] not in codes:
                raise DomainError('存在无所属需求的场景')
            scenario_codes.add(code)
        return source

    def import_bundle(self, db, data, actor):
        only(data, ('bundle',))
        bundle = data.get('bundle')
        source = self.validate_bundle(bundle)
        snapshot = encoded(bundle)
        digest = hashlib.sha256(snapshot.encode()).hexdigest()
        previous = db.execute('SELECT digest,result FROM requirement_imports WHERE source_id=?', (source,)).fetchone()
        if previous:
            if previous['digest'] != digest:
                raise DomainError('该来源已有不同快照；为保护原始数据，禁止覆盖，请使用新来源标识和未占用项目', 409)
            return {**json.loads(previous['result']), 'reused':True}
        project_keys = [p['project_code'] for p in bundle['projects']]
        for key in project_keys:
            if db.execute('SELECT 1 FROM projects WHERE key=?', (key,)).fetchone():
                raise DomainError(f'项目 {key} 已存在，禁止与原项目混合覆盖', 409)
        result = dict(source_id=source, digest=digest, projects=project_keys,
                      requirements=len(bundle['requirements']), scenarios=len(bundle.get('scenarios',[])), reused=False)
        db.execute('INSERT INTO requirement_imports VALUES(?,?,?,?,?)', (source,digest,snapshot,encoded(result),now()))
        for row in bundle['projects']:
            self.store.create_project(db, {'key':row['project_code'],'name':row['project_name'],
                'description':f'原始需求分析导入 · {source}。需求评估状态与研发状态分开记录；人天不等于 SP。'}, actor)
        originals = {r['req_code']:r for r in bundle.get('original_requirements', [])}
        links = {}
        for row in bundle['requirements']:
            item = self.store.create_issue(db, {'project':row['project_code'],'title':row['req_name'],
                'description':row.get('req_desc') or '', 'type':'story','status':'backlog',
                'priority':'medium',
                'labels':['需求导入']}, actor)
            key = item['key']
            original = originals.get(row['req_code'])
            db.execute('INSERT INTO requirement_links(issue_key,source_id,req_code,raw,original) VALUES(?,?,?,?,?)',
                (key,source,row['req_code'],encoded(row),encoded(original) if original is not None else None))
            links[row['req_code']] = key
        for row in bundle.get('scenarios', []):
            db.execute('INSERT INTO requirement_scenarios(issue_key,scenario_code,raw,status) VALUES(?,?,?,?)',
                (links[row['req_code']],row['scenario_code'],encoded(row),str(row.get('status') or '待复核')))
        for project in project_keys:
            self.store.log(db, project, project, 'requirement.import', actor,
                           {'source_id':source,'digest':digest,'requirements':sum(r['project_code']==project for r in bundle['requirements'])})
        return result

    @staticmethod
    def scenario(row):
        raw, fields = json.loads(row['raw']), json.loads(row['fields'])
        return dict(scenario_code=row['scenario_code'],raw=raw,current={**raw,**fields},version=row['version'])

    def summaries(self, db, project=None):
        query = 'SELECT r.* FROM requirement_links r JOIN issues i ON i.key=r.issue_key'
        params = ()
        if project is not None:
            query += ' WHERE i.project=?'
            params = (project,)
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        counts = {}
        for row in db.execute('SELECT issue_key,scenario_code,status FROM requirement_scenarios'):
            if not life.visible('scenario',row['issue_key']+'::'+row['scenario_code']): continue
            count = counts.setdefault(row['issue_key'],{'count':0,'confirmed':0})
            count['count'] += row['status'] != '已废弃'
            count['confirmed'] += row['status'] == '已确认'
        result = {}
        for link in db.execute(query, params):
            if not life.visible('requirement',link['issue_key']): continue
            row = {**json.loads(link['raw']), **json.loads(link['fields'])}
            missing = missing_fields(row)
            count = counts.get(link['issue_key'], {'count':0,'confirmed':0})
            result[link['issue_key']] = {
                **{k:row.get(k) for k in ('req_code','system_name','chapter','module_path','req_type',
                                        'priority','status','workload_md','is_common')},
                'missing':missing,'filled':len(REQUIRED)-len(missing),'need':len(REQUIRED),
                'scenario_count':count['count'],'confirmed_scenario_count':count['confirmed']}
        return result

    def get(self, db, data, actor):
        only(data, ('key',))
        link = self.link(db, data.get('key'))
        raw = json.loads(link['raw'])
        current = {**raw, **json.loads(link['fields'])}
        snapshot = json.loads(db.execute('SELECT snapshot FROM requirement_imports WHERE source_id=?', (link['source_id'],)).fetchone()[0])
        summary = self.summaries(db, raw['project_code'])[link['issue_key']]
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        return {**summary,'source_id':link['source_id'],'raw':raw,'current':current,
                'original':json.loads(link['original']) if link['original'] else None,
                'version':link['version'], 'source':source_context(raw,snapshot.get('documents', {})),
                'scenarios':[self.scenario(r) for r in db.execute(
                    'SELECT * FROM requirement_scenarios WHERE issue_key=? ORDER BY scenario_code', (link['issue_key'],))
                    if life.visible('scenario',link['issue_key']+'::'+r['scenario_code'])]}

    def update(self, db, data, actor):
        only(data, ('key','version','fields'))
        link = self.link(db, data.get('key'))
        fields = data.get('fields')
        if not isinstance(fields,dict) or not fields: raise DomainError('请提供要补充的需求字段')
        only(fields, ANALYSIS_FIELDS)
        integer(data.get('version'), '版本', 1, 2**31)
        if data['version'] != link['version']: raise DomainError('需求分析编辑冲突，请刷新后重试',409)
        fields = self.validate_analysis(fields)
        old = json.loads(link['fields'])
        current = {**json.loads(link['raw']),**old}
        changes = {k:{'before':current.get(k),'after':v} for k,v in fields.items() if current.get(k)!=v}
        if changes:
            db.execute('UPDATE requirement_links SET fields=?,version=version+1 WHERE issue_key=?',
                       (encoded({**old,**fields}),link['issue_key']))
            self.store.log(db,current['project_code'],link['issue_key'],'requirement.update',actor,changes)
        synced = {target:fields[source] for source,target in (('req_name','title'),('req_desc','description')) if source in fields}
        if synced: self.store.update_issue(db,{'key':link['issue_key'],**synced},actor)
        return self.get(db,{'key':link['issue_key']},actor)

    @staticmethod
    def validate_analysis(fields):
        only(fields,ANALYSIS_FIELDS)
        fields = dict(fields)
        for key, value in fields.items():
            if key=='workload_md':
                if value is not None:
                    try:
                        number = Decimal(str(value))
                        if isinstance(value,bool) or not number.is_finite() or not 0 <= number <= 999999.99:
                            raise InvalidOperation
                    except InvalidOperation: raise DomainError('工作量应为非负人天数或 null') from None
            elif key=='priority':
                if value not in (None,'P0','P1','P2'): raise DomainError('需求优先级为 P0/P1/P2 或 null')
            elif key=='status':
                if value not in REVIEW_STATUSES: raise DomainError('需求评估状态无效')
            elif key in ('req_name','req_desc'):
                fields[key] = text(value,key,key=='req_name',240 if key=='req_name' else 100000)
            elif value is not None:
                text(value, key, limit=20000)
        return fields

    def update_scenario(self, db, data, actor):
        only(data, ('key','scenario_code','version','fields'))
        link = self.link(db,data.get('key'))
        code = text(data.get('scenario_code'),'场景编号',True,140)
        from .object_lifecycle import Lifecycle
        Lifecycle(db).require_visible('scenario',link['issue_key']+'::'+code)
        row = db.execute('SELECT * FROM requirement_scenarios WHERE issue_key=? AND scenario_code=?', (link['issue_key'],code)).fetchone()
        if row is None: raise DomainError('该需求中没有此场景',404)
        integer(data.get('version'),'版本',1,2**31)
        if data['version']!=row['version']: raise DomainError('场景编辑冲突，请刷新后重试',409)
        fields = data.get('fields')
        if not isinstance(fields,dict) or not fields: raise DomainError('请提供场景更新字段')
        only(fields,SCENARIO_FIELDS)
        fields = dict(fields)
        for key,value in fields.items():
            text(value,key,required=key not in ('remark',),limit=20000)
            if key=='status' and value not in SCENARIO_STATUSES: raise DomainError('场景复核状态无效')
        current = self.scenario(row)['current']
        revised = any(k in fields and fields[k]!=current.get(k) for k in SCENARIO_FIELDS if k not in ('status','remark'))
        if revised:
            fields.update(status='待复核',derived=1)
        elif fields.get('status')=='已确认':
            if any(not str(current.get(k) or '').strip() for k in ('given_text','when_text','then_text')):
                raise DomainError('确认前需要完整 Given / When / Then')
            fields['derived']=0
        elif fields.get('status')=='待复核': fields['derived']=1
        changes = {k:{'before':current.get(k),'after':v} for k,v in fields.items() if current.get(k)!=v}
        if changes:
            db.execute('UPDATE requirement_scenarios SET fields=?,version=version+1,status=? WHERE issue_key=? AND scenario_code=?',
                (encoded({**json.loads(row['fields']),**fields}),fields.get('status',row['status']),link['issue_key'],code))
            self.store.log(db,json.loads(link['raw'])['project_code'],link['issue_key'],'requirement.scenario.update',actor,
                           {'scenario_code':code,'fields':changes})
        return self.scenario(db.execute('SELECT * FROM requirement_scenarios WHERE issue_key=? AND scenario_code=?', (link['issue_key'],code)).fetchone())

    def list(self, db, data, actor):
        only(data, ('project','q','system','chapter','req_type','missing','limit','offset'))
        self.store.row(db,'projects',data.get('project'))
        items = [i for i in self.store.issues(db,{'project':data['project']},actor) if 'requirement' in i]
        q = text(data.get('q',''),'搜索',limit=240).casefold()
        for key,field in [('system','system_name'),('chapter','chapter'),('req_type','req_type')]:
            if data.get(key): items=[i for i in items if i['requirement'][field]==data[key]]
        if data.get('missing'): items=[i for i in items if data['missing'] in i['requirement']['missing']]
        if q:
            items=[i for i in items if q in ' '.join(str(v or '') for v in (
                i['key'],i['title'],i['description'],*(i['requirement'].get(k) for k in
                ('req_code','system_name','chapter','module_path','req_type')))).casefold()]
        limit, offset = data.get('limit',50), data.get('offset',0)
        integer(limit,'每页数量',1,100)
        integer(offset,'偏移',0,1000000)
        return {'total':len(items),'items':items[offset:offset+limit],'limit':limit,'offset':offset}

    def report(self, db, data, actor):
        only(data, ('project',))
        self.store.row(db,'projects',data.get('project'))
        rows = list(self.summaries(db,data['project']).values())
        total = len(rows)
        fields = []
        for key,label in REQUIRED.items():
            filled = sum(key not in r['missing'] for r in rows)
            fields.append(dict(key=key,label=label,filled=filled,total=total,rate=round(filled/total*100,1) if total else None))
        def distribution(key):
            return [{'name':name or '未填写','count':count} for name,count in Counter(r[key] for r in rows).most_common()]
        return dict(total=total,scenario_count=sum(r['scenario_count'] for r in rows),
            confirmed_scenario_count=sum(r['confirmed_scenario_count'] for r in rows),
            common_count=sum(bool(r['is_common']) for r in rows),fields=fields,
            by_system=distribution('system_name'),by_type=distribution('req_type'),
            methodology='11 个源文档必备字段；GWT 是过程产物，不计入源文档完备率。人天不等于 SP；需求评估状态独立于工作项交付状态。')

    def export(self, db, data, actor):
        only(data, ('source_id',))
        source = text(data.get('source_id'),'来源标识',True,100)
        row = db.execute('SELECT * FROM requirement_imports WHERE source_id=?',(source,)).fetchone()
        if row is None: raise DomainError('导入来源不存在',404)
        links = db.execute('SELECT * FROM requirement_links WHERE source_id=? ORDER BY issue_key',(source,)).fetchall()
        scenarios = db.execute('''SELECT s.* FROM requirement_scenarios s JOIN requirement_links r
            ON r.issue_key=s.issue_key WHERE r.source_id=? ORDER BY s.issue_key,s.scenario_code''',(source,)).fetchall()
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        return {'snapshot':json.loads(row['snapshot']),'digest':row['digest'],
                'requirements':[{'key':r['issue_key'],'req_code':r['req_code'],'raw':json.loads(r['raw']),
                    'original':json.loads(r['original']) if r['original'] else None,
                    'fields':json.loads(r['fields']),'version':r['version'],
                    'deleted':not life.visible('requirement',r['issue_key']),
                    'tombstone':life.state('requirement',r['issue_key'])} for r in links],
                'scenarios':[{'key':r['issue_key'],'scenario_code':r['scenario_code'],'raw':json.loads(r['raw']),
                    'fields':json.loads(r['fields']),'version':r['version'],
                    'deleted':not life.visible('scenario',r['issue_key']+'::'+r['scenario_code']),
                    'tombstone':life.state('scenario',r['issue_key']+'::'+r['scenario_code'])} for r in scenarios],
                'tombstones':[dict(r) for r in db.execute('SELECT * FROM object_tombstones')
                    if (r['kind']=='project' and r['object_id'] in {life.project('requirement',link['issue_key']) for link in links})
                    or (r['kind']=='issue' and r['object_id'] in {link['issue_key'] for link in links})
                    or (r['kind']=='scenario' and r['object_id'] in {s['issue_key']+'::'+s['scenario_code'] for s in scenarios})]}
