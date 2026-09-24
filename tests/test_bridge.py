# SPDX-License-Identifier: GPL-3.0-only
"""Offline regression tests; external transports and SDK are substituted."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        config = json.loads((ROOT / 'config.example.json').read_text())
        config['device_id'] = 'TEST_DEVICE'
        config['oauth']['client_secret'] = 'TEST_SECRET'
        cfg_path = Path(cls.tmp.name) / 'config.json'
        cfg_path.write_text(json.dumps(config))
        cls.env = patch.dict(os.environ, {'NAVIMOW_CONFIG': str(cfg_path), 'NAVIMOW_CLIENT_SECRET': 'TEST_SECRET'})
        cls.env.start()
        requests = types.ModuleType('requests')
        requests.post = Mock()
        requests.put = Mock()
        aiohttp = types.ModuleType('aiohttp')
        aiohttp.ClientSession = Mock()
        mower = types.ModuleType('mower_sdk')
        mower.MowerClient = Mock()
        errors = types.ModuleType('mower_sdk.errors')
        errors.MowerAPIError = type('MowerAPIError', (Exception,), {})
        cls.modules = patch.dict(sys.modules, {
            'requests': requests, 'aiohttp': aiohttp,
            'mower_sdk': mower, 'mower_sdk.errors': errors,
        })
        cls.modules.start()
        for name in ('navimow_common', 'navimow_refresh', 'navimow_to_openhab'):
            sys.modules.pop(name, None)
        cls.common = importlib.import_module('navimow_common')
        cls.refresh = importlib.import_module('navimow_refresh')
        cls.bridge = importlib.import_module('navimow_to_openhab')

    @classmethod
    def tearDownClass(cls):
        cls.modules.stop()
        cls.env.stop()
        for name in ('navimow_common', 'navimow_refresh', 'navimow_to_openhab'):
            sys.modules.pop(name, None)
        cls.tmp.cleanup()

    def setUp(self):
        self.old = {'access_token': 'OLD_ACCESS', 'refresh_token': 'OLD_REFRESH', 'api_base_url': 'https://example.invalid'}
        self.common.save_tokens(self.old)

    def respond(self, payload, status=200):
        return patch.object(self.refresh.requests, 'post', return_value=Mock(status_code=status, json=Mock(return_value=payload)))

    def test_failed_responses_preserve_tokens(self):
        before = self.common.TOKENS_FILE.read_bytes()
        for payload, status in [({'error': 'invalid_grant'}, 400), ({}, 200), ([], 200),
                                ({'access_token': '', 'expires_in': 3600}, 200),
                                ({'access_token': 'NEW', 'expires_in': 'bad'}, 200),
                                ({'access_token': 'NEW', 'expires_in': float('nan')}, 200)]:
            with self.subTest(payload=payload), self.respond(payload, status):
                with self.assertRaises(RuntimeError):
                    self.refresh.refresh_tokens()
                self.assertEqual(before, self.common.TOKENS_FILE.read_bytes())

    def test_refresh_rotation(self):
        with self.respond({'access_token': 'NEW_ACCESS', 'refresh_token': 'NEW_REFRESH', 'expires_in': 3600}):
            result = self.refresh.refresh_tokens()
        self.assertEqual(result['refresh_token'], 'NEW_REFRESH')
        self.assertEqual(self.common.load_tokens(), result)
        self.assertFalse(self.common.token_is_expired(result))

    def test_refresh_retains_old_when_not_rotated(self):
        with self.respond({'access_token': 'NEW_ACCESS', 'expires_in': 3600}):
            result = self.refresh.refresh_tokens()
        self.assertEqual(result['refresh_token'], 'OLD_REFRESH')

    def test_atomic_replace_failure_preserves_old(self):
        before = self.common.TOKENS_FILE.read_bytes()
        with patch.object(self.common.os, 'replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                self.common.save_tokens({'access_token': 'NEW'})
        self.assertEqual(before, self.common.TOKENS_FILE.read_bytes())
        self.assertEqual(list(self.common.TOKENS_FILE.parent.glob('.navimow-*.tmp')), [])

    def test_unknown_expiry_requires_refresh(self):
        for value in ({}, {'expires_at': 'bad'}, {'expires_at': float('inf')}):
            self.assertTrue(self.common.token_is_expired(value))

    def run_poll(self, last=None, failure=None, writer_failure=False):
        class Session:
            closed = False
            async def close(inner):
                inner.closed = True
        session = Session()
        async def status(_device):
            if failure:
                raise failure
            return {'status': 'DOCKED', 'battery': 85, 'extra': {}, 'error_code': 'NONE'}
        async def client():
            return session, types.SimpleNamespace(async_get_device_status=status)
        calls = []
        def write(item, value):
            calls.append((item, value))
            if writer_failure and item == self.bridge.ITEM_BATTERY:
                raise RuntimeError('simulated openHAB failure')
        with patch.object(self.bridge, 'get_client', client), patch.object(self.bridge, 'oh_put_state', write):
            result = asyncio.run(self.bridge.poll_once(last))
        self.assertTrue(session.closed)
        return result, calls

    def test_heartbeat_after_values_and_on_unchanged_poll(self):
        blob, calls = self.run_poll()
        self.assertEqual(calls[-1][0], self.bridge.ITEM_LASTUPDATE)
        self.assertLess([x[0] for x in calls].index(self.bridge.ITEM_BATTERY), len(calls) - 1)
        again, calls = self.run_poll(blob)
        self.assertEqual(again, blob)
        self.assertEqual([x[0] for x in calls], [self.bridge.ITEM_ONLINE, self.bridge.ITEM_LASTUPDATE])

    def test_partial_openhab_failure_does_not_advance_heartbeat(self):
        result, calls = self.run_poll('OLD', writer_failure=True)
        self.assertEqual(result, 'OLD')
        self.assertNotIn(self.bridge.ITEM_LASTUPDATE, [x[0] for x in calls])
        self.assertEqual(calls[-1], (self.bridge.ITEM_ONLINE, 'OFF'))

    def test_auth_error_refreshes_once_without_success_heartbeat(self):
        with patch.object(self.bridge, 'refresh_tokens') as refresh:
            result, calls = self.run_poll('OLD', failure=self.bridge.MowerAPIError('401'))
            refresh.assert_called_once()
        self.assertEqual(result, 'OLD')
        self.assertEqual(calls, [(self.bridge.ITEM_ONLINE, 'OFF')])

    def test_client_construction_failure_closes_session(self):
        class Session:
            closed = False
            async def close(inner):
                inner.closed = True
        session = Session()
        with patch.object(self.bridge, 'load_tokens', return_value=self.old), \
             patch.object(self.bridge, 'token_is_expired', return_value=False), \
             patch.object(self.bridge.aiohttp, 'ClientSession', return_value=session), \
             patch.object(self.bridge, 'MowerClient', side_effect=RuntimeError('constructor failed')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.bridge.get_client())
        self.assertTrue(session.closed)


if __name__ == '__main__':
    unittest.main()
