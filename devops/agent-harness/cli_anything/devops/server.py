"""Loopback-only web app and API. All writes require same-origin JSON requests."""
import argparse
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from .store import Store, DomainError, STATUSES, TYPES, PRIORITIES

WEB = Path(__file__).parent / 'web'

def make_server(db_path, port=8766):
    store = Store(db_path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not log arbitrary user request bodies or query strings.
            pass

        def send(self, status, payload, mime='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def guard(self, write=False):
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if host not in expected:
                raise DomainError('只允许本机访问', 403)
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                raise DomainError('跨站请求被拒绝', 403)
            if write:
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    raise DomainError('请使用 application/json', 415)
                if self.headers.get('X-Forge-Client') != '1':
                    raise DomainError('缺少客户端标识', 403)

        def do_GET(self):
            try:
                self.guard()
                url = urlsplit(self.path)
                if url.path == '/api/health':
                    return self.send(200, {'ok': True, 'name': 'Forge DevOps', 'version': '0.1.0'})
                if url.path == '/api/state':
                    projects = store.call('project.list')
                    project = parse_qs(url.query).get('project', [projects[0]['key'] if projects else ''])[0]
                    if project and project not in {p['key'] for p in projects}:
                        # Only a known hidden project URL falls back; typos remain 404.
                        hidden = store.call('object.get',{'kind':'project','id':project,'include_deleted':True})
                        if not hidden['deleted']: raise DomainError('项目不存在',404)
                        project = projects[0]['key'] if projects else ''
                    state = {'projects': projects, 'project': project, 'statuses': STATUSES, 'types': TYPES, 'priorities': PRIORITIES}
                    for key, action in [('issues', 'issue.list'), ('sprints', 'sprint.list'), ('releases', 'release.list'), ('activity', 'activity.list'), ('summary', 'report.summary')]:
                        state[key] = store.call(action, {'project': project})
                    state['analytics'] = store.call('report.analytics', {'project':project,'scope':'all'}) if project else {}
                    return self.send(200, state)
                assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
                assets.update({'/analytics.js': ('analytics.js','text/javascript; charset=utf-8'),
                               '/analytics.css': ('analytics.css','text/css; charset=utf-8')})
                assets.update({'/requirements.js':('requirements.js','text/javascript; charset=utf-8'),
                               '/requirements.css':('requirements.css','text/css; charset=utf-8')})
                if url.path in assets:
                    name, mime = assets[url.path]
                    return self.send(200, (WEB / name).read_bytes(), mime)
                self.send(404, {'error': '页面不存在'})
            except DomainError as exc:
                self.send(exc.status, {'error': str(exc)})
            except Exception:
                logging.exception('GET failed')
                self.send(500, {'error': '服务内部错误'})

        def do_POST(self):
            try:
                self.guard(write=True)
                bulk = self.path == '/api/requirements/import'
                if self.path not in ('/api/call','/api/requirements/import'):
                    raise DomainError('接口不存在', 404)
                if self.headers.get('Transfer-Encoding'):
                    raise DomainError('不支持分块请求')
                length = int(self.headers.get('Content-Length', '0'))
                self.connection.settimeout(2)
                if not 0 < length <= (32 * 1024 * 1024 if bulk else 2 * 1024 * 1024):
                    # Drain a bounded small over-limit body before closing, so the
                    # client receives HTTP 413 instead of a TCP reset on macOS.
                    if 0 < length <= 131072:
                        self.rfile.read(length)
                    raise DomainError('请求体过大或为空', 413)
                self.connection.settimeout(10)
                try:
                    body = json.loads(self.rfile.read(length))
                except (ValueError,UnicodeError):
                    if not bulk and length > 65536: raise DomainError('请求体过大或无效',413) from None
                    raise
                if not isinstance(body, dict) or set(body) - {'action', 'data'}:
                    raise DomainError('请求必须包含 action 和 data 对象')
                if not bulk and length > 65536 and body.get('action') not in (
                        'object.create','object.update','requirement.update','issue.create','issue.update'):
                    raise DomainError('请求体过大',413)
                if bulk and body.get('action') != 'requirement.import':
                    raise DomainError('此接口仅接受需求导入')
                result = store.call(body.get('action'), body.get('data'), unquote(self.headers.get('X-Forge-Actor', '网页')))
                self.send(200, {'data': result})
            except DomainError as exc:
                self.send(exc.status, {'error': str(exc)})
            except (ValueError, UnicodeError):
                self.send(400, {'error': '无效 JSON 或请求长度'})
            except Exception:
                logging.exception('POST failed')
                self.send(500, {'error': '服务内部错误'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)

def main():
    parser = argparse.ArgumentParser(description='Forge DevOps local server')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--db', default=os.environ.get('FORGE_DEVOPS_DB', str(Path.home() / '.local/share/forge-devops/data.sqlite3')))
    args = parser.parse_args()
    server = make_server(args.db, args.port)
    print(f'Forge DevOps: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
