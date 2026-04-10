import asyncio
import json
import os
import random
import re
import sys

import aiohttp
import websockets

from rumble.auth import get_valid_token, maybe_refresh, get_broadcaster_id
from rumble.eventsub import run_eventsub

if getattr(sys, 'frozen', False):
    _configs = os.path.join(os.path.dirname(sys.executable), "configs")
else:
    _configs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../configs")

with open(os.path.join(_configs, "config.json"), encoding="utf-8") as _f:
    _cfg = json.load(_f)

TWITCH_CLIENT_ID = _cfg["twitch_client_id"]
TWITCH_NICK = _cfg["twitch_nick"]
TWITCH_CHANNEL = _cfg["twitch_channel"]
CHANNEL_POINT_REWARD_TITLE = _cfg["channel_point_reward_title"]
WS_HOST = _cfg["ws_host"]
WS_PORT = _cfg["ws_port"]

# Set by main() after auth, used by fetch_avatars
_api_token: str = ""


async def fetch_avatars(*usernames: str) -> dict[str, str]:
    """
    Fetch Twitch profile picture URLs for one or more usernames.
    Returns {username_lower: profile_image_url}.
    Falls back to empty string if a user isn't found.
    """
    if not usernames or not _api_token:
        return {u: "" for u in usernames}
    query = "&".join(f"login={u}" for u in usernames)
    url = f"https://api.twitch.tv/helix/users?{query}"
    headers = {
        "Authorization": f"Bearer {_api_token}",
        "Client-Id": TWITCH_CLIENT_ID,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
        return {u["login"]: u["profile_image_url"] for u in data.get("data", [])}
    except Exception as e:
        print(f"[API] Failed to fetch avatars: {e}")
        return {u: "" for u in usernames}


# ──────────────────────────────────────────────
#  GAME DATA — loaded from JSON files at startup
# ──────────────────────────────────────────────


def _load_type_chart(path: str) -> dict[tuple[str, str], float]:
    """
    Load type matchups from typechart.json.
    Each matchup is [attacker, defender, multiplier].
    Returns a dict keyed by (attacker, defender) tuples.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    chart = {}
    for entry in data.get("matchups", []):
        if len(entry) != 3:
            raise ValueError(f"Bad matchup entry {entry!r} — expected [attacker, defender, multiplier]")
        attacker, defender, multiplier = entry
        chart[(str(attacker), str(defender))] = float(multiplier)
    return chart


def _load_move_pool(path: str) -> list[tuple]:
    """
    Load moves from movepool.json.
    Returns a list of (name, type, power, desc) tuples.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pool = []
    for m in data.get("moves", []):
        missing = [k for k in ("name", "type", "power", "desc") if k not in m]
        if missing:
            raise ValueError(f"Move {m.get('name', '?')!r} is missing fields: {missing}")
        pool.append((m["name"], m["type"], int(m["power"]), m["desc"]))
    return pool


def _derive_types(chart: dict[tuple[str, str], float]) -> list[str]:
    """Derive the full set of type names from all attacker/defender names in the chart."""
    types: set[str] = set()
    for attacker, defender in chart:
        types.add(attacker)
        types.add(defender)
    return sorted(types)


try:
    TYPE_CHART = _load_type_chart(os.path.join(_configs, "typechart.json"))
    MOVE_POOL = _load_move_pool(os.path.join(_configs, "movepool.json"))
    TYPES = _derive_types(TYPE_CHART)
    print(f"[Data] Loaded {len(TYPES)} types, {len(TYPE_CHART)} matchups, {len(MOVE_POOL)} moves.")
except FileNotFoundError as e:
    sys.exit(
        f"[Data] Missing data file: {e}\nMake sure typechart.json and movepool.json are in the same folder as main.py.")
except (KeyError, ValueError, json.JSONDecodeError) as e:
    sys.exit(f"[Data] Malformed data file: {e}")

if len(MOVE_POOL) < 4:
    sys.exit("[Data] movepool.json must contain at least 4 moves to run a fight.")


# ──────────────────────────────────────────────
#  FIGHTER CLASS
# ──────────────────────────────────────────────

class Fighter:
    def __init__(self, name: str):
        self.name = name
        self.type = random.choice(TYPES)
        self.hp = random.randint(30, 50)
        self.max_hp = self.hp
        self.moves = self._pick_moves()
        self.choice: int | None = None  # 0-3 index

    def _pick_moves(self) -> list[tuple]:
        return random.sample(MOVE_POOL, 4)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "moves": [
                {"name": m[0], "type": m[1], "power": m[2], "desc": m[3]}
                for m in self.moves
            ],
        }


