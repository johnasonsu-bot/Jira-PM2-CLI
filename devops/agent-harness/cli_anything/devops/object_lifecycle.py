"""Shared identity, visibility and revisions; callers supply their transaction."""
import hashlib
import json
import re

from .store import DomainError, integer, text
from .requirements import encoded

KINDS = ('project', 'issue', 'requirement', 'scenario', 'sprint', 'release', 'comment')
TABLES = {'project':'projects', 'issue':'issues', 'requirement':'requirement_links',
          'scenario':'requirement_scenarios', 'sprint':'sprints', 'release':'releases', 'comment':'comments'}


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS object_tombstones (
            kind TEXT NOT NULL, object_id TEXT NOT NULL, deleted INTEGER NOT NULL,
            generation INTEGER NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(kind, object_id));
        CREATE TABLE IF NOT EXISTS object_requests (
            actor TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
            result TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(actor, request_id));
    ''')


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


def identity(kind, value):
    if not isinstance(kind, str) or kind not in KINDS:
        raise DomainError('对象类型必须是：' + ', '.join(KINDS))
    original = value
    value = text(value, '对象 ID', True, 182)
    if value != original: raise DomainError('对象 ID 不可含首尾空格')
    if kind in ('sprint','release','comment'):
        if not re.fullmatch(r'[1-9][0-9]*', value):
            raise DomainError('对象 ID 必须是正十进制 ID 字符串')
        integer(int(value), 'ID', 1, 2**31)
    elif kind == 'scenario':
        parts = value.split('::', 1)
        if len(parts) != 2:
            raise DomainError('场景 ID 必须是 issue_key::scenario_code')
        text(parts[0], '工作项标识', True, 40)
        text(parts[1], '场景编号', True, 140)
    else:
        text(value, '标识', True, 40)
    return kind, value


class Lifecycle:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def shared(kind, value):
        return ('issue' if kind == 'requirement' else kind, value)

    def raw(self, kind, value):
        kind, value = identity(kind, value)
        field = 'id' if kind in ('sprint','release','comment') else 'issue_key' if kind in ('requirement','scenario') else 'key'
        args = (value,)
        where = field + '=?'
        if kind == 'scenario':
            args = tuple(value.split('::', 1))
            where = 'issue_key=? AND scenario_code=?'
        row = self.db.execute(f'SELECT * FROM {TABLES[kind]} WHERE {where}',args).fetchone()
        if row is None:
            raise DomainError(f'记录不存在：{value}', 404)
        return dict(row)

    def state(self, kind, value):
        row = self.db.execute('SELECT * FROM object_tombstones WHERE kind=? AND object_id=?',self.shared(kind,value)).fetchone()
        return dict(row) if row else None

    def parent(self, kind, value, row=None):
        row = row or self.raw(kind,value)
        if kind == 'project': return None
        if kind == 'requirement': return ('issue',value)
        if kind in ('scenario','comment'): return ('issue',row['issue_key'])
        return ('project',row['project'])

    def visible(self, kind, value, restoring=None):
        try:
            row = self.raw(kind,value)
        except DomainError as exc:
            if exc.status == 404: return False
            raise
        state = self.state(kind,value)
        if state and state['deleted'] and self.shared(kind,value) != restoring:
            return False
        parent = self.parent(kind,value,row)
        return not parent or self.visible(*parent,restoring=restoring)

    def require_visible(self, kind, value):
        if not self.visible(kind,value):
            raise DomainError(f'记录不存在或已删除：{value}',404)

    def revision(self, kind, value):
        row = self.raw(kind,value)
        state = [self.state(kind,value)]
        parent = self.parent(kind,value,row)
        while parent:
            state.append(self.state(*parent))
            parent = self.parent(*parent)
        related = None
        if kind == 'requirement': related = self.raw('issue',value)
        if kind == 'issue':
            link = self.db.execute('SELECT * FROM requirement_links WHERE issue_key=?',(value,)).fetchone()
            related = dict(link) if link else None
        # Audit sequence notices legacy changes even when a value is later reverted.
        target = self.target(kind,value,row)
        audit = self.db.execute('SELECT MAX(id) FROM activity WHERE target=?',(target,)).fetchone()[0]
        return digest([kind,value,row,related,state,audit])

    def target(self, kind, value, row=None):
        if kind in ('sprint','release'): return kind + ':' + value
        if kind in ('scenario','comment'): return (row or self.raw(kind,value))['issue_key']
        return value

    def project(self, kind, value, row=None):
        row = row or self.raw(kind,value)
        if kind == 'project': return value
        if kind in ('requirement','scenario','comment'):
            return self.raw('issue',row['issue_key'])['project']
        return row['project']

    def ids(self, kind):
        if kind not in KINDS: raise DomainError('不支持的对象类型')
        field = 'id' if kind in ('sprint','release','comment') else 'issue_key' if kind in ('requirement','scenario') else 'key'
        cols = 'issue_key,scenario_code' if kind == 'scenario' else field
        rows = self.db.execute(f'SELECT {cols} FROM {TABLES[kind]} ORDER BY {cols}')
        return [r['issue_key']+'::'+r['scenario_code'] if kind=='scenario' else str(r[field]) for r in rows]

    def closure(self, kind, value):
        self.raw(kind,value)
        result = []
        for candidate in KINDS:
            if kind not in ('project','issue','requirement') and candidate != kind: continue
            for ident in self.ids(candidate):
                if kind == 'project':
                    match = self.project(candidate,ident) == value
                elif kind in ('issue','requirement'):
                    match = ((candidate in ('issue','requirement') and ident==value) or
                             (candidate in ('comment','scenario') and self.raw(candidate,ident)['issue_key']==value))
                else: match = ident == value
                if match: result.append((candidate,ident))
        return result

    def audit_visible(self, row):
        if not self.visible('project',row['project']): return False
        target = row['target']
        if target == row['project']: return True
        for kind in ('sprint','release'):
            if target.startswith(kind+':'): return self.visible(kind,target.split(':',1)[1])
        if not self.visible('issue',target): return False
        changes = json.loads(row['changes'])
        kind, ident = changes.get('kind'), changes.get('id')
        if kind in KINDS and isinstance(ident,str): return self.visible(kind,ident)
        if row['action']=='requirement.scenario.update' and changes.get('scenario_code'):
            return self.visible('scenario',target+'::'+changes['scenario_code'])
        if row['action']=='issue.comment' and 'body' in changes:
            # Before this migration each comment and its creation audit were inserted
            # together, in order, and neither table physically deletes rows. Match
            # that order rather than mutable body text or second-resolution clocks.
            ordinal = self.db.execute("SELECT COUNT(*) FROM activity WHERE target=? AND action='issue.comment' AND id<=?",
                                      (target,row['id'])).fetchone()[0]
            comment = self.db.execute('SELECT id FROM comments WHERE issue_key=? ORDER BY id LIMIT 1 OFFSET ?',
                                      (target,ordinal-1)).fetchone()
            if comment: return self.visible('comment',str(comment['id']))
        return True
