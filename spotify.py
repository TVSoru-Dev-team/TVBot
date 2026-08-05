"""Minimal Spotify client used to queue tracks on the streamer's player.

This module has no Twitch dependency, so it can be tested on its own:
`python -m spotify <link>`.

Authentication flow: the streamer authorizes the app once through
`scripts/authorize_spotify.py`, which yields a long-lived refresh token. That
refresh token lives in the .env and is used to mint short-lived access tokens
(1 hour) on demand.

Note on language: `SpotifyError` messages are surfaced directly in Twitch chat,
so they are written in French like the rest of the viewer-facing strings.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import aiohttp

LOGGER = logging.getLogger(__name__)

ACCOUNTS_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

# Scopes needed: queueing tracks, plus reading the player state so we can tell
# "no active device" apart from other failures and report it usefully.
SCOPES = "user-modify-playback-state user-read-playback-state"

# A Spotify ID is a 22-character base62 string.
_ID = r"(?P<id>[A-Za-z0-9]{22})"
_TRACK_PATTERNS = (
    # spotify:track:<id>
    re.compile(rf"^spotify:track:{_ID}$"),
    # https://open.spotify.com/track/<id>, with an optional locale prefix
    # (e.g. /intl-fr/track/<id>) and an optional ?si=... query string.
    re.compile(rf"^https?://open\.spotify\.com/(?:[a-z-]+/)?track/{_ID}(?:[/?#].*)?$"),
)
# Only used to produce a precise error message.
_OTHER_KIND = re.compile(
    r"^(?:https?://open\.spotify\.com/(?:[a-z-]+/)?|spotify:)(?P<kind>album|playlist|artist|episode|show)[/:]"
)


class SpotifyError(Exception):
    """An expected failure whose message is meant for Twitch chat."""


class InvalidTrackLink(SpotifyError):
    pass


class NoActiveDevice(SpotifyError):
    pass


class PremiumRequired(SpotifyError):
    pass


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    name: str
    artists: str
    duration_ms: int
    explicit: bool

    @property
    def uri(self) -> str:
        return f"spotify:track:{self.id}"

    @property
    def duration_display(self) -> str:
        seconds = round(self.duration_ms / 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def __str__(self) -> str:
        return f"{self.name} - {self.artists} ({self.duration_display})"


def parse_track_id(link: str) -> str:
    """Extract a track ID from a link, a URI or a bare ID.

    Raises `InvalidTrackLink` when the input does not point at a track.
    """
    link = link.strip().strip("<>")  # Twitch and Discord sometimes wrap links

    for pattern in _TRACK_PATTERNS:
        match = pattern.match(link)
        if match:
            return match.group("id")

    if re.fullmatch(_ID, link):
        return link

    other = _OTHER_KIND.match(link)
    if other:
        kind = {
            "album": "un album",
            "playlist": "une playlist",
            "artist": "un artiste",
            "episode": "un épisode",
            "show": "un podcast",
        }[other.group("kind")]
        raise InvalidTrackLink(f"ce lien pointe vers {kind}, il me faut un lien vers un morceau")

    raise InvalidTrackLink("lien Spotify invalide (attendu : https://open.spotify.com/track/...)")


class SpotifyClient:
    """Wrapper around the handful of Spotify endpoints the bot needs.

    The aiohttp session is supplied by the caller (the bot already owns one),
    which avoids opening a second connection pool.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        session: aiohttp.ClientSession,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._session = session
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def _token(self) -> str:
        """Return a valid access token, refreshing it when needed.

        A 60s margin keeps us from starting a request with a token that expires
        mid-flight.
        """
        if self._access_token and time.monotonic() < self._expires_at - 60:
            return self._access_token

        data = {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        auth = aiohttp.BasicAuth(self._client_id, self._client_secret)
        async with self._session.post(ACCOUNTS_URL, data=data, auth=auth) as resp:
            body = await resp.json()
            if resp.status != 200:
                # Usual cause: the refresh token was revoked, or the app
                # credentials changed. Re-run authorize_spotify.py.
                # The upstream reason goes to the logs only: SpotifyError
                # messages are posted in public chat, and telling viewers which
                # credential is broken is free reconnaissance.
                LOGGER.error(
                    "Spotify token refresh failed (%s): %s",
                    resp.status,
                    body.get("error_description") or body.get("error"),
                )
                raise SpotifyError("Spotify est indisponible pour le moment")

        self._access_token = body["access_token"]
        self._expires_at = time.monotonic() + body.get("expires_in", 3600)
        # Spotify may rotate the refresh token; keep the most recent one.
        if body.get("refresh_token"):
            self._refresh_token = body["refresh_token"]
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._token()}"}

    async def get_track(self, track_id: str) -> Track:
        async with self._session.get(
            f"{API_BASE}/tracks/{track_id}", headers=await self._headers()
        ) as resp:
            if resp.status == 404:
                raise InvalidTrackLink("ce morceau n'existe pas sur Spotify")
            if resp.status != 200:
                LOGGER.error("Spotify track lookup failed (%s): %s", resp.status, await resp.text())
                raise SpotifyError("Spotify est indisponible pour le moment")
            data = await resp.json()

        return Track(
            id=data["id"],
            name=data["name"],
            artists=", ".join(a["name"] for a in data["artists"]),
            duration_ms=data["duration_ms"],
            explicit=data.get("explicit", False),
        )

    async def add_to_queue(self, track: Track) -> None:
        """Append the track to the queue of the streamer's active player."""
        async with self._session.post(
            f"{API_BASE}/me/player/queue",
            params={"uri": track.uri},
            headers=await self._headers(),
        ) as resp:
            if resp.status in (200, 204):
                return

            # Spotify error bodies look like
            # {"error": {"status": .., "message": .., "reason": ..}}
            try:
                error = (await resp.json()).get("error", {})
            except aiohttp.ContentTypeError:
                error = {}
            reason = error.get("reason")

            if resp.status == 404 or reason == "NO_ACTIVE_DEVICE":
                raise NoActiveDevice(
                    "aucun appareil Spotify actif : le streamer doit lancer la lecture"
                )
            if reason == "PREMIUM_REQUIRED":
                raise PremiumRequired("le compte Spotify du streamer n'est pas Premium")
            if resp.status == 429:
                raise SpotifyError("Spotify limite les requêtes, réessaie dans un instant")
            # Spotify's own message stays in the logs: chat messages are public,
            # so upstream details are kept out of them.
            LOGGER.error("Spotify queue call failed (%s): %s", resp.status, error)
            raise SpotifyError("Spotify a refusé la requête")

    async def get_track_from_link(self, link: str) -> Track:
        """Resolve a link/URI/ID into a track, without queueing it."""
        return await self.get_track(parse_track_id(link))

    async def request_track(self, link: str) -> Track:
        """Full path: link -> track queued. Returns the track."""
        track = await self.get_track_from_link(link)
        await self.add_to_queue(track)
        return track


if __name__ == "__main__":
    # Manual check: python -m spotify "https://open.spotify.com/track/..."
    import asyncio
    import os
    import sys

    from dotenv import load_dotenv

    async def main() -> None:
        load_dotenv()
        if len(sys.argv) < 2:
            sys.exit("usage: python -m spotify <spotify link>")

        async with aiohttp.ClientSession() as session:
            client = SpotifyClient(
                os.environ["SPOTIFY_CLIENT_ID"],
                os.environ["SPOTIFY_CLIENT_SECRET"],
                os.environ["SPOTIFY_REFRESH_TOKEN"],
                session=session,
            )
            try:
                track = await client.request_track(sys.argv[1])
            except SpotifyError as exc:
                sys.exit(f"Failed: {exc}")
            print(f"Queued: {track}")

    asyncio.run(main())
