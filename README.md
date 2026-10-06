# TVBot

Twitch bot for the **tvsoru** channel, written in Python with [twitchio 3](https://twitchio.dev).

*🇫🇷 [Version française](README.fr.md)*

## Commands

| Command | Who | Effect |
| --- | --- | --- |
| `!test` | everyone | Check that the bot responds |
| `!commandes` (`!aide`) | everyone | List the available commands |
| `!song` (`!musique`) | everyone | Show the Spotify track currently playing |
| `!queue [count]` (`!file`) | everyone | Show the upcoming tracks in the queue (longer cooldown than `!song`) |
| `!1v1` | everyone | Add yourself to the 1v1 wheel |
| `!addwheel <text>` | everyone | Add an entry to the wheel |
| `!remove <text>` | moderators | Remove an entry from the wheel |
| `!resetwheel` | moderators | Clear the wheel |
| `!createsongreward [cost]` | broadcaster | Create the "Demande de musique" channel points reward |
| `!addcom <name> <text>` | moderators | Create or update a custom command (e.g. `!addcom youtube https://...`) |
| `!delcom <name>` | moderators | Delete a custom command |
| `!listcom` | everyone | List the existing custom commands |

Chat replies are in French, matching the channel's audience; the code, comments and logs are in English.

Song requests only happen through a **channel points reward**: the viewer spends their points and pastes the Spotify link into the text field. If the link is invalid, the track too long, or Spotify unavailable, the bot **automatically refunds** the points. `!song` and `!queue` are read-only: they show what is playing / coming up, they do not request anything.

Custom commands (`!addcom`) let you add fixed text replies without touching the code — typically links (YouTube, Discord, Instagram, TikTok, donations, channel VODs...). They are stored in `custom_commands.json` (created automatically, git-ignored) and reloaded on every restart.

## Installation

```bash
poetry lock       # required: the lockfile predates the twitchio 3 migration
poetry install
cp .env.example .env   # then fill it in
```

## Configuration

### 1. Twitch application

At <https://dev.twitch.tv/console/apps>, create an application with `http://localhost:4343/oauth/callback` as the **OAuth Redirect URL**. Copy the Client ID and Client Secret into the `.env`.

Also set `TWITCH_BOT_ID` (bot account) and `TWITCH_OWNER_ID` (streamer account): twitchio 3 works with numeric user IDs, no longer with logins.

### 2. Authorize both Twitch accounts

The bot needs a token for the bot account **and** a token for the streamer's account (channel points belong to the streamer). Start the bot:

```bash
poetry run python main.py
```

then open <http://localhost:4343/oauth> **while logged in as the bot account**, and a second time **logged in as the streamer's account**. Tokens are stored in `.tio.tokens.json` and refreshed automatically afterwards: this step only needs redoing if the scopes change.

### 3. Spotify

At <https://developer.spotify.com/dashboard>, create an application with `http://127.0.0.1:8888/callback` as the **Redirect URI** (Spotify no longer accepts `localhost`, the loopback IP is required). Copy the Client ID / Client Secret into the `.env`, then, **on the streamer's machine, logged into their Spotify account**:

```bash
poetry run python scripts/authorize_spotify.py
```

The script prints a `SPOTIFY_REFRESH_TOKEN` to paste into the `.env`. Verify with:

```bash
poetry run python -m spotify "https://open.spotify.com/track/..."
```

> The Spotify account must be **Premium**: the playback control API refuses free
> accounts. Spotify also has to be actively playing on some device, otherwise
> there is no queue to add to.

### 4. Channel points reward

Once the bot is running and Spotify is configured, type in chat (as the streamer):

```
!createsongreward 500
```

The reward ID is printed in the bot's console. Put it in `SPOTIFY_REWARD_ID` and restart the bot.

The reward is created *without* "skip the request queue": that is what lets the bot refund the points when a request fails.

## Running

```bash
poetry run python main.py
```

## Audio on stream

Nothing to configure in OBS: Spotify runs on the streamer's machine and OBS already captures its audio. The bot appends tracks to the Spotify queue, so playback follows on its own. The bot draws nothing on screen.

## Layout

```
main.py                        Entry point: bot setup, EventSub, error handling
config.py                      .env loading and validation
spotify.py                     Spotify client (OAuth, link parsing, queueing)
components/general.py          !test, !commandes
components/custom_commands.py  !addcom, !delcom, !listcom
components/music.py            !song, !queue and the channel points reward
components/wheel.py            Wheel of Names commands
scripts/authorize_spotify.py   Spotify authorization, run once
data/                          Runtime state written by the bot (see below), git-ignored
```

Each group of commands is a `commands.Component`: that is the only registration mechanism in twitchio 3 : a command defined directly on the `Bot` class is **silently ignored**.

Everything the bot writes at runtime — `.tio.tokens.json` (Twitch OAuth tokens)
and `custom_commands.json` (from `!addcom`) — lives under `data/` instead of
the project root, so a deployment only has one directory to persist instead of
tracking each file individually.

## Docker

```bash
docker build -t tvbot .
docker run -d --name tvbot -p 4343:4343 \
  -v "$(pwd)/.env:/app/.env" \
  -v "$(pwd)/data:/app/data" \
  tvbot
```

`data/` must persist across restarts/redeploys (it holds the OAuth tokens and
custom commands) — mount it as a volume, same as on any orchestrator (Komodo,
Portainer, a plain `docker-compose.yml`...). `.env` is simplest as a mounted
file for local Docker use; on an orchestrator that has its own secret/env
storage (Komodo's `environment` field, for instance), set the variables there
instead and skip mounting `.env` entirely — `config.py` reads from the
process environment either way.

Port `4343` only needs to stay published for the one-time `/oauth`
authorization of both Twitch accounts (see Configuration above); it is not
needed for the bot to keep running afterwards, but leaving it published makes
re-authorizing easier if scopes ever change.

## Security notes

- `.env` and `data/` (Twitch OAuth tokens, custom commands) are git-ignored. Never commit them.
- Viewer-supplied links are validated against an anchored regex before reaching the Spotify API; only a 22-character base62 track ID ever reaches a URL.
- Upstream API errors are written to the logs, never echoed into public chat, which would leak which credential is broken.
- The streamer's Twitch token is used only to fulfill or refund the redemption that triggered it.
- `!addwheel` is open to everyone, as it already was before the twitchio 3 migration: any viewer can publish arbitrary text on the streamer's public wheel. Add `@commands.is_moderator()` in `components/wheel.py` to restrict it.

## TODO

- Host the bot on a server to keep it running 24/7.
- `!resetwheel` and `!remove` use `is_moderator()`, which checks the moderator badge, the broadcaster does not carry it, so they cannot use those commands. `is_elevated()` would cover broadcaster, moderators and VIPs.
- Known issue (predating the port): the first entry is sometimes not added to the wheel.