def calc_damage(attacker: Fighter, move_idx: int, defender: Fighter) -> tuple[int, float]:
    """Returns (damage, effectiveness_multiplier)."""
    move = attacker.moves[move_idx]
    base_power = move[2]
    move_type = move[1]
    multi = TYPE_CHART.get((move_type, defender.type), 1.0)
    # Random variance ±10%
    variance = random.uniform(0.9, 1.1)
    damage = max(1, int(base_power * multi * variance / 10))
    return damage, multi


# ──────────────────────────────────────────────
#  WEBSOCKET BROADCAST
# ──────────────────────────────────────────────

connected_clients: set = set()


async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)


async def broadcast(msg: dict):
    if connected_clients:
        data = json.dumps(msg)
        await asyncio.gather(*[c.send(data) for c in connected_clients], return_exceptions=True)


# ──────────────────────────────────────────────
#  FIGHT ENGINE
# ──────────────────────────────────────────────

class FightEngine:
    def __init__(self):
        self.queue: list[str] = []
        self.active = False
        self.fighter1: Fighter | None = None
        self.fighter2: Fighter | None = None
        self.round = 0

    def join(self, username: str) -> bool:
        if username in self.queue or self.active:
            return False
        if len(self.queue) < 2:
            self.queue.append(username)
            return True
        return False

    async def start_fight(self):
        self.active = True
        self.round = 0
        self.fighter1 = Fighter(self.queue[0])
        self.fighter2 = Fighter(self.queue[1])
        self.queue.clear()

        # Fetch both avatars concurrently
        avatars = await fetch_avatars(self.fighter1.name, self.fighter2.name)

        await broadcast({
            "event": "fight_start",
            "fighter1": {**self.fighter1.to_dict(), "avatar": avatars.get(self.fighter1.name, "")},
            "fighter2": {**self.fighter2.to_dict(), "avatar": avatars.get(self.fighter2.name, "")},
        })

        await asyncio.sleep(3)
        await self.run_rounds()

    async def run_rounds(self):
        while self.fighter1.hp > 0 and self.fighter2.hp > 0:
            self.round += 1
            self.fighter1.choice = None
            self.fighter2.choice = None

            timer = 10  # seconds to choose
            await broadcast({
                "event": "round_start",
                "round": self.round,
                "timer": timer,
                "fighter1": self.fighter1.to_dict(),
                "fighter2": self.fighter2.to_dict(),
            })

            await asyncio.sleep(timer)

            # Auto-select if no choice made
            if self.fighter1.choice is None:
                self.fighter1.choice = random.randint(0, 3)
            if self.fighter2.choice is None:
                self.fighter2.choice = random.randint(0, 3)

            # Both attack simultaneously
            dmg1, multi1 = calc_damage(self.fighter1, self.fighter1.choice, self.fighter2)
            dmg2, multi2 = calc_damage(self.fighter2, self.fighter2.choice, self.fighter1)

            self.fighter2.hp = max(0, self.fighter2.hp - dmg1)
            self.fighter1.hp = max(0, self.fighter1.hp - dmg2)

            await broadcast({
                "event": "round_result",
                "round": self.round,
                "fighter1": {**self.fighter1.to_dict(), "move_used": self.fighter1.choice, "damage_dealt": dmg1,
                             "effectiveness": multi1},
                "fighter2": {**self.fighter2.to_dict(), "move_used": self.fighter2.choice, "damage_dealt": dmg2,
                             "effectiveness": multi2},
            })

            await asyncio.sleep(4)

        # Determine winner
        if self.fighter1.hp <= 0 and self.fighter2.hp <= 0:
            winner = None
        elif self.fighter1.hp <= 0:
            winner = self.fighter2.name
        else:
            winner = self.fighter1.name

        await broadcast({
            "event": "fight_end",
            "winner": winner,
            "fighter1": self.fighter1.to_dict(),
            "fighter2": self.fighter2.to_dict(),
        })

        await asyncio.sleep(8)
        self.active = False
        self.fighter1 = None
        self.fighter2 = None

    def set_choice(self, username: str, choice: int):
        """Called from IRC when a chatter types 1-4."""
        if self.fighter1 and self.fighter1.name == username and self.fighter1.choice is None:
            self.fighter1.choice = choice
        elif self.fighter2 and self.fighter2.name == username and self.fighter2.choice is None:
            self.fighter2.choice = choice


