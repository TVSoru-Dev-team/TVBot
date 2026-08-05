"""Configuration loading and validation (.env).

Validation happens at startup rather than discovering a missing variable the
moment a viewer runs a command.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Missing environment variable: {name}. "
            "See .env.example and the README for the setup procedure."
        )
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


# --- Twitch ---
# Register the application at https://dev.twitch.tv/console/apps with
# http://localhost:4343/oauth/callback as the OAuth Redirect URL.
TWITCH_CLIENT_ID = _required("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = _required("TWITCH_CLIENT_SECRET")
# twitchio 3 works with numeric user IDs, no longer with logins.
BOT_ID = _required("TWITCH_BOT_ID")
OWNER_ID = _required("TWITCH_OWNER_ID")

# --- Wheel of Names ---
WHEEL_NAME = os.getenv("WHEEL_NAME")
WHEEL_API_KEY = os.getenv("WHEEL_API_KEY")
WHEEL_ENABLED = bool(WHEEL_NAME and WHEEL_API_KEY)

# --- Spotify ---
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")
SPOTIFY_ENABLED = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN)

# ID of the "song request" channel points reward.
# Create it with !createsongreward from chat (broadcaster only).
SPOTIFY_REWARD_ID = os.getenv("SPOTIFY_REWARD_ID")

# Guard rails on viewer requests.
SONG_MAX_DURATION_S = _int("SONG_MAX_DURATION_S", 600)  # 10 min
SONG_COOLDOWN_S = _int("SONG_COOLDOWN_S", 60)  # per viewer, on !song
