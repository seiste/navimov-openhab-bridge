# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time

CONFIG_FILE = Path(os.environ.get('NAVIMOW_CONFIG', Path(__file__).with_name('config.json'))).resolve()
with CONFIG_FILE.open(encoding='utf-8') as handle:
    CONFIG = json.load(handle)
interval = CONFIG.get('poll_seconds', 300)
if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < 30:
    raise ValueError('poll_seconds must be a finite number of at least 30 seconds')
CONFIG['poll_seconds'] = interval
TOKENS_FILE = Path(CONFIG.get('tokens_file', 'navimow_tokens.json'))
if not TOKENS_FILE.is_absolute():
    TOKENS_FILE = CONFIG_FILE.parent / TOKENS_FILE
OAUTH = CONFIG['oauth']
CLIENT_ID = OAUTH['client_id']
CLIENT_SECRET = os.environ.get('NAVIMOW_CLIENT_SECRET') or OAUTH.get('client_secret', '')
TOKEN_URL = OAUTH['token_url']
API_BASE_URL = OAUTH['api_base_url']


def load_tokens() -> dict:
    with TOKENS_FILE.open(encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError('Token file must contain a JSON object')
    return data


def save_tokens(data: dict) -> None:
    if not isinstance(data.get('access_token'), str) or not data['access_token'].strip():
        raise ValueError('Refusing to save a token response without a valid access_token')
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.navimow-', suffix='.tmp', dir=TOKENS_FILE.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, TOKENS_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def token_is_expired(cfg: dict, skew_seconds: int = 60) -> bool:
    try:
        expiry = float(cfg['expires_at'])
    except (KeyError, ValueError, TypeError):
        return True
    return not math.isfinite(expiry) or time.time() >= expiry - skew_seconds