fight_engine = FightEngine()


# ──────────────────────────────────────────────
#  TWITCH IRC
# ──────────────────────────────────────────────

async def handle_line(line: str, chat):
    # PING/PONG keepalive
    if line.startswith("PING"):
        # PONG is handled in twitch_irc loop directly; nothing to do here
        return

    # Parse PRIVMSG
    msg_match = re.match(r"@([^ ]+) :([^!]+)!.+ PRIVMSG #\S+ :(.+)", line)
    if not msg_match:
        return

    tags_raw, username, message = msg_match.groups()
    username = username.lower()
    message = message.strip()

    # ── Move selection (1–4) during active fight ──
    # Redemption joining is handled by EventSub, not IRC.
    if fight_engine.active and message in ("1", "2", "3", "4"):
        fight_engine.set_choice(username, int(message) - 1)


# ──────────────────────────────────────────────
#  EVENTSUB REDEMPTION CALLBACK
# ──────────────────────────────────────────────

# irc_chat_fn is set by main() so on_redemption can send chat messages
_irc_chat = None


async def on_redemption(username: str):
    """Called by EventSub when the configured reward is redeemed."""
    if fight_engine.active:
        if _irc_chat:
            await _irc_chat(f"@{username} A fight is already in progress! Wait for the next one.")
        return
    if len(fight_engine.queue) >= 2:
        if _irc_chat:
            await _irc_chat(f"@{username} The ring is full! Wait for the current fight to finish.")
        return

    joined = fight_engine.join(username)
    if joined:
        count = len(fight_engine.queue)
        await broadcast({"event": "queue_update", "queue": fight_engine.queue.copy()})
        if _irc_chat:
            await _irc_chat(f"@{username} entered the ring! ({count}/2)")
        if count == 2:
            if _irc_chat:
                await _irc_chat(
                    f"🥊 Both fighters ready! {fight_engine.queue[0]} vs {fight_engine.queue[1]} — FIGHT!"
                )
            asyncio.create_task(fight_engine.start_fight())


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

async def token_refresh_loop():
    """Proactively refresh the token every 30 minutes if needed."""
    while True:
        await asyncio.sleep(30 * 60)
        await maybe_refresh(TWITCH_CLIENT_ID)


