import asyncio
import json
import random
import websockets
import re
import aiohttp
from config import (
    TWITCH_CLIENT_ID, TWITCH_NICK, TWITCH_CHANNEL,
    CHANNEL_POINT_REWARD_TITLE,
    WS_HOST, WS_PORT
)
from auth import get_valid_token, maybe_refresh, get_broadcaster_id
from eventsub import run_eventsub

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
#  GAME DATA
# ──────────────────────────────────────────────

TYPES = [
    "Fire", "Water", "Grass", "Electric", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic",
    "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy", "Normal"
]

# Simplified type chart: (attacker_type, defender_type) -> multiplier
# 2.0 = super effective, 0.5 = not very effective, 0.0 = immune
TYPE_CHART: dict[tuple[str, str], float] = {
    ("Fire",     "Grass"):    2.0,
    ("Fire",     "Ice"):      2.0,
    ("Fire",     "Bug"):      2.0,
    ("Fire",     "Steel"):    2.0,
    ("Fire",     "Water"):    0.5,
    ("Fire",     "Fire"):     0.5,
    ("Fire",     "Rock"):     0.5,
    ("Fire",     "Dragon"):   0.5,

    ("Water",    "Fire"):     2.0,
    ("Water",    "Ground"):   2.0,
    ("Water",    "Rock"):     2.0,
    ("Water",    "Water"):    0.5,
    ("Water",    "Grass"):    0.5,
    ("Water",    "Dragon"):   0.5,

    ("Grass",    "Water"):    2.0,
    ("Grass",    "Ground"):   2.0,
    ("Grass",    "Rock"):     2.0,
    ("Grass",    "Fire"):     0.5,
    ("Grass",    "Grass"):    0.5,
    ("Grass",    "Poison"):   0.5,
    ("Grass",    "Flying"):   0.5,
    ("Grass",    "Bug"):      0.5,
    ("Grass",    "Dragon"):   0.5,
    ("Grass",    "Steel"):    0.5,

    ("Electric", "Water"):    2.0,
    ("Electric", "Flying"):   2.0,
    ("Electric", "Ground"):   0.0,
    ("Electric", "Grass"):    0.5,
    ("Electric", "Electric"): 0.5,
    ("Electric", "Dragon"):   0.5,

    ("Ice",      "Grass"):    2.0,
    ("Ice",      "Ground"):   2.0,
    ("Ice",      "Flying"):   2.0,
    ("Ice",      "Dragon"):   2.0,
    ("Ice",      "Fire"):     0.5,
    ("Ice",      "Water"):    0.5,
    ("Ice",      "Ice"):      0.5,
    ("Ice",      "Steel"):    0.5,

    ("Fighting", "Normal"):   2.0,
    ("Fighting", "Ice"):      2.0,
    ("Fighting", "Rock"):     2.0,
    ("Fighting", "Dark"):     2.0,
    ("Fighting", "Steel"):    2.0,
    ("Fighting", "Poison"):   0.5,
    ("Fighting", "Flying"):   0.5,
    ("Fighting", "Psychic"):  0.5,
    ("Fighting", "Bug"):      0.5,
    ("Fighting", "Fairy"):    0.5,
    ("Fighting", "Ghost"):    0.0,

    ("Poison",   "Grass"):    2.0,
    ("Poison",   "Fairy"):    2.0,
    ("Poison",   "Poison"):   0.5,
    ("Poison",   "Ground"):   0.5,
    ("Poison",   "Rock"):     0.5,
    ("Poison",   "Ghost"):    0.5,
    ("Poison",   "Steel"):    0.0,

    ("Ground",   "Fire"):     2.0,
    ("Ground",   "Electric"): 2.0,
    ("Ground",   "Poison"):   2.0,
    ("Ground",   "Rock"):     2.0,
    ("Ground",   "Steel"):    2.0,
    ("Ground",   "Grass"):    0.5,
    ("Ground",   "Bug"):      0.5,
    ("Ground",   "Flying"):   0.0,

    ("Flying",   "Grass"):    2.0,
    ("Flying",   "Fighting"): 2.0,
    ("Flying",   "Bug"):      2.0,
    ("Flying",   "Electric"): 0.5,
    ("Flying",   "Rock"):     0.5,
    ("Flying",   "Steel"):    0.5,

    ("Psychic",  "Fighting"): 2.0,
    ("Psychic",  "Poison"):   2.0,
    ("Psychic",  "Psychic"):  0.5,
    ("Psychic",  "Steel"):    0.5,
    ("Psychic",  "Dark"):     0.0,

    ("Bug",      "Grass"):    2.0,
    ("Bug",      "Psychic"): 2.0,
    ("Bug",      "Dark"):     2.0,
    ("Bug",      "Fire"):     0.5,
    ("Bug",      "Fighting"): 0.5,
    ("Bug",      "Flying"):   0.5,
    ("Bug",      "Ghost"):    0.5,
    ("Bug",      "Steel"):    0.5,
    ("Bug",      "Fairy"):    0.5,

    ("Rock",     "Fire"):     2.0,
    ("Rock",     "Ice"):      2.0,
    ("Rock",     "Flying"):   2.0,
    ("Rock",     "Bug"):      2.0,
    ("Rock",     "Fighting"): 0.5,
    ("Rock",     "Ground"):   0.5,
    ("Rock",     "Steel"):    0.5,

    ("Ghost",    "Psychic"):  2.0,
    ("Ghost",    "Ghost"):    2.0,
    ("Ghost",    "Normal"):   0.0,
    ("Ghost",    "Dark"):     0.5,

    ("Dragon",   "Dragon"):   2.0,
    ("Dragon",   "Steel"):    0.5,
    ("Dragon",   "Fairy"):    0.0,

    ("Dark",     "Psychic"):  2.0,
    ("Dark",     "Ghost"):    2.0,
    ("Dark",     "Fighting"): 0.5,
    ("Dark",     "Dark"):     0.5,
    ("Dark",     "Fairy"):    0.5,

    ("Steel",    "Ice"):      2.0,
    ("Steel",    "Rock"):     2.0,
    ("Steel",    "Fairy"):    2.0,
    ("Steel",    "Fire"):     0.5,
    ("Steel",    "Water"):    0.5,
    ("Steel",    "Electric"): 0.5,
    ("Steel",    "Steel"):    0.5,

    ("Fairy",    "Fighting"): 2.0,
    ("Fairy",    "Dragon"):   2.0,
    ("Fairy",    "Dark"):     2.0,
    ("Fairy",    "Fire"):     0.5,
    ("Fairy",    "Poison"):   0.5,
    ("Fairy",    "Steel"):    0.5,

    ("Normal",   "Rock"):     0.5,
    ("Normal",   "Steel"):    0.5,
    ("Normal",   "Ghost"):    0.0,
}

