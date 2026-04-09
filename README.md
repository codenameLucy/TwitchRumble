# 🥊 Twitch Boxing Ring

A Pokémon-style fight overlay for Twitch streams where chatters battle via channel point redeems.

---

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure `config.py`
Edit these values:

| Setting | Description |
|---|---|
| `TWITCH_CLIENT_ID` | Your app's Client ID from https://dev.twitch.tv/console/apps |
| `TWITCH_NICK` | The Twitch account username you'll authorize as |
| `TWITCH_CHANNEL` | Your channel name (lowercase) |
| `CHANNEL_POINT_REWARD_TITLE` | Exact title of your channel point reward |

> **Registering your app:** Go to https://dev.twitch.tv/console/apps → Register Your Application.  
> Set the OAuth Redirect URL to `http://localhost:3000`. No client secret needed.

### 3. First-time authorization
On first run, the bot will print a Twitch URL and a short code in the terminal.  
Open the URL in your browser, enter the code, and click **Authorize**.  
The token is saved to `twitch_token.json` and auto-refreshed on future runs — you only do this once.

### 4. Create your Channel Point Reward
On Twitch Dashboard → Channel Points → Manage Rewards:
- Create a reward with the **exact same title** as `CHANNEL_POINT_REWARD_TITLE` in `config.py`
- Recommended: limit to 1 redemption per user per stream

### 5. Add the overlay to OBS
- Add a **Browser Source**
- Check **Local File** and browse to `overlay.html`
- Set width to **1920** and height to **1080**
- Make sure `overlay.html`, `overlay.css`, and `overlay.js` are all in the **same folder**
- Enable **Shutdown source when not visible** (optional)

### 6. Run the bot
```bash
python main.py
```

---

## How it works

1. Two chatters each redeem the channel point reward
2. They are assigned a random **Pokémon type** and **4 random moves**
3. Each gets **30-50 HP** randomly
4. Each round, a timer (10s) counts down in the overlay
5. Chatters type **1, 2, 3, or 4** in chat to choose their move
6. If no input is given, a move is **auto-selected randomly**
7. Both moves resolve simultaneously — damage is calculated with type effectiveness
8. Fight continues until one or both fighter(s) reaches 0 HP

## Type effectiveness
- Super effective (×2.0): Bold announcement on overlay
- Not very effective (×0.5): Noted in overlay
- Immune (×0.0): "It had no effect!"

---

## Customization

### `move_pool.json` — Adding and removing moves

Each move is a JSON object in the `moves` array:

```json
{
  "name": "Inferno Punch",
  "type": "Fire",
  "power": 80,
  "desc": "A scorching straight"
}
```

| Field | Description |
|---|---|
| `name` | Display name shown on the overlay |
| `type` | Must match a type that exists in `type_chart.json` |
| `power` | Base damage (roughly 40–95 is the intended range) |
| `desc` | Short flavour text shown on the overlay |

To **add a move**, append a new object to the `moves` array following the format above.  
To **remove a move**, delete its object from the array.  
You need a minimum of 4 moves in the pool for the fight engine to work.

The `type` field determines type effectiveness — a move with `"type": "Fire"` will deal double damage against a fighter whose assigned type is weak to Fire, based on the matchups in `type_chart.json`.

> **Tip:** You can create entirely custom types (e.g. `"Cosmic"` or `"Shadow"`) by using a new type name in both a move and a matchup entry. The type list is derived automatically — no Python edits needed.

---

### `type_chart.json` — Editing type matchups

Each matchup is a 3-element array in the `matchups` array:

```json
["Fire", "Grass", 2.0]
```

The three values are `[attacker_type, defender_type, multiplier]`.

| Multiplier | Meaning | Shown on overlay as |
|---|---|---|
| `2.0` | Super effective | "⚡ SUPER EFFECTIVE!" |
| `0.5` | Not very effective | "Not very effective…" |
| `0.0` | Immune (no damage) | "It had no effect!" |

Any type pair **not listed** defaults to `1.0` (normal damage) — you only need to add entries for non-standard matchups.

To **add a matchup**, append a new entry to the `matchups` array:
```json
["Shadow", "Psychic", 2.0]
```

To **remove a matchup**, delete its entry. That pair will then deal normal (×1.0) damage.

To **add a completely new type**, add matchup entries that reference it — the type will automatically appear as a possible fighter type once it exists in the chart.

---

## File overview

| File | Purpose |
|---|---|
| `main.py` | Twitch IRC bot + fight engine + WebSocket server |
| `auth.py` | Twitch Device Code OAuth flow + token refresh |
| `eventsub.py` | Twitch EventSub WebSocket client for redemption events |
| `config.py` | All your settings live here |
| `type_chart.json` | Type effectiveness matchups — edit to customise damage |
| `move_pool.json` | All available moves — add or remove freely |
| `overlay.html` | OBS browser source — markup only |
| `overlay.css` | Overlay styles and animations |
| `overlay.js` | Overlay WebSocket logic and event handling |
| `requirements.txt` | Python dependencies |
| `twitch_token.json` | Auto-created on first run, stores your OAuth token |

## Testing

the test script can be run using the following command:
```shell
    python test_fight.py --fighters "StreamerA" "StreamerB"
```

the args and how to use is documented in the file itself.