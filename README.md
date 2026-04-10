# 🥊 Twitch Boxing Ring

A Pokémon-style fight overlay for Twitch streams where chatters battle via channel point redeems.

---

## Setup

### 1. Download the latest release

Go to the [Releases](../../releases) page and download the latest `twitchrumble-vX.X.X.zip`. Extract it anywhere you like.

### 2. Create your Channel Point Reward

On Twitch Dashboard → Channel Points → Manage Rewards:
- Create a reward with the **exact same title** as `channel_point_reward_title` in your `config.json`

### 3. Configure `config.json`

In configs, copy `config.template.json` and rename the copy to `config.json`. Open it in any text editor and fill in your values:

| Setting | Description |
|---|---|
| `twitch_client_id` | Your app's Client ID from https://dev.twitch.tv/console/apps |
| `twitch_nick` | The Twitch account username you'll authorize as |
| `twitch_channel` | Your channel name (lowercase) |
| `channel_point_reward_title` | Exact title of your channel point reward |
| `ws_host` | Leave as `localhost` unless you know what you are doing |
| `ws_port` | Leave as `8765` unless you know what you are doing |

> **Registering your app:** Go to https://dev.twitch.tv/console/apps → Register Your Application.  
> Set the OAuth Redirect URL to `https://localhost:3000`. No client secret needed.
> once your app is registered, click on manage to see the client id

### 4. Add the overlay to OBS

- Add a **Browser Source**
- Check **Local File** and inside the folder you have extracted, browse to `web/overlay.html`
- Set width to **1920** and height to **1080**
- Enable **Shutdown source when not visible** (optional)

### 5. Run the bot

Double-click `main.exe` to start the bot.

On first run, it will print a Twitch URL and a short code in the terminal. Open the URL in your browser, enter the code, and click **Authorize**. The token is saved automatically and refreshed on future runs — you only do this once.

Closing `main.exe` will turn off the program. Once your stream is done and you no longer want the overlay to work you can safely close it by pressing the x button or by pressing ctrl+c

---

## How it works

1. Two chatters each redeem the channel point reward
2. They are assigned a random **Pokémon type** and **4 random moves**
3. Each gets **30-50 HP** randomly
4. Each round, a timer (10s) counts down in the overlay
5. Chatters type **1, 2, 3, or 4** in chat to choose their move
6. If no input is given, a move is **auto-selected randomly**
7. Both moves resolve simultaneously — damage is calculated with type effectiveness

## Type effectiveness

- Super effective (×2.0): Bold announcement on overlay
- Not very effective (×0.5): Noted in overlay
- Immune (×0.0): "It had no effect!"

---

## Customization

### `configs/movepool.json` — Adding and removing moves

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
| `type` | Must match a type that exists in `typechart.json` |
| `power` | Base damage (roughly 40–95 is the intended range) |
| `desc` | Short flavour text shown on the overlay |

To **add a move**, append a new object to the `moves` array following the format above.  
To **remove a move**, delete its object from the array.  
You need a minimum of 4 moves in the pool for the fight engine to work.

> **Tip:** You can create entirely custom types (e.g. `"Cosmic"` or `"Shadow"`) by using a new type name in both a move and a matchup entry. The type list is derived automatically.

---

### `configs/typechart.json` — Editing type matchups

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

To **add a completely new type**, add matchup entries that reference it — the type will automatically appear as a possible fighter type once it exists in the chart.

---

## File overview

| File | Purpose |
|---|---|
| `main.exe` | The bot — run this to start |
| `configs/config.template.json` | Copy this to `config.json` and fill in your settings |
| `configs/config.json` | Your personal settings (you create this from the template) |
| `configs/typechart.json` | Type effectiveness matchups — edit to customise damage |
| `configs/movepool.json` | All available moves — add or remove freely |
| `web/overlay.html` | OBS browser source |
| `web/overlay.css` | Overlay styles and animations |
| `web/overlay.js` | Overlay WebSocket logic and event handling |

---
---

## Developer notes

### Running from source

Requires Python 3.14+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
uv run rumble/main.py
```

### Project structure

| File | Purpose |
|---|---|
| `rumble/main.py` | Twitch IRC bot + fight engine + WebSocket server |
| `rumble/auth.py` | Twitch Device Code OAuth flow + token refresh |
| `rumble/eventsub.py` | Twitch EventSub WebSocket client for redemption events |
| `configs/config.template.json` | Committed template — copy to `config.json` to run locally |
| `configs/typechart.json` | Type effectiveness matchups |
| `configs/movepool.json` | All available moves |
| `web/overlay.html` | OBS browser source — markup only |
| `web/overlay.css` | Overlay styles and animations |
| `web/overlay.js` | Overlay WebSocket logic and event handling |
| `main.spec` | PyInstaller build spec |
| `pyproject.toml` | Project metadata and dependencies |

### Building the exe locally

```bash
uv run pyinstaller main.spec
cp configs dist/main/configs -r
cp web dist/main/web -r
./dist/main/main
```

### Config in development

`configs/config.json` is gitignored. Copy `configs/config.template.json` to `configs/config.json` and fill in your own values. Your local config will never be committed.

### Running tests

```bash
python tests/test_fight.py --fighters "StreamerA" "StreamerB"
```

Arguments and usage are documented in the test file itself.

### Releases

Releases are created automatically by the GitHub Actions workflow when a new tag is pushed:

```bash
git tag v1.0.0
git push origin v1.0.0
```
