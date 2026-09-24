#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import aiohttp
import requests
from mower_sdk import MowerClient
from mower_sdk.errors import MowerAPIError

from navimow_common import load_tokens, token_is_expired, CONFIG
from navimow_refresh import refresh_tokens

DEVICE_ID = CONFIG["device_id"]
POLL_SECONDS = CONFIG["poll_seconds"]

OPENHAB_BASE = CONFIG["openhab_base_url"].rstrip("/") + "/rest/items"

ITEM_STATUS = "Navimow_Status"
ITEM_VEHICLE = "Navimow_VehicleState"
ITEM_BATTERY = "Navimow_Battery"
ITEM_ERROR = "Navimow_Error"
ITEM_ERRORMSG = "Navimow_ErrorMessage"
ITEM_ONLINE = "Navimow_Online"
ITEM_LASTUPDATE = "Navimow_LastUpdate"


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def unwrap_enum(value) -> str:
    if value is None:
        return ""
    s = str(value)
    if "." in s:
        return s.split(".")[-1]
    return s


def oh_put_state(item: str, value) -> None:
    url = f"{OPENHAB_BASE}/{item}/state"
    r = requests.put(
        url,
        data=str(value).encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        auth=(CONFIG["openhab_api_token"], "") if CONFIG.get("openhab_api_token") else None,
        timeout=15,
    )
    r.raise_for_status()


def is_token_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "401" in msg
        or "403" in msg
        or "unauthorized" in msg
        or "invalid_token" in msg
        or "token" in msg and "expired" in msg
    )


async def get_client():
    cfg = load_tokens()

    if not cfg.get("access_token"):
        print(now_text(), "Token file has no access_token, trying refresh ...", flush=True)
        cfg = refresh_tokens()

    elif token_is_expired(cfg):
        print(now_text(), "Access token expired locally, refreshing ...", flush=True)
        cfg = refresh_tokens()
        print(now_text(), "Access token refreshed", flush=True)

    if not cfg.get("access_token"):
        raise RuntimeError("Kein access_token verfügbar. Manueller Login nötig.")

    api_base_url = cfg.get("api_base_url", "https://navimow-fra.ninebot.com")

    session = None
    try:
        session = aiohttp.ClientSession()
        client = MowerClient(
            session=session,
            token=cfg["access_token"],
            api_base_url=api_base_url,
        )
        return session, client
    except Exception:
        if session is not None:
            await session.close()
        raise


async def poll_once(last_blob: str | None) -> str | None:
    session = None

    try:
        session, client = await get_client()
        status = await client.async_get_device_status(DEVICE_ID)

        data = getattr(status, "__dict__", status)
        blob = json.dumps(data, sort_keys=True, default=str)

        ts = now_text()

        if blob != last_blob:
            status_txt = unwrap_enum(data.get("status"))
            error_txt = unwrap_enum(data.get("error_code"))
            error_msg = data.get("error_message") or ""
            battery = data.get("battery")
            extra = data.get("extra") or {}
            vehicle_state = extra.get("vehicleState", "")

            oh_put_state(ITEM_STATUS, status_txt)
            oh_put_state(ITEM_VEHICLE, vehicle_state)
            oh_put_state(ITEM_ERROR, error_txt)
            oh_put_state(ITEM_ERRORMSG, error_msg)

            if battery is not None:
                oh_put_state(ITEM_BATTERY, battery)

            print(
                ts,
                f"OpenHAB values updated: status={status_txt} vehicle={vehicle_state} battery={battery} error={error_txt}",
                flush=True,
            )
            oh_put_state(ITEM_ONLINE, "ON")
            oh_put_state(ITEM_LASTUPDATE, ts)
            return blob

        oh_put_state(ITEM_ONLINE, "ON")
        oh_put_state(ITEM_LASTUPDATE, ts)
        print(ts, "Poll OK, no status change", flush=True)
        return last_blob

    except MowerAPIError as e:
        ts = now_text()
        print(ts, "Navimow API error:", e, flush=True)

        if is_token_error(e):
            print(ts, "Token error detected, trying refresh ...", flush=True)
            try:
                refresh_tokens()
                print(ts, "Token refreshed; next poll will retry", flush=True)
            except Exception as re:
                print(ts, "Token refresh failed; manual re-login may be required:", re, flush=True)

        try:
            oh_put_state(ITEM_ONLINE, "OFF")
        except Exception as ee:
            print(ts, "OpenHAB update error:", ee, flush=True)

        return last_blob

    except Exception as e:
        ts = now_text()
        print(ts, "General error:", e, flush=True)

        try:
            oh_put_state(ITEM_ONLINE, "OFF")
        except Exception as ee:
            print(ts, "OpenHAB update error:", ee, flush=True)

        return last_blob

    finally:
        if session is not None:
            await session.close()


async def main():
    if not DEVICE_ID or DEVICE_ID == "YOUR_DEVICE_ID":
        raise SystemExit("Set device_id in config.json first.")
    last_blob = None

    print(now_text(), "Navimow OpenHAB poller started", flush=True)
    print(now_text(), f"Polling every {POLL_SECONDS} seconds", flush=True)

    while True:
        last_blob = await poll_once(last_blob)
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
