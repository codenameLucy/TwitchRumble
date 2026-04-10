"""
auth.py — Twitch Device Code Grant Flow
Handles first-time authorization, token storage, and automatic refresh.
"""

import asyncio
import json
import time
import os
import sys
import aiohttp

# Resolve the configs directory relative to the executable (or repo root when
# running from source). sys.executable points to the .exe inside a PyInstaller
# bundle, and to the python interpreter when running from source — both cases
# end up finding the configs/ folder in the right place.
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
else:
    _exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_configs_dir = os.path.join(_exe_dir, "configs")
os.makedirs(_configs_dir, exist_ok=True)
TOKEN_FILE = os.path.join(_configs_dir, "twitch_token.json")

# Scopes needed: read/send chat + listen to channel point redemptions
SCOPES = "chat:read chat:edit channel:read:redemptions"


async def _request(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> dict:
    async with session.request(method, url, **kwargs) as resp:
        return await resp.json()


async def _start_device_flow(session: aiohttp.ClientSession, client_id: str) -> dict:
    """Step 1: Ask Twitch for a device code."""
    data = await _request(
        session, "POST",
        "https://id.twitch.tv/oauth2/device",
        data={"client_id": client_id, "scopes": SCOPES},
    )
    return data


async def _poll_for_token(
    session: aiohttp.ClientSession,
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
) -> dict | None:
    """Step 2: Poll until the user authorizes or the code expires."""
    deadline = time.time() + expires_in
    while time.time() < deadline:
        await asyncio.sleep(interval)
        result = await _request(
            session, "POST",
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id":   client_id,
                "device_code": device_code,
                "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                "scopes":      SCOPES,
            },
        )
        if "access_token" in result:
            return result
        msg = result.get("message", "")
        if msg == "authorization_pending":
            continue
        if msg == "slow_down":
            interval += 5
            continue
        print(f"[Auth] Error during polling: {result}")
        return None
    print("[Auth] Device code expired.")
    return None


async def _refresh_token(
    session: aiohttp.ClientSession,
    client_id: str,
    refresh_tok: str,
) -> dict | None:
    """Exchange a refresh token for a new access token."""
    result = await _request(
        session, "POST",
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id":     client_id,
            "grant_type":    "refresh_token",
            "refresh_token": refresh_tok,
        },
    )
    if "access_token" in result:
        return result
    print(f"[Auth] Refresh failed: {result}")
    return None


def _save_token(data: dict, client_id: str):
    payload = {
        "access_token":  data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at":    time.time() + data.get("expires_in", 14400),
        "client_id":     client_id,
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[Auth] Token saved to {TOKEN_FILE}")


def _load_token() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


async def get_valid_token(client_id: str) -> str:
    """
    Returns a valid access token, going through the full flow if needed.
    Call this once at startup; it blocks until the user authorizes.
    """
    async with aiohttp.ClientSession() as session:

        saved = _load_token()

        if saved and saved.get("client_id") == client_id:
            if saved["expires_at"] - time.time() > 60:
                print("[Auth] Using saved access token.")
                return saved["access_token"]

            if saved.get("refresh_token"):
                print("[Auth] Access token expired, refreshing…")
                refreshed = await _refresh_token(session, client_id, saved["refresh_token"])
                if refreshed:
                    _save_token(refreshed, client_id)
                    return refreshed["access_token"]
                print("[Auth] Refresh failed, starting new auth flow.")

        print("[Auth] Starting Twitch Device Code authorization…")
        device = await _start_device_flow(session, client_id)

        if "error" in device:
            raise RuntimeError(f"[Auth] Failed to start device flow: {device}")

        print("\n" + "═" * 60)
        print("  TWITCH AUTHORIZATION REQUIRED")
        print("═" * 60)
        print(f"  1. Open this URL in your browser:")
        print(f"     {device['verification_uri']}")
        print(f"  2. Enter code: {device['user_code']}")
        print(f"  3. Click Authorize")
        print(f"  (Code expires in {device['expires_in'] // 60} minutes)")
        print("═" * 60 + "\n")

        token_data = await _poll_for_token(
            session,
            client_id,
            device["device_code"],
            device["interval"],
            device["expires_in"],
        )

        if not token_data:
            raise RuntimeError("[Auth] Authorization failed or timed out.")

        _save_token(token_data, client_id)
        print("[Auth] Authorization successful!")
        return token_data["access_token"]


async def get_broadcaster_id(client_id: str, access_token: str, channel_name: str) -> str:
    """Resolve a channel login name to its Twitch user ID."""
    url = f"https://api.twitch.tv/helix/users?login={channel_name}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
    users = data.get("data", [])
    if not users:
        raise RuntimeError(f"[Auth] Could not find Twitch user '{channel_name}'")
    return users[0]["id"]


async def maybe_refresh(client_id: str) -> str | None:
    """Call periodically to keep the token fresh."""
    saved = _load_token()
    if not saved:
        return None
    if saved["expires_at"] - time.time() > 300:
        return None

    async with aiohttp.ClientSession() as session:
        refreshed = await _refresh_token(session, client_id, saved["refresh_token"])
        if refreshed:
            _save_token(refreshed, client_id)
            print("[Auth] Token refreshed proactively.")
            return refreshed["access_token"]
    return None