# SPDX-License-Identifier: GPL-3.0-only
"""Receive a loopback OAuth callback, validate state, and save tokens."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
import webbrowser

from navimow_common import OAUTH, CLIENT_ID
from navimow_refresh import exchange_tokens


def main():
    redirect = OAUTH['redirect_uri']
    callback = urlsplit(redirect)
    if callback.scheme != 'http' or callback.hostname != '127.0.0.1' or callback.query or callback.fragment:
        raise ValueError('redirect_uri must be an HTTP callback on 127.0.0.1 without query or fragment')
    state = secrets.token_urlsafe(32)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            valid = (parsed.path == callback.path and query.get('state') == [state])
            code = query.get('code', [])
            accepted = valid and len(code) == 1 and bool(code[0])
            if accepted:
                result['code'] = code[0]
            elif valid and query.get('error'):
                result['error'] = True
            self.send_response(200 if accepted else 400)
            self.end_headers()
            self.wfile.write(b'Callback received. Check the terminal.' if accepted else b'Login callback rejected.')

        def log_message(self, *_args):
            pass

    base = urlsplit(OAUTH['authorize_url'])
    params = parse_qs(base.query)
    params.update(client_id=[CLIENT_ID], redirect_uri=[redirect], response_type=['code'], state=[state])
    url = urlunsplit((base.scheme, base.netloc, base.path, urlencode(params, doseq=True), base.fragment))
    with HTTPServer(('127.0.0.1', callback.port or 80), Handler) as server:
        server.timeout = 1
        print('Open this URL in your browser:\n' + url, flush=True)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result.get('code'):
        raise SystemExit('Login cancelled or timed out; saved tokens unchanged.')
    exchange_tokens({'grant_type': 'authorization_code', 'code': result['code'], 'redirect_uri': redirect})
    print('Login successful. Tokens saved.')


if __name__ == '__main__':
    main()