async def main():
    global _irc_chat, _api_token

    # ── Auth ──
    token = await get_valid_token(TWITCH_CLIENT_ID)
    _api_token = token

    # Resolve channel name → numeric broadcaster ID (required by EventSub API)
    broadcaster_id = await get_broadcaster_id(TWITCH_CLIENT_ID, token, TWITCH_CHANNEL)
    print(f"[Main] Broadcaster ID for '{TWITCH_CHANNEL}': {broadcaster_id}")

    # ── Overlay WebSocket server ──
    print(f"[WS] Starting WebSocket server on ws://{WS_HOST}:{WS_PORT}")
    ws_server = await websockets.serve(ws_handler, WS_HOST, WS_PORT)

    # ── IRC (for move inputs only) ──
    # We start it as a task so we can grab the chat function via a shared ref.
    # The chat callable is captured inside twitch_irc and exposed via _irc_chat
    # after IRC connects.
    irc_ready = asyncio.Event()

    async def irc_with_chat_ref():
        global _irc_chat
        host = "irc.chat.twitch.tv"
        # Docs specify SSL on port 6697 for IRC clients.
        # Port 6667 (plain TCP) is legacy and being decommissioned.
        port = 6697
        retry_delay = 5

        while True:
            writer = None
            try:
                import ssl
                ssl_ctx = ssl.create_default_context()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, ssl=ssl_ctx),
                    timeout=10
                )

                def send(msg: str):
                    writer.write((msg + "\r\n").encode())

                # ── Auth sequence (order matters per docs) ──
                # 1. CAP REQ must come before PASS/NICK per IRCv3 spec
                # 2. tags capability requires commands to also be requested
                # 3. PASS then NICK for authentication
                send("CAP REQ :twitch.tv/commands twitch.tv/tags")
                send(f"PASS oauth:{token}")
                send(f"NICK {TWITCH_NICK}")
                await writer.drain()

                # JOIN is sent after we confirm auth succeeded (in read_loop below)

                async def chat(msg: str):
                    try:
                        send(f"PRIVMSG #{TWITCH_CHANNEL} :{msg}")
                        await writer.drain()
                    except Exception as e:
                        print(f"[IRC] Failed to send chat message: {e}")

                pong_event = asyncio.Event()
                auth_ok = False

                async def ping_loop():
                    """
                    Send a PING every 30s and wait up to 10s for a PONG.
                    Per docs, the PONG text must match our PING text exactly.
                    If no PONG arrives, close writer to trigger reconnect.
                    """
                    PING_INTERVAL = 30
                    PONG_TIMEOUT = 10
                    while True:
                        await asyncio.sleep(PING_INTERVAL)
                        pong_event.clear()
                        send("PING :tmi.twitch.tv")
                        await writer.drain()
                        try:
                            await asyncio.wait_for(pong_event.wait(), timeout=PONG_TIMEOUT)
                        except asyncio.TimeoutError:
                            print("[IRC] No PONG received, connection stale — reconnecting.")
                            writer.close()
                            return

                async def read_loop():
                    nonlocal auth_ok
                    buffer = ""
                    while True:
                        data = await reader.read(4096)
                        if not data:
                            print("[IRC] Connection closed by server.")
                            return
                        buffer += data.decode("utf-8", errors="ignore")
                        while "\r\n" in buffer:
                            line, buffer = buffer.split("\r\n", 1)

                            # ── Server-initiated PING: echo text back exactly ──
                            if line.startswith("PING"):
                                ping_text = line.split(" ", 1)[1] if " " in line else ":tmi.twitch.tv"
                                send(f"PONG {ping_text}")
                                await writer.drain()
                                continue

                            # ── PONG response to our proactive PING ──
                            if "PONG" in line:
                                pong_event.set()
                                continue

                            # ── Auth failure detection ──
                            if "Login authentication failed" in line or "Improperly formatted auth" in line:
                                print(f"[IRC] Authentication failed: {line}")
                                writer.close()
                                return

                            # ── Successful auth: server sends 001 Welcome ──
                            # Join the channel only after auth is confirmed.
                            if not auth_ok and " 001 " in line:
                                auth_ok = True
                                send(f"JOIN #{TWITCH_CHANNEL}")
                                await writer.drain()
                                _irc_chat = chat
                                irc_ready.set()
                                print(f"[IRC] Authenticated and joined #{TWITCH_CHANNEL}")

                            # ── RECONNECT: server wants us to reconnect gracefully ──
                            if "RECONNECT" in line:
                                print("[IRC] Server requested RECONNECT — reconnecting.")
                                writer.close()
                                return

                            await handle_line(line, chat)

                nonlocal_retry = retry_delay  # capture for reset after success
                await asyncio.gather(read_loop(), ping_loop())
                retry_delay = 5  # reset backoff only after a clean session

            except asyncio.TimeoutError:
                print("[IRC] Connection timed out.")
            except OSError as e:
                print(f"[IRC] Connection error: {e}")
            except Exception as e:
                print(f"[IRC] Unexpected error: {e}")
            finally:
                _irc_chat = None  # disable chat while disconnected
                if writer:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass

            print(f"[IRC] Reconnecting in {retry_delay}s…")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

    print("[IRC] Connecting to Twitch...")
    await asyncio.gather(
        ws_server.wait_closed(),
        irc_with_chat_ref(),
        run_eventsub(TWITCH_CLIENT_ID, token, broadcaster_id, CHANNEL_POINT_REWARD_TITLE, on_redemption),
        token_refresh_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
