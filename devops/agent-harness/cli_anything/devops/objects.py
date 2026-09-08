"""Finite object API. Every handler runs inside the caller's Store transaction."""
import json
from functools import partial

from .store import DomainError, date_field, integer, now, only, text
from .requirements import Requirements, ANALYSIS_FIELDS, SCENARIO_FIELDS, encoded
from .object_lifecycle import KINDS, Lifecycle, digest, identity


class ObjectService:
    def __init__(self, store):
        self.store = store
        self.requirements = Requirements(store)

    def handlers(self):
        return {'object.'+action:partial(self.dispatch,action) for action in
                ('list','get','create','update','delete.preview','delete','restore')}

    def dispatch(self, action, db, data, actor):
        allowed = {
            'list':('kind','project','include_deleted','limit','offset'),
            'get':('kind','id','include_deleted'),
            'create':('kind','fields','request_id'),
            'update':('kind','id','revision','fields','request_id'),
            'delete.preview':('kind','id'),
            'delete':('kind','id','confirmation','request_id'),
            'restore':('kind','id','revision','request_id'),
        }
        only(data,allowed[action])
        kind = data.get('kind')
        if not isinstance(kind,str) or kind not in KINDS: raise DomainError('不支持的对象类型')
        if 'include_deleted' in data and type(data['include_deleted']) is not bool:
            raise DomainError('include_deleted 必须是布尔值')
        if action not in ('list','create'): identity(kind,data.get('id'))
        if action in ('list','get','delete.preview'):
            return {'list':self.list,'get':self.get,'delete.preview':self.preview}[action](db,data,actor)
        request = text(data.get('request_id'),'request_id',True,200)
        fingerprint = digest({'action':'object.'+action, 'data':data})
        previous = db.execute('SELECT digest,result FROM object_requests WHERE actor=? AND request_id=?',(actor,request)).fetchone()
        if previous:
            if previous['digest'] != fingerprint: raise DomainError('request_id 内容冲突',409)
            return json.loads(previous['result'])
        if action in ('create','update') and (not isinstance(data.get('fields'),dict) or not data['fields']):
            raise DomainError('fields 必须是非空对象')
        result = {'create':self.create,'update':self.update,'delete':self.delete,'restore':self.restore}[action](db,data,actor)
        db.execute('INSERT INTO object_requests VALUES(?,?,?,?,?)',(actor,request,fingerprint,encoded(result),now()))
        return result

    def object(self, db, kind, ident, include_deleted=False):
        life = Lifecycle(db)
        row = life.raw(kind,ident)
        deleted = not life.visible(kind,ident)
        if deleted and not include_deleted: raise DomainError('对象已删除或祖先不可见',404)
        if kind == 'requirement':
            raw = json.loads(row['raw'])
            data = dict(issue_key=ident,source_id=row['source_id'],req_code=row['req_code'],raw=raw,
                        original=json.loads(row['original']) if row['original'] else None,
                        current={**raw,**json.loads(row['fields'])},version=row['version'])
        elif kind == 'scenario':
            data = {**self.requirements.scenario(row),'issue_key':row['issue_key']}
        else: data = self.store.decode(row)
        return dict(kind=kind,id=ident,revision=life.revision(kind,ident),deleted=deleted,data=data)

    def get(self, db, data, actor):
        return self.object(db,data['kind'],data['id'],data.get('include_deleted',False))

    def list(self, db, data, actor):
        limit = integer(data.get('limit',50),'limit',1,100)
        offset = integer(data.get('offset',0),'offset',0,1000000)
        if 'project' in data: text(data['project'],'项目',True,40)
        life = Lifecycle(db)
        ids = [ident for ident in life.ids(data['kind'])
               if ('project' not in data or life.project(data['kind'],ident)==data['project'])
               and (data.get('include_deleted',False) or life.visible(data['kind'],ident))]
        return dict(items=[self.object(db,data['kind'],ident,True) for ident in ids[offset:offset+limit]],
                    total=len(ids),limit=limit,offset=offset)

    def create(self, db, data, actor):
        kind, fields = data['kind'], data['fields']
        if kind in ('project','issue','sprint','release'):
            row = {'project':self.store.create_project,'issue':self.store.create_issue,
                   'sprint':self.store.create_sprint,'release':self.store.create_release}[kind](db,fields,actor)
            ident = str(row['key'] if kind in ('project','issue') else row['id'])
        elif kind == 'comment':
            only(fields,('issue_key','body'))
            row = self.store.comment(db,{'key':fields.get('issue_key'),'body':fields.get('body')},actor)
            ident = str(row['id'])
        elif kind == 'requirement':
            ident = self.create_requirement(db,fields,actor)
        else:
            ident = self.create_scenario(db,fields,actor)
        return self.object(db,kind,ident)

    def create_requirement(self, db, fields, actor):
        only(fields,('project','req_code',*ANALYSIS_FIELDS))
        project = self.store.row(db,'projects',fields.get('project'))['key']
        code = text(fields.get('req_code'),'需求编号',True,100)
        if code != fields['req_code']: raise DomainError('需求编号不可含首尾空格')
        validated = self.requirements.validate_analysis({k:v for k,v in fields.items() if k not in ('project','req_code')})
        name = text(validated.get('req_name'),'需求名称',True,240)
        description = text(validated.get('req_desc',''),'需求描述',limit=100000)
        # Project-scoped check preserves imported numbering without overwriting any identity.
        if db.execute('''SELECT 1 FROM requirement_links r JOIN issues i ON i.key=r.issue_key
                         WHERE i.project=? AND r.req_code=?''',(project,code)).fetchone():
            raise DomainError('需求编号已存在',409)
        issue = self.store.create_issue(db,dict(project=project,title=name,description=description,type='story'),actor)
        source = 'manual-'+issue['key']
        raw = {**dict(req_code=code,project_code=project,req_name=name,req_desc=description,
                      status='待评估',source_type='manual'),**validated}
        snapshot = dict(source_id=source,source_type='manual',requirements=[raw],scenarios=[],documents={})
        result = dict(source_id=source,projects=[project],requirements=1,scenarios=0,reused=False)
        db.execute('INSERT INTO requirement_imports VALUES(?,?,?,?,?)',(source,digest(snapshot),encoded(snapshot),encoded(result),now()))
        db.execute('INSERT INTO requirement_links(issue_key,source_id,req_code,raw,original) VALUES(?,?,?,?,?)',
                   (issue['key'],source,code,encoded(raw),encoded(raw)))
        self.store.log(db,project,issue['key'],'requirement.create',actor,{'req_code':code,'source_type':'manual'})
        return issue['key']

    def create_scenario(self, db, fields, actor):
        only(fields,('issue_key','scenario_code',*SCENARIO_FIELDS))
        key = fields.get('issue_key')
        link = self.requirements.link(db,key)
        code = text(fields.get('scenario_code'),'场景编号',True,140)
        if code != fields['scenario_code']: raise DomainError('场景编号不可含首尾空格')
        raw = dict(req_code=link['req_code'],scenario_code=code,source_type='manual',derived=1)
        for field in SCENARIO_FIELDS:
            if field in fields: raw[field] = text(fields[field],field,field=='title',20000)
        text(raw.get('title'),'场景名称',True,20000)
        if fields.get('status','待复核') != '待复核': raise DomainError('新场景必须从待复核开始')
        raw['status'] = '待复核'
        db.execute('INSERT INTO requirement_scenarios(issue_key,scenario_code,raw,status) VALUES(?,?,?,?)',
                   (key,code,encoded(raw),'待复核'))
        self.store.log(db,Lifecycle(db).project('requirement',key),key,'scenario.create',actor,
                       {'kind':'scenario','id':key+'::'+code})
        return key+'::'+code

    def check_revision(self, db, data):
        revision = text(data.get('revision'),'revision',True,100)
        if revision != Lifecycle(db).revision(data['kind'],data['id']):
            raise DomainError('对象已更新，revision 冲突，请重新读取',409)

    def update(self, db, data, actor):
        kind, ident, fields = data['kind'],data['id'],data['fields']
        life = Lifecycle(db)
        life.require_visible(kind,ident)
        self.check_revision(db,data)
        row = life.raw(kind,ident)
        if kind == 'issue':
            only(fields,('title','description','type','status','priority','assignee','points','labels','due_date','sprint_id'))
            self.store.update_issue(db,{'key':ident,**fields},actor)
        elif kind == 'requirement':
            self.requirements.update(db,{'key':ident,'version':row['version'],'fields':fields},actor)
        elif kind == 'scenario':
            self.requirements.update_scenario(db,{'key':row['issue_key'],'scenario_code':row['scenario_code'],
                'version':row['version'],'fields':fields},actor)
        elif kind == 'release':
            only(fields,('name','notes','status','issue_keys'))
            self.store.update_release(db,{'id':int(ident),**fields},actor)
        else:
            allowed = {'project':('name','description'), 'comment':('body',),
                       'sprint':('name','goal','start_date','end_date','status')}[kind]
            only(fields,allowed)
            values = dict(fields)
            for key,value in fields.items():
                if key in ('start_date','end_date'): values[key] = date_field(value)
                elif key != 'status': values[key] = text(value,key,key in ('name','body'),120 if key=='name' else 10000)
            if kind == 'sprint':
                merged = {**row,**values}
                if merged['start_date'] and merged['end_date'] and merged['end_date'] < merged['start_date']:
                    raise DomainError('结束日期不能早于开始日期')
                status = values.pop('status',row['status'])
                if status not in ('planned','active','completed'): raise DomainError('迭代状态无效')
                if status != row['status']:
                    if status == 'active': self.store.start_sprint(db,{'id':int(ident)},actor)
                    elif status == 'completed': self.store.complete_sprint(db,{'id':int(ident)},actor)
                    else: raise DomainError('迭代状态不可回退')
            changes = {k:{'before':row[k],'after':v} for k,v in values.items() if row[k]!=v}
            if changes:
                table, column = {'project':('projects','key'),'sprint':('sprints','id'),'comment':('comments','id')}[kind]
                db.execute(f'UPDATE {table} SET '+','.join(k+'=?' for k in values)+f' WHERE {column}=?',(*values.values(),ident))
                self.store.log(db,life.project(kind,ident),life.target(kind,ident),kind+'.update',actor,
                               {'kind':kind,'id':ident,'fields':changes})
        return self.object(db,kind,ident)

    def preview(self, db, data, actor):
        kind, ident = data['kind'], data['id']
        life = Lifecycle(db)
        life.require_visible(kind,ident)
        closure = life.closure(kind,ident)
        affected = [dict(kind=k,id=i,deleted=not life.visible(k,i),revision=life.revision(k,i)) for k,i in closure]
        blockers = []
        if kind == 'sprint':
            if life.raw(kind,ident)['status']=='active': blockers.append({'reason':'活动迭代不能删除','kind':kind,'id':ident})
            blockers.extend({'reason':'迭代仍被工作项引用','kind':'issue','id':i}
                            for i in life.ids('issue') if life.visible('issue',i) and life.raw('issue',i)['sprint_id']==int(ident))
        if kind in ('issue','requirement'):
            blockers.extend({'reason':'工作项仍被版本引用','kind':'release','id':i}
                            for i in life.ids('release') if life.visible('release',i) and ident in json.loads(life.raw('release',i)['issue_keys']))
        return dict(kind=kind,id=ident,confirmation=digest([kind,ident,affected,blockers]),affected=affected,blockers=blockers)

    def set_deleted(self, db, kind, ident, deleted, actor):
        life = Lifecycle(db)
        db.execute('''INSERT INTO object_tombstones VALUES(?,?,?,1,?,?) ON CONFLICT(kind,object_id)
                      DO UPDATE SET deleted=excluded.deleted,generation=generation+1,actor=excluded.actor,updated_at=excluded.updated_at''',
                   (*life.shared(kind,ident),int(deleted),actor,now()))
        self.store.log(db,life.project(kind,ident),life.target(kind,ident),'object.delete' if deleted else 'object.restore',
                       actor,{'kind':kind,'id':ident,'deleted':deleted})

    def delete(self, db, data, actor):
        confirmation = text(data.get('confirmation'),'confirmation',True,100)
        preview = self.preview(db,data,actor)
        if confirmation != preview['confirmation']: raise DomainError('删除影响已变化，confirmation 冲突，请重新预览',409)
        if preview['blockers']: raise DomainError('删除被阻止：'+ '；'.join(b['reason'] for b in preview['blockers']),409)
        self.set_deleted(db,data['kind'],data['id'],True,actor)
        return self.object(db,data['kind'],data['id'],True)

    def restore(self, db, data, actor):
        kind, ident = data['kind'],data['id']
        life = Lifecycle(db)
        self.check_revision(db,data)
        state = life.state(kind,ident)
        if not state or not state['deleted']: raise DomainError('对象没有独立删除状态；请先恢复被删除的祖先',409)
        restoring = life.shared(kind,ident)
        if not life.visible(kind,ident,restoring): raise DomainError('父对象不可见，不能恢复',409)
        # Check the entire newly visible closure before changing any tombstone.
        for child, key in life.closure(kind,ident):
            if not life.visible(child,key,restoring): continue
            row = life.raw(child,key)
            if child == 'issue' and row['sprint_id'] is not None:
                sid = str(row['sprint_id'])
                if not life.visible('sprint',sid,restoring) or life.raw('sprint',sid)['project']!=row['project']:
                    raise DomainError('恢复冲突：关联迭代不可用',409)
            if child == 'release':
                for issue in json.loads(row['issue_keys']):
                    if not life.visible('issue',issue,restoring) or life.raw('issue',issue)['project']!=row['project']:
                        raise DomainError('恢复冲突：版本工作项不可用',409)
        self.set_deleted(db,kind,ident,False,actor)
        return self.object(db,kind,ident)
