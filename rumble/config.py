# ──────────────────────────────────────────────
#  TWITCH BOXING RING — CONFIGURATION
#  Edit these values before running main.py
# ──────────────────────────────────────────────

# Your Twitch application's Client ID.
# Register your app at: https://dev.twitch.tv/console/apps
# Set the OAuth Redirect URL to: https://localhost:3000
# No client secret is needed — we use the Device Code flow.
TWITCH_CLIENT_ID = ""

# The Twitch username of your bot account (or your own account).
# This must match the account that authorizes via the browser.
TWITCH_NICK = ""

# Your Twitch channel name (lowercase).
TWITCH_CHANNEL = ""

# The EXACT title of the channel point reward chatters redeem to join the ring.
# Must match your reward title on the Twitch Dashboard exactly.
CHANNEL_POINT_REWARD_TITLE = "Join the Boxing Ring"

# WebSocket server settings (used to talk to the HTML overlay).
WS_HOST = "localhost"
WS_PORT = 8765
