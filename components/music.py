"""Song requests: the !song command and the channel points reward.

Both entry points (chat and channel points) funnel into `_queue_track`, so that
behaviour and messages stay identical between them.

This component draws nothing on screen: Spotify runs on the streamer's machine
and OBS already captures its audio, so queueing the track is enough for it to
change on stream.

Chat-facing strings are in French, matching the channel's audience.
"""

from __future__ import annotations

import logging

import aiohttp
from twitchio.ext import commands

import config
from spotify import SpotifyClient, SpotifyError, Track

LOGGER = logging.getLogger(__name__)

REWARD_TITLE = "Demande de musique"
REWARD_PROMPT = "Colle le lien Spotify du morceau (https://open.spotify.com/track/...)"

# Hard cap on !queue, regardless of the count argument: keeps the chat message
# from growing unbounded (Twitch also caps message length).
MAX_QUEUE_DISPLAY = 10


class MusicComponent(commands.Component):
    def __init__(self, bot: commands.Bot, *, session: aiohttp.ClientSession) -> None:
        self.bot = bot
        self.spotify = SpotifyClient(
            config.SPOTIFY_CLIENT_ID or "",
            config.SPOTIFY_CLIENT_SECRET or "",
            config.SPOTIFY_REFRESH_TOKEN or "",
            session=session,
        )

    async def _queue_track(self, link: str, requester: str) -> str:
        """Queue `link` on Spotify. Returns the message to post in chat.

        Raises `SpotifyError` when the request cannot be fulfilled; the caller
        decides what to do about it (refund the points, reply in chat, ...).
        """
        track: Track = await self.spotify.get_track_from_link(link)

        if track.duration_ms > config.SONG_MAX_DURATION_S * 1000:
            raise SpotifyError(
                f"« {track.name} » fait {track.duration_display}, "
                f"la limite est de {config.SONG_MAX_DURATION_S // 60} min"
            )

        await self.spotify.add_to_queue(track)
        LOGGER.info("%s queued %s", requester, track)
        return f"🎵 {track} ajouté à la file !"

    # --- Chat ---

    @commands.command(name="song", aliases=["musique"])
    @commands.cooldown(rate=1, per=config.SONG_COOLDOWN_S, key=commands.BucketType.chatter)
    async def song(self, ctx: commands.Context) -> None:
        """Show the track currently playing: !song"""
        try:
            current, _ = await self.spotify.get_queue()
        except SpotifyError as exc:
            await ctx.reply(f"impossible de récupérer le morceau en cours : {exc}")
            return

        if current is None:
            await ctx.reply("rien ne joue sur Spotify en ce moment.")
            return

        await ctx.reply(f"🎵 en cours : {current}")

    @commands.command(name="queue", aliases=["file"])
    @commands.cooldown(rate=1, per=config.QUEUE_COOLDOWN_S, key=commands.BucketType.chatter)
    async def queue(self, ctx: commands.Context, count: int = 5) -> None:
        """Show the upcoming tracks in the queue: !queue [nombre]"""
        count = max(1, min(count, MAX_QUEUE_DISPLAY))

        try:
            _, upcoming = await self.spotify.get_queue()
        except SpotifyError as exc:
            await ctx.reply(f"impossible de récupérer la file : {exc}")
            return

        if not upcoming:
            await ctx.reply("la file d'attente est vide.")
            return

        listing = " | ".join(f"{i}. {track}" for i, track in enumerate(upcoming[:count], start=1))
        await ctx.reply(f"🎶 à venir : {listing}")

    # --- Channel points ---

    # The command name is derived from the reward ID. When SPOTIFY_REWARD_ID is
    # unset the command is still registered, but no redemption can ever match
    # it, so the bot still starts.
    # `invoke_when=unfulfilled`: the reward must NOT be configured to skip the
    # request queue, which is what lets us fulfill or refund it afterwards.
    @commands.reward_command(
        id=config.SPOTIFY_REWARD_ID or "reward-not-configured",
        invoke_when=commands.RewardStatus.unfulfilled,
    )
    async def song_reward(self, ctx: commands.Context, *, user_input: str = "") -> None:
        redemption = ctx.redemption
        assert redemption is not None  # guaranteed by reward_command

        requester = redemption.user.name or redemption.user.display_name or str(redemption.user.id)

        try:
            message = await self._queue_track(user_input, requester)
        except SpotifyError as exc:
            LOGGER.warning("Refused request from %s (%s), refunding points", requester, exc)
            await ctx.send(f"@{requester} {exc} - tes points t'ont été rendus.")
            await self._settle(redemption, refund=True)
            return

        await ctx.send(f"@{requester} {message}")
        await self._settle(redemption, refund=False)

    async def _settle(self, redemption, *, refund: bool) -> None:
        """Fulfill or refund the redemption. Needs channel:manage:redemptions."""
        try:
            if refund:
                await redemption.refund(token_for=config.OWNER_ID)
            else:
                await redemption.fulfill(token_for=config.OWNER_ID)
        except Exception:
            # The track is already queued: don't break the flow just because
            # updating the redemption queue failed.
            LOGGER.exception("Could not update redemption %s", redemption.id)

    # --- Setup ---

    @commands.command(name="createsongreward")
    @commands.is_broadcaster()
    async def create_song_reward(self, ctx: commands.Context, cost: int = 500) -> None:
        """Create the channel points reward and print its ID (broadcaster only)."""
        try:
            reward = await ctx.broadcaster.create_custom_reward(
                REWARD_TITLE,
                cost,
                prompt=REWARD_PROMPT,
                global_cooldown=config.SONG_COOLDOWN_S,
                # Left False so the bot can refund an invalid request.
                redemptions_skip_queue=False,
            )
        except Exception:
            LOGGER.exception("Failed to create the reward")
            await ctx.reply("création de la récompense impossible, voir les logs du bot.")
            return

        # The ID has to end up in the .env, so the console is where it matters.
        print(f"\n>>> Add this to your .env and restart the bot:\nSPOTIFY_REWARD_ID={reward.id}\n")
        await ctx.reply(
            f"récompense « {REWARD_TITLE} » créée ({cost} points). "
            "Son ID est affiché dans la console du bot : mets-le dans SPOTIFY_REWARD_ID puis redémarre-moi."
        )