MOVE_POOL = [
    # name, type, base_power, description
    ("Inferno Punch",   "Fire",     80, "A scorching straight"),
    ("Ember Jab",       "Fire",     50, "A quick fiery jab"),
    ("Blaze Kick",      "Fire",     75, "Blazing roundhouse kick"),
    ("Heat Haymaker",   "Fire",     90, "Slow but fiery haymaker"),

    ("Aqua Slam",       "Water",    80, "A drenching body slam"),
    ("Tidal Hook",      "Water",    65, "Surging hook shot"),
    ("Whirlpool Spin",  "Water",    55, "Spinning water attack"),
    ("Hydro Uppercut",  "Water",    85, "Rising water uppercut"),

    ("Leaf Slash",      "Grass",    60, "Sharp leaf-edge strike"),
    ("Vine Whip",       "Grass",    45, "Quick vine lash"),
    ("Solar Smash",     "Grass",    90, "Powered-up solar blow"),
    ("Petal Barrage",   "Grass",    55, "Rapid petal flurry"),

    ("Thunder Cross",   "Electric", 85, "Electric cross punch"),
    ("Spark Jab",       "Electric", 50, "Zapping quick jab"),
    ("Volt Tackle",     "Electric", 95, "Reckless electric charge"),
    ("Static Stomp",    "Electric", 65, "Ground-shaking stomp"),

    ("Ice Fist",        "Ice",      75, "Frozen knuckle punch"),
    ("Frost Kick",      "Ice",      65, "Freezing kick"),
    ("Blizzard Rush",   "Ice",      85, "Icy charging assault"),
    ("Hail Hammer",     "Ice",      90, "Frozen overhead smash"),

    ("Mach Punch",      "Fighting", 40, "Ultra-fast jab"),
    ("Close Combat",    "Fighting", 95, "All-out fighting flurry"),
    ("Superpower",      "Fighting", 90, "Incredible strength hit"),
    ("Focus Blast",     "Fighting", 80, "Charged power punch"),

    ("Poison Jab",      "Poison",   80, "Toxic-tipped strike"),
    ("Sludge Bomb",     "Poison",   65, "Toxic goop thrown"),
    ("Venom Drip",      "Poison",   55, "Corrosive venom splash"),
    ("Toxic Fang",      "Poison",   70, "Venomous bite attack"),

    ("Earthquake",      "Ground",   95, "Ground-shaking stomp"),
    ("Mud Slam",        "Ground",   65, "Muddy heavy slam"),
    ("Sand Tomb",       "Ground",   55, "Trapping sand whirl"),
    ("Bulldoze",        "Ground",   75, "Heavy ground stomp"),

    ("Aerial Ace",      "Flying",   70, "Swift aerial strike"),
    ("Wing Smash",      "Flying",   85, "Powerful wing blow"),
    ("Gust Spin",       "Flying",   50, "Whirling gust attack"),
    ("Sky Uppercut",    "Flying",   80, "Leaping sky punch"),

    ("Psyblast",        "Psychic",  80, "Mental energy burst"),
    ("Mind Crush",      "Psychic",  90, "Telekinetic squeeze"),
    ("Zen Strike",      "Psychic",  70, "Focused psychic hit"),
    ("Future Sight",    "Psychic",  85, "Predicted strike"),

    ("Bug Bite",        "Bug",      60, "Sharp mandible bite"),
    ("Signal Beam",     "Bug",      75, "Confusing beam attack"),
    ("X-Scissor",       "Bug",      80, "Cross cutting strike"),
    ("Megahorn",        "Bug",      85, "Massive horn stab"),

    ("Rock Slide",      "Rock",     75, "Raining rock barrage"),
    ("Stone Edge",      "Rock",     90, "Sharp stone pierce"),
    ("Rock Blast",      "Rock",     65, "Multiple rock shots"),
    ("Power Gem",       "Rock",     80, "Gem-powered strike"),

    ("Shadow Ball",     "Ghost",    80, "Dark energy sphere"),
    ("Phantom Force",   "Ghost",    90, "Ghostly dive attack"),
    ("Hex",             "Ghost",    65, "Cursed ghostly strike"),
    ("Shadow Punch",    "Ghost",    70, "Invisible ghost punch"),

    ("Dragon Claw",     "Dragon",   80, "Fierce dragon swipe"),
    ("Outrage",         "Dragon",   95, "Rampaging dragon fury"),
    ("Dragon Rush",     "Dragon",   85, "Charging dragon blow"),
    ("Draco Meteor",    "Dragon",   90, "Meteor-powered strike"),

    ("Crunch",          "Dark",     80, "Crushing dark bite"),
    ("Night Slash",     "Dark",     70, "Shadowy blade slash"),
    ("Sucker Punch",    "Dark",     65, "Surprise dark strike"),
    ("Foul Play",       "Dark",     85, "Uses foe's strength"),

    ("Iron Head",       "Steel",    80, "Steel-hard headbutt"),
    ("Flash Cannon",    "Steel",    80, "Steel energy beam"),
    ("Meteor Mash",     "Steel",    90, "Meteor-speed punch"),
    ("Gyro Ball",       "Steel",    75, "Spinning steel orb"),

    ("Moonblast",       "Fairy",    85, "Moonlight energy beam"),
    ("Play Rough",      "Fairy",    90, "Ferocious fairy tackle"),
    ("Dazzling Gleam",  "Fairy",    75, "Blinding fairy flash"),
    ("Fairy Wind",      "Fairy",    45, "Gentle fairy gust"),

    ("Body Slam",       "Normal",   85, "Full weight body drop"),
    ("Hyper Beam",      "Normal",   90, "Powerful energy beam"),
    ("Quick Attack",    "Normal",   40, "Blindingly fast strike"),
    ("Double-Edge",     "Normal",   95, "Reckless full charge"),
]

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
    move_type  = move[1]
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
                "fighter1": {**self.fighter1.to_dict(), "move_used": self.fighter1.choice, "damage_dealt": dmg1, "effectiveness": multi1},
                "fighter2": {**self.fighter2.to_dict(), "move_used": self.fighter2.choice, "damage_dealt": dmg2, "effectiveness": multi2},
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
    message  = message.strip()

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
                    PONG_TIMEOUT  = 10
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