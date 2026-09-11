"""Twitch bot for the tvsoru channel (twitchio 3.x).

Run with:  python main.py

Unlike the 2.x version, twitchio 3 no longer connects over IRC with a single
token: it uses the Twitch API plus EventSub, and needs user tokens for the bot
account AND for the streamer's account. Those tokens are obtained once through
the browser (see README), then stored in .tio.tokens.json and refreshed
automatically.

Chat-facing strings are in French, matching the channel's audience; everything
else (logs, comments) is in English.

TODO: host the bot on a server to keep it running 24/7.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import aiohttp
import twitchio
from twitchio import eventsub
from twitchio.ext import commands

try:
    # config validates the .env at import time; catching this prints a readable
    # message instead of a traceback on first run (ConfigError < RuntimeError).
    import config
except RuntimeError as exc:
    raise SystemExit(f"Invalid configuration.\n{exc}") from None

from components.custom_commands import CustomCommandsComponent
from components.general import GeneralComponent
from components.music import MusicComponent
from components.wheel import WheelComponent

LOGGER = logging.getLogger(__name__)

# Scopes requested during authorization via http://localhost:4343/oauth.
# Twitch only grants what is asked for: adding a feature that needs a new scope
# means re-authorizing both accounts.
SCOPES = twitchio.Scopes(
    [
        # Bot account: read and write chat.
        "user:read:chat",
        "user:write:chat",
        "user:bot",
        # Streamer account: let the bot post, and manage channel points.
        "channel:bot",
        "channel:read:redemptions",
        "channel:manage:redemptions",
    ]
)


class Bot(commands.Bot):
    def __init__(self, *, session: aiohttp.ClientSession) -> None:
        self.session = session
        self._chat_subscribed = False
        self._redemptions_subscribed = False
        super().__init__(
            client_id=config.TWITCH_CLIENT_ID,
            client_secret=config.TWITCH_CLIENT_SECRET,
            bot_id=config.BOT_ID,
            owner_id=config.OWNER_ID,
            prefix="!",
            scopes=SCOPES,
        )

    async def setup_hook(self) -> None:
        await self.add_component(GeneralComponent(self))
        await self.add_component(CustomCommandsComponent(self))

        if config.SPOTIFY_ENABLED:
            await self.add_component(MusicComponent(self, session=self.session))
            if not config.SPOTIFY_REWARD_ID:
                LOGGER.warning(
                    "SPOTIFY_REWARD_ID is not set: !song works, but the channel points "
                    "reward is inactive. Run !createsongreward."
                )
        else:
            LOGGER.warning("Spotify is not configured: music commands are disabled.")

        if config.WHEEL_ENABLED:
            await self.add_component(WheelComponent(self, session=self.session))
        else:
            LOGGER.warning("Wheel of Names is not configured: wheel commands are disabled.")

        await self._subscribe_available()

    async def _subscribe_available(self) -> None:
        """Subscribe to the EventSub feeds whose account has already authorized.

        On a fresh setup, .tio.tokens.json is empty and login() (which calls
        setup_hook) runs before the /oauth web adapter starts listening:
        subscribing unconditionally here would crash before the account could
        ever authorize. Missing subscriptions are retried from
        event_oauth_authorized once the corresponding account authorizes.
        """
        if not self._chat_subscribed:
            if config.BOT_ID in self.tokens:
                # Receive the streamer's chat messages (using the bot's token).
                await self.subscribe_websocket(
                    eventsub.ChatMessageSubscription(
                        broadcaster_user_id=config.OWNER_ID, user_id=config.BOT_ID
                    )
                )
                self._chat_subscribed = True
            else:
                LOGGER.warning(
                    "Bot account not authorized yet: open http://localhost:4343/oauth "
                    "logged in as the bot account."
                )

        if config.SPOTIFY_ENABLED and not self._redemptions_subscribed:
            if config.OWNER_ID in self.tokens:
                # Channel points redemptions require the streamer's token, not the
                # bot's, hence as_bot=False.
                await self.subscribe_websocket(
                    eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=config.OWNER_ID),
                    as_bot=False,
                    token_for=config.OWNER_ID,
                )
                self._redemptions_subscribed = True
            else:
                LOGGER.warning(
                    "Streamer account not authorized yet: open http://localhost:4343/oauth "
                    "logged in as the streamer account."
                )

    async def event_ready(self) -> None:
        LOGGER.info("Logged in as %s (id %s)", self.user, self.bot_id)

    async def event_oauth_authorized(self, payload: twitchio.authentication.UserTokenPayload) -> None:
        # Fired when an account authorizes via http://localhost:4343/oauth.
        await self.add_token(payload.access_token, payload.refresh_token)
        LOGGER.info("Stored token for %s (%s)", payload.user_login, payload.user_id)
        await self._subscribe_available()

    async def event_command_error(self, payload: commands.CommandErrorPayload) -> None:
        error = payload.exception

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CommandOnCooldown):
            await payload.context.reply(f"doucement ! Réessaie dans {error.remaining:.0f}s.")
            return
        if isinstance(error, commands.GuardFailure):
            await payload.context.reply("tu n'as pas les droits pour cette commande.")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await payload.context.reply(f"il manque un argument : {error.param.name}")
            return

        # Unexpected errors are logged in full but reported generically, so that
        # internals never leak into chat.
        LOGGER.error("Error in command %s", payload.context.command, exc_info=error)
        await payload.context.reply("une erreur est survenue, désolé.")


async def main() -> None:
    # The Windows console defaults to cp1252: a track title containing an emoji
    # or non-latin characters would otherwise crash logging.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    twitchio.utils.setup_logging(level=logging.INFO)

    async with aiohttp.ClientSession() as session, Bot(session=session) as bot:
        await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
