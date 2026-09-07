"""CLI adapter to the real Forge server. No shadow database or fake responses."""
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Backend:
    def __init__(self, url, actor='Codex/CLI'):
        parts = urlsplit(url)
        if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost') or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
            raise ValueError('服务地址必须是本地 http://127.0.0.1:端口')
        self.url, self.actor = url.rstrip('/'), actor
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, payload=None):
        # URL-encode non-ASCII actor label for valid HTTP headers.
        from urllib.parse import quote
        headers = {'Content-Type': 'application/json', 'X-Forge-Client': '1', 'X-Forge-Actor': quote(self.actor)}
        request = Request(self.url + path, data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None, headers=headers)
        try:
            with self.opener.open(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                message = json.load(exc).get('error', str(exc))
            except (ValueError, AttributeError):
                message = f'HTTP {exc.code}'
            raise ValueError(message) from None
        except (URLError, OSError):
            raise ValueError(f'无法连接 {self.url}，请先运行 forge-devops-server') from None

    def call(self, action, data):
        path = '/api/requirements/import' if action == 'requirement.import' else '/api/call'
        return self.request(path, {'action': action, 'data': data})['data']
