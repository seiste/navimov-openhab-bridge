#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import asyncio
import json
import sys

import aiohttp
from mower_sdk import MowerClient
from mower_sdk.errors import MowerAPIError

from navimow_common import load_tokens, save_tokens, token_is_expired
from navimow_refresh import refresh_tokens


def dump_obj(obj) -> str:
    try:
        return json.dumps(obj.__dict__, indent=2, ensure_ascii=False, default=str)
    except Exception:
        try:
            return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
        except Exception:
            return str(obj)


def get_cfg_auto_refresh() -> dict:
    cfg = load_tokens()
    if not cfg.get("access_token") or token_is_expired(cfg):
        cfg = refresh_tokens()
    return cfg


def print_usage() -> None:
    print("Usage:")
    print("  navimowctl.py devices")
    print("  navimowctl.py status DEVICE_ID")
    print("  navimowctl.py start DEVICE_ID")
    print("  navimowctl.py pause DEVICE_ID")
    print("  navimowctl.py resume DEVICE_ID")
    print("  navimowctl.py dock DEVICE_ID")
    print("  navimowctl.py refresh")


async def run() -> int:
    if len(sys.argv) < 2:
        print_usage()
        return 1

    cmd = sys.argv[1]

    if cmd == "refresh":
        cfg = refresh_tokens()
        print("Tokens refreshed and saved.")
        return 0

    cfg = get_cfg_auto_refresh()
    session = aiohttp.ClientSession()
    try:
        client = MowerClient(
            session=session,
            token=cfg["access_token"],
            api_base_url=cfg["api_base_url"],
        )
        if cmd == "devices":
            devices = await client.async_discover_devices()
            print(json.dumps(
                [getattr(d, "__dict__", str(d)) for d in devices],
                indent=2,
                ensure_ascii=False,
                default=str,
            ))
            return 0

        if len(sys.argv) < 3:
            print("DEVICE_ID fehlt")
            print_usage()
            return 1

        device_id = sys.argv[2]

        if cmd == "status":
            result = await client.async_get_device_status(device_id)
        elif cmd == "start":
            result = await client.async_start_mowing(device_id)
        elif cmd == "pause":
            result = await client.async_pause_mowing(device_id)
        elif cmd == "resume":
            result = await client.async_resume(device_id)
        elif cmd == "dock":
            result = await client.async_dock(device_id)
        else:
            print(f"Unbekannter Befehl: {cmd}")
            print_usage()
            return 1

        print(dump_obj(result))
        return 0

    except MowerAPIError as e:
        msg = str(e)

        if "401" in msg or "403" in msg or "unauthorized" in msg.lower():
            print("Access-Token wurde abgelehnt, versuche Refresh ...", file=sys.stderr)
            cfg = refresh_tokens()
            save_tokens(cfg)
            print("Token erneuert. Bitte Befehl nochmals ausführen.", file=sys.stderr)
            return 2

        print(f"Navimow API Fehler: {e}", file=sys.stderr)
        return 2

    finally:
        await session.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
