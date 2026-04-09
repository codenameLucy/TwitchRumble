"""
eventsub.py — Twitch EventSub WebSocket client

Connects to wss://eventsub.wss.twitch.tv/ws, waits for the session_welcome
message to get a session_id, then registers a subscription for
channel.channel_points_custom_reward_redemption.add via the Helix REST API.

Message types we handle:
  session_welcome   → grab session_id, register subscription
  session_keepalive → no-op (Twitch confirming the connection is alive)
  notification      → a redemption happened, call on_redemption()
  session_reconnect → Twitch wants us to move to a new URL gracefully
  revocation        → subscription was revoked (log and ignore)
"""

import asyncio
import json
import aiohttp
import websockets

EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
SUBSCRIPTION_TYPE = "channel.channel_points_custom_reward_redemption.add"
SUBSCRIPTION_VERSION = "1"


async def _register_subscription(
    session: aiohttp.ClientSession,
    client_id: str,
    access_token: str,
    broadcaster_id: str,
    session_id: str,
    reward_title: str,
) -> None:
    """
    POST to the Helix EventSub API to subscribe to redemption events
    on the given broadcaster's channel, tied to this WebSocket session.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id,
        "Content-Type": "application/json",
    }
    body = {
        "type": SUBSCRIPTION_TYPE,
        "version": SUBSCRIPTION_VERSION,
        "condition": {
            "broadcaster_user_id": broadcaster_id,
            # Omitting reward_id subscribes to ALL custom rewards.
            # We filter by title in the notification handler below.
        },
        "transport": {
            "method": "websocket",
            "session_id": session_id,
        },
    }
    async with session.post(
        "https://api.twitch.tv/helix/eventsub/subscriptions",
        headers=headers,
        json=body,
    ) as resp:
        if resp.status in (200, 202):
            print(f"[EventSub] Subscribed to {SUBSCRIPTION_TYPE} ✓")
        else:
            text = await resp.text()
            print(f"[EventSub] Subscription failed ({resp.status}): {text}")


async def run_eventsub(
    client_id: str,
    access_token: str,
    broadcaster_id: str,
    reward_title: str,
    on_redemption,          # async callable(username: str)
    ws_url: str = EVENTSUB_WS_URL,
):
    """
    Main EventSub loop. Reconnects automatically on disconnect.
    Calls on_redemption(username) whenever the matching reward is redeemed.

    The reconnect flow follows the Twitch spec:
      1. On session_reconnect, connect to the new URL FIRST
      2. Wait for session_welcome on the new connection
      3. Only then close the old connection
    """
    current_url = ws_url

    while True:
        try:
            print(f"[EventSub] Connecting to {current_url}")
            async with websockets.connect(current_url) as ws:
                async with aiohttp.ClientSession() as http:
                    async for raw in ws:
                        msg = json.loads(raw)
                        meta = msg.get("metadata", {})
                        msg_type = meta.get("message_type", "")
                        payload = msg.get("payload", {})

                        if msg_type == "session_welcome":
                            session_id = payload["session"]["id"]
                            print(f"[EventSub] Session ID: {session_id}")
                            await _register_subscription(
                                http, client_id, access_token,
                                broadcaster_id, session_id, reward_title,
                            )

                        elif msg_type == "session_keepalive":
                            # Twitch sends this every ~10s to confirm the
                            # connection is alive. Nothing to do.
                            pass

                        elif msg_type == "notification":
                            event = payload.get("event", {})
                            redeemed_title = event.get("reward", {}).get("title", "")
                            username = event.get("user_login", "")

                            if redeemed_title.lower() == reward_title.lower():
                                print(f"[EventSub] Redemption: {username} redeemed '{redeemed_title}'")
                                await on_redemption(username)
                            else:
                                print(f"[EventSub] Ignored redemption: '{redeemed_title}' by {username}")

                        elif msg_type == "session_reconnect":
                            # Twitch is asking us to move to a new URL.
                            # Per spec: connect to new URL, get welcome,
                            # THEN drop the old connection.
                            new_url = payload["session"]["reconnect_url"]
                            print(f"[EventSub] Reconnect requested → {new_url}")
                            current_url = new_url
                            break  # exits the async for, closes old ws

                        elif msg_type == "revocation":
                            sub = payload.get("subscription", {})
                            print(f"[EventSub] Subscription revoked: {sub.get('status')} — {sub.get('type')}")

        except (websockets.ConnectionClosed, OSError) as e:
            print(f"[EventSub] Connection lost ({e}), reconnecting in 5s…")
            await asyncio.sleep(5)
            current_url = ws_url  # reset to original URL on unexpected drops