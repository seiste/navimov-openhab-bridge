# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import math
import time
import requests

from navimow_common import (
    CLIENT_ID, CLIENT_SECRET, TOKEN_URL, API_BASE_URL, load_tokens, save_tokens,
)


def exchange_tokens(fields: dict, old: dict | None = None) -> dict:
    if not CLIENT_SECRET:
        raise RuntimeError('Configure oauth.client_secret or NAVIMOW_CLIENT_SECRET first')
    old = old or {}
    response = requests.post(TOKEN_URL, data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, **fields,
    }, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'Token request failed: HTTP {response.status_code}; login may be required')
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError('Token endpoint returned invalid JSON') from None
    if not isinstance(payload, dict) or payload.get('error'):
        raise RuntimeError('Token endpoint returned an invalid response')
    token = payload.get('access_token')
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError('Token response has no valid access_token; saved tokens unchanged')
    refresh = payload.get('refresh_token') or old.get('refresh_token')
    if not isinstance(refresh, str) or not refresh.strip():
        raise RuntimeError('Token response has no valid refresh_token; saved tokens unchanged')
    try:
        lifetime = float(payload['expires_in'])
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('Token response has no valid expires_in; saved tokens unchanged') from None
    if not math.isfinite(lifetime) or lifetime <= 0:
        raise RuntimeError('Token response has an invalid lifetime; saved tokens unchanged')
    result = {
        'access_token': token, 'refresh_token': refresh,
        'expires_in': lifetime, 'expires_at': time.time() + lifetime,
        'api_base_url': old.get('api_base_url', API_BASE_URL),
    }
    save_tokens(result)
    return result


def refresh_tokens() -> dict:
    old = load_tokens()
    refresh = old.get('refresh_token')
    if not refresh:
        raise RuntimeError('No refresh_token available; run navimow_login.py')
    return exchange_tokens({'grant_type': 'refresh_token', 'refresh_token': refresh}, old)


if __name__ == '__main__':
    refresh_tokens()
    print('Tokens refreshed and saved.')
