"""Transactional domain rules shared by every HTTP and CLI operation."""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, date
from pathlib import Path

STATUSES = ('backlog', 'todo', 'in_progress', 'review', 'done')
TYPES = ('story', 'task', 'bug', 'epic')
PRIORITIES = ('critical', 'high', 'medium', 'low')

class DomainError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def text(value, name, required=False, limit=10000):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise DomainError(f'{name} 格式不正确（长度上限 {limit}）')
    return value.strip()

def integer(value, name, minimum=0, maximum=10000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DomainError(f'{name} 必须是 {minimum}–{maximum} 的整数')
    return value

def only(data, allowed):
    extra = set(data) - set(allowed)
    if extra:
        raise DomainError('不支持的字段：' + ', '.join(sorted(extra)))

def date_field(value):
    value = text(value, '日期', limit=10)
    if value:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise DomainError('日期必须是 YYYY-MM-DD')
    return value

class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    key TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                    next_number INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sprints (
                    id INTEGER PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(key),
                    name TEXT NOT NULL, goal TEXT NOT NULL, start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_sprint ON sprints(project) WHERE status='active';
                CREATE TABLE IF NOT EXISTS issues (
                    key TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(key),
                    title TEXT NOT NULL, description TEXT NOT NULL, type TEXT NOT NULL,
                    status TEXT NOT NULL, priority TEXT NOT NULL, assignee TEXT NOT NULL,
                    points INTEGER NOT NULL, labels TEXT NOT NULL, due_date TEXT NOT NULL,
                    sprint_id INTEGER REFERENCES sprints(id), version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS issue_project ON issues(project);
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY, issue_key TEXT NOT NULL REFERENCES issues(key),
                    body TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(key),
                    target TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                    changes TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(key),
                    name TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL,
                    issue_keys TEXT NOT NULL, created_at TEXT NOT NULL, released_at TEXT,
                    UNIQUE(project, name));
            ''')
            from .requirements import initialize
            initialize(db)
            from .object_lifecycle import initialize as initialize_objects
            initialize_objects(db)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def call(self, action, data=None, actor='local'):
        from .requirements import Requirements
        handlers = {
            'project.list': self.projects, 'project.create': self.create_project,
            'issue.list': self.issues, 'issue.create': self.create_issue,
            'issue.get': self.get_issue, 'issue.update': self.update_issue,
            'issue.comment': self.comment, 'sprint.list': self.sprints,
            'sprint.create': self.create_sprint, 'sprint.start': self.start_sprint,
            'sprint.complete': self.complete_sprint, 'release.list': self.releases,
            'release.create': self.create_release, 'release.update': self.update_release,
            'activity.list': self.activity, 'report.summary': self.summary,
            'report.analytics': self.analytics,
        }
        handlers.update(Requirements(self).handlers())
        from .objects import ObjectService
        handlers.update(ObjectService(self).handlers())
        if not isinstance(action, str) or action not in handlers:
            raise DomainError('未知操作')
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise DomainError('data 必须是对象')
        actor = text(actor, '操作者', required=True, limit=100)
        try:
            with closing(self.connect()) as db, db:
                db.execute('BEGIN IMMEDIATE')
                return handlers[action](db, data, actor)
        except sqlite3.IntegrityError:
            raise DomainError('记录冲突：项目标识、版本名称或活动迭代已存在', 409)

    def row(self, db, table, value, field='key'):
        # table/field are internal constants, never client-controlled SQL.
        if field == 'id':
            integer(value, 'ID', 1, 2**31)
        else:
            text(value, '标识', True, 40)
        row = db.execute(f'SELECT * FROM {table} WHERE {field}=?', (value,)).fetchone()
        if row is None:
            raise DomainError(f'记录不存在：{value}', 404)
        from .object_lifecycle import Lifecycle
        kind = {'projects':'project','issues':'issue','sprints':'sprint','releases':'release','comments':'comment'}[table]
        Lifecycle(db).require_visible(kind,str(value))
        return self.decode(row)

    @staticmethod
    def decode(row):
        result = dict(row)
        for key in ('labels', 'changes', 'issue_keys'):
            if key in result:
                result[key] = json.loads(result[key])
        return result

    def log(self, db, project, target, action, actor, changes):
        db.execute('INSERT INTO activity(project,target,action,actor,changes,created_at) VALUES(?,?,?,?,?,?)',
                   (project, target, action, actor, json.dumps(changes, ensure_ascii=False), now()))

    def projects(self, db, d, actor):
        only(d, [])
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        return [dict(r) for r in db.execute('SELECT key,name,description,created_at FROM projects ORDER BY created_at,key')
                if life.visible('project',r['key'])]

    def create_project(self, db, d, actor):
        only(d, ('key', 'name', 'description'))
        key = text(d.get('key'), '项目标识', True, 10).upper()
        if not re.fullmatch(r'[A-Z][A-Z0-9]{1,9}', key):
            raise DomainError('项目标识为 2–10 位大写字母或数字，以字母开头')
        name = text(d.get('name'), '项目名称', True, 120)
        db.execute('INSERT INTO projects(key,name,description,created_at) VALUES(?,?,?,?)',
                   (key, name, text(d.get('description', ''), '描述'), now()))
        self.log(db, key, key, 'project.create', actor, {'name': name})
        return self.row(db, 'projects', key)

    def validate_fields(self, db, d, project):
        fields = dict(d)
        for name, values in [('status', STATUSES), ('type', TYPES), ('priority', PRIORITIES)]:
            if name in fields and fields[name] not in values:
                raise DomainError(f'{name} 必须是：' + ', '.join(values))
        for name, limit in [('title', 240), ('description', 100000), ('assignee', 100)]:
            if name in fields:
                fields[name] = text(fields[name], name, name == 'title', limit)
        if 'points' in fields:
            integer(fields['points'], '故事点', 0, 100)
        if 'labels' in fields:
            labels = fields['labels']
            if not isinstance(labels, list) or len(labels) > 20:
                raise DomainError('标签应是最多 20 项的数组')
            fields['labels'] = list(dict.fromkeys(text(v, '标签', True, 50) for v in labels))
        if 'due_date' in fields:
            fields['due_date'] = date_field(fields['due_date'])
        if fields.get('sprint_id') is not None:
            integer(fields['sprint_id'], '迭代 ID', 1, 2**31)
            sprint = self.row(db, 'sprints', fields['sprint_id'], 'id')
            if sprint['project'] != project or sprint['status'] == 'completed':
                raise DomainError('迭代必须属于同一项目，且未完成')
        return fields

    def create_issue(self, db, d, actor):
        only(d, ('project', 'title', 'description', 'type', 'status', 'priority', 'assignee', 'points', 'labels', 'due_date', 'sprint_id'))
        project = self.row(db, 'projects', d.get('project'))
        f = self.validate_fields(db, {
            'title': d.get('title'), 'description': '', 'type': 'task', 'status': 'backlog',
            'priority': 'medium', 'assignee': '', 'points': 0, 'labels': [], 'due_date': '',
            'sprint_id': None, **{k: v for k, v in d.items() if k != 'project'},
        }, project['key'])
        key = f"{project['key']}-{project['next_number']}"
        db.execute('UPDATE projects SET next_number=next_number+1 WHERE key=?', (project['key'],))
        stamp = now()
        db.execute('''INSERT INTO issues(key,project,title,description,type,status,priority,assignee,points,labels,due_date,sprint_id,created_at,updated_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (key, project['key'], f['title'], f['description'], f['type'], f['status'], f['priority'],
                    f['assignee'], f['points'], json.dumps(f['labels'], ensure_ascii=False), f['due_date'], f['sprint_id'], stamp, stamp))
        self.log(db, project['key'], key, 'issue.create', actor, f)
        return self.row(db, 'issues', key)

    def issues(self, db, d, actor):
        only(d, ('project', 'q', 'status', 'type', 'priority', 'assignee', 'sprint_id'))
        items = [self.decode(r) for r in db.execute('SELECT * FROM issues ORDER BY updated_at DESC,rowid DESC')]
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        items = [i for i in items if life.visible('issue',i['key'])]
        for key in ('project', 'status', 'type', 'priority', 'assignee', 'sprint_id'):
            if key in d:
                items = [i for i in items if i[key] == d[key]]
        if d.get('q'):
            q = text(d['q'], '搜索', limit=240).casefold()
            items = [i for i in items if q in (i['key'] + ' ' + i['title'] + ' ' + i['description']).casefold()]
        from .requirements import Requirements
        summaries = Requirements(self).summaries(db, d.get('project'))
        for item in items:
            if item['key'] in summaries:
                item['requirement'] = summaries[item['key']]
        return items

    def get_issue(self, db, d, actor):
        only(d, ('key',))
        item = self.row(db, 'issues', d.get('key'))
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        item['comments'] = [dict(r) for r in db.execute('SELECT * FROM comments WHERE issue_key=? ORDER BY id', (item['key'],))
                            if life.visible('comment',str(r['id']))]
        item['activity'] = self.activity(db, {'target': item['key']}, actor)
        if db.execute('SELECT 1 FROM requirement_links WHERE issue_key=?',(item['key'],)).fetchone():
            from .requirements import Requirements
            item['requirement'] = Requirements(self).get(db, {'key':item['key']},actor)
        return item

    def update_issue(self, db, d, actor):
        only(d, ('key', 'version', 'title', 'description', 'type', 'status', 'priority', 'assignee', 'points', 'labels', 'due_date', 'sprint_id'))
        item = self.row(db, 'issues', d.get('key'))
        if 'version' in d:
            integer(d['version'], '版本', 1, 2**31)
            if d['version'] != item['version']:
                raise DomainError('记录已更新，存在编辑冲突；请刷新后重试', 409)
        fields = self.validate_fields(db, {k: v for k, v in d.items() if k not in ('key', 'version')}, item['project'])
        if not fields:
            raise DomainError('没有提供更新字段')
        changes = {k: {'before': item[k], 'after': v} for k, v in fields.items() if item[k] != v}
        if changes:
            values = [json.dumps(v, ensure_ascii=False) if k == 'labels' else v for k, v in fields.items()]
            db.execute('UPDATE issues SET ' + ','.join(k + '=?' for k in fields) + ',version=version+1,updated_at=? WHERE key=?',
                       (*values, now(), item['key']))
            self.log(db, item['project'], item['key'], 'issue.update', actor, changes)
        return self.row(db, 'issues', item['key'])

    def comment(self, db, d, actor):
        only(d, ('key', 'body'))
        item = self.row(db, 'issues', d.get('key'))
        body = text(d.get('body'), '评论', True)
        cur = db.execute('INSERT INTO comments(issue_key,body,actor,created_at) VALUES(?,?,?,?)', (item['key'], body, actor, now()))
        self.log(db, item['project'], item['key'], 'issue.comment', actor,
                 {'body': body,'kind':'comment','id':str(cur.lastrowid)})
        return self.row(db, 'comments', cur.lastrowid, 'id')

    def sprints(self, db, d, actor):
        only(d, ('project',))
        rows = [dict(r) for r in db.execute('SELECT * FROM sprints ORDER BY id DESC')]
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        return [r for r in rows if (not d.get('project') or r['project'] == d['project']) and life.visible('sprint',str(r['id']))]

    def create_sprint(self, db, d, actor):
        only(d, ('project', 'name', 'goal', 'start_date', 'end_date'))
        project = self.row(db, 'projects', d.get('project'))['key']
        name = text(d.get('name'), '迭代名称', True, 120)
        start, end = date_field(d.get('start_date', '')), date_field(d.get('end_date', ''))
        if start and end and end < start:
            raise DomainError('结束日期不能早于开始日期')
        cur = db.execute('INSERT INTO sprints(project,name,goal,start_date,end_date,status,created_at) VALUES(?,?,?,?,?,?,?)',
                         (project, name, text(d.get('goal', ''), '迭代目标'), start, end, 'planned', now()))
        self.log(db, project, f'sprint:{cur.lastrowid}', 'sprint.create', actor, {'name': name})
        return self.row(db, 'sprints', cur.lastrowid, 'id')

    def start_sprint(self, db, d, actor):
        only(d, ('id',))
        sprint = self.row(db, 'sprints', d.get('id'), 'id')
        if sprint['status'] != 'planned':
            raise DomainError('只有计划中的迭代可以启动')
        db.execute("UPDATE sprints SET status='active' WHERE id=?", (sprint['id'],))
        self.log(db, sprint['project'], f"sprint:{sprint['id']}", 'sprint.start', actor, {})
        return self.row(db, 'sprints', sprint['id'], 'id')

    def complete_sprint(self, db, d, actor):
        only(d, ('id',))
        sprint = self.row(db, 'sprints', d.get('id'), 'id')
        if sprint['status'] != 'active':
            raise DomainError('只有进行中的迭代可以完成')
        unfinished = list(db.execute("SELECT key FROM issues WHERE sprint_id=? AND status!='done'", (sprint['id'],)))
        from .object_lifecycle import Lifecycle
        unfinished = [i for i in unfinished if Lifecycle(db).visible('issue',i['key'])]
        for item in unfinished:
            self.update_issue(db, {'key': item['key'], 'sprint_id': None, 'status': 'backlog'}, actor)
        db.execute("UPDATE sprints SET status='completed' WHERE id=?", (sprint['id'],))
        self.log(db, sprint['project'], f"sprint:{sprint['id']}", 'sprint.complete', actor, {'returned_to_backlog': len(unfinished)})
        return self.row(db, 'sprints', sprint['id'], 'id')

    def releases(self, db, d, actor):
        only(d, ('project',))
        rows = [self.decode(r) for r in db.execute('SELECT * FROM releases ORDER BY id DESC')]
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        return [r for r in rows if (not d.get('project') or r['project'] == d['project']) and life.visible('release',str(r['id']))]

    def release_keys(self, db, project, keys):
        if not isinstance(keys, list) or len(keys) > 500:
            raise DomainError('issue_keys 应是最多 500 项的工作项编号数组')
        if not keys:
            raise DomainError('版本至少关联一个工作项')
        keys = list(dict.fromkeys(text(key, '工作项编号', True, 40) for key in keys))
        for key in keys:
            if self.row(db, 'issues', key)['project'] != project:
                raise DomainError('版本工作项必须属于同一项目')
        return keys

    def create_release(self, db, d, actor):
        only(d, ('project', 'name', 'notes', 'issue_keys'))
        project = self.row(db, 'projects', d.get('project'))['key']
        name = text(d.get('name'), '版本名称', True, 120)
        keys = self.release_keys(db, project, d.get('issue_keys', []))
        cur = db.execute('INSERT INTO releases(project,name,status,notes,issue_keys,created_at) VALUES(?,?,?,?,?,?)',
                         (project, name, 'planned', text(d.get('notes', ''), '发布说明'), json.dumps(list(dict.fromkeys(keys))), now()))
        self.log(db, project, f'release:{cur.lastrowid}', 'release.create', actor, {'name': name})
        return self.row(db, 'releases', cur.lastrowid, 'id')

    def update_release(self, db, d, actor):
        only(d, ('id', 'status', 'name', 'notes', 'issue_keys'))
        release = self.row(db, 'releases', d.get('id'), 'id')
        status = d.get('status', release['status'])
        if status not in ('planned', 'staging', 'released'):
            raise DomainError('版本状态必须是 planned、staging、released')
        if release['status'] == 'released':
            raise DomainError('已发布版本不可修改')
        name = text(d.get('name', release['name']), '版本名称', True, 120)
        notes = text(d.get('notes', release['notes']), '发布说明')
        keys = self.release_keys(db, release['project'], d['issue_keys']) if 'issue_keys' in d else release['issue_keys']
        if status == 'released':
            if not keys:
                raise DomainError('发布前至少关联一个工作项')
            pending = [k for k in keys if self.row(db, 'issues', k)['status'] != 'done']
            if pending:
                raise DomainError('发布被阻止，仍有未完成工作项：' + ', '.join(pending))
        db.execute('UPDATE releases SET status=?,released_at=?,name=?,notes=?,issue_keys=? WHERE id=?',
                   (status, now() if status == 'released' else None, name, notes, json.dumps(keys), release['id']))
        changes = {key: {'before': release[key], 'after': value} for key, value in
                   {'status': status, 'name': name, 'notes': notes, 'issue_keys': keys}.items() if release[key] != value}
        self.log(db, release['project'], f"release:{release['id']}", 'release.update', actor, changes)
        return self.row(db, 'releases', release['id'], 'id')

    def activity(self, db, d, actor):
        only(d, ('project', 'target', 'limit'))
        limit = integer(d.get('limit', 100), 'limit', 1, 500)
        filters = [(key, d[key]) for key in ('project', 'target') if key in d]
        where = ' WHERE ' + ' AND '.join(k + '=?' for k, _ in filters) if filters else ''
        from .object_lifecycle import Lifecycle
        life = Lifecycle(db)
        result = []
        for row in db.execute('SELECT * FROM activity' + where + ' ORDER BY id DESC', tuple(v for _, v in filters)):
            if life.audit_visible(row): result.append(self.decode(row))
            if len(result) == limit: break
        return result

    def summary(self, db, d, actor):
        only(d, ('project',))
        items = self.issues(db, d, actor)
        done = [i for i in items if i['status'] == 'done']
        return {
            'total': len(items), 'done': len(done),
            'in_progress': sum(i['status'] == 'in_progress' for i in items),
            'open_bugs': sum(i['type'] == 'bug' and i['status'] != 'done' for i in items),
            'overdue': sum(bool(i['due_date']) and i['due_date'] < date.today().isoformat() and i['status'] != 'done' for i in items),
            'points': sum(i['points'] for i in items), 'done_points': sum(i['points'] for i in done),
            'by_status': {s: sum(i['status'] == s for i in items) for s in STATUSES},
        }

    def analytics(self, db, d, actor):
        from .analytics import build_report, release_readiness
        only(d, ('project','scope'))
        project = self.row(db, 'projects', d.get('project'))['key']
        scope = d.get('scope', 'active')
        items = self.issues(db, {'project':project}, actor)
        sprints = self.sprints(db, {'project':project}, actor)
        releases = release_readiness(self.releases(db, {'project':project}, actor), items)
        active = next((s for s in sprints if s['status']=='active'), None)
        today = date.today()
        def report(key, sprint=None):
            selected = items if key=='project' else [i for i in items if sprint and i['sprint_id']==sprint['id']]
            return build_report(selected, sprint, key, project, releases, today)
        if scope=='all':
            result = {'project':report('project'), 'active':report('active',active)}
            result.update({f"sprint:{s['id']}":report(f"sprint:{s['id']}",s) for s in sprints})
            return result
        if scope=='project': return report(scope)
        if scope=='active': return report(scope,active)
        selected = next((s for s in sprints if scope==f"sprint:{s['id']}"),None)
        if not selected:
            raise DomainError('分析范围无效：请选择 project、active 或本项目 sprint:ID')
        return report(scope,selected)
