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
On Twitch Dashboard → Channel Points → Manage Rewards:
- Create a reward with the **exact same title** as `CHANNEL_POINT_REWARD_TITLE` in config.py
- Recommended: limit to 1 redemption per user per stream

### 4. Add the overlay to OBS
- Add a **Browser Source**
- Check **Local File** and browse to `overlay.html`
- Set width to **1920** and height to **1080**
- Enable **Shutdown source when not visible** (optional)

### 5. Run the bot
```bash
python main.py
```

---

## How it works

1. Two chatters each redeem the channel point reward
2. They are assigned a random **Pokémon type** and **4 random moves**
3. Each gets **70–100 HP** randomly
4. Each round, a timer (15–25s) counts down in the overlay
5. Chatters type **1, 2, 3, or 4** in chat to choose their move
6. If no input is given, a move is **auto-selected randomly**
7. Both moves resolve simultaneously — damage is calculated with type effectiveness
8. Fight continues until one fighter reaches 0 HP

## Type effectiveness
- Super effective (×2.0): Bold announcement on overlay
- Not very effective (×0.5): Noted in overlay
- Immune (×0.0): "It had no effect!"

---

## File overview

| File | Purpose |
|---|---|
| `main.py` | Twitch IRC bot + fight engine + WebSocket server |
| `auth.py` | Twitch Device Code OAuth flow + token refresh |
| `config.py` | All your settings live here |
| `overlay.html` | OBS browser source overlay |
| `requirements.txt` | Python dependencies |
| `twitch_token.json` | Auto-created on first run, stores your token |
