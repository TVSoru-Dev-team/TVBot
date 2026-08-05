"""Wheel of Names commands.

Ported from the 2.x version of the bot. Two changes beyond the port itself: HTTP
calls go through aiohttp (http.client blocked the asyncio loop for the whole
request), and the entries belong to the component instead of a module global.

API failures are logged in full but reported to chat generically, so that a
third-party error body never lands in the channel.

Known issue (already present before the port): the first entry is sometimes not
added to the wheel.

Chat-facing strings are in French, matching the channel's audience.
"""

from __future__ import annotations

import logging

import aiohttp
from twitchio.ext import commands

import config

LOGGER = logging.getLogger(__name__)

WHEEL_API_URL = "https://wheelofnames.com/api/v1/wheels"

GENERIC_ERROR = "l'API de la roue a renvoyé une erreur, voir les logs du bot."


class WheelComponent(commands.Component):
    def __init__(self, bot: commands.Bot, *, session: aiohttp.ClientSession) -> None:
        self.bot = bot
        self._session = session
        self._entries: list[dict[str, object]] = []

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": config.WHEEL_API_KEY or "",
            "Content-Type": "application/json",
            "Accept": "application/json, application/xml",
        }

    async def _push(self) -> bool:
        """Send the current wheel state. Returns whether it succeeded.

        The Wheel of Names API replaces the whole configuration on every PUT, so
        the full entry list is always sent.
        """
        payload = {
            "wheelConfig": {
                "description": "Roue de test",
                "title": "Roue de test",
                "entries": self._entries,
            },
            "shareMode": "gallery",
        }
        try:
            async with self._session.put(
                f"{WHEEL_API_URL}/{config.WHEEL_NAME}", json=payload, headers=self._headers
            ) as resp:
                if resp.status != 200:
                    LOGGER.error("Wheel API error (%s): %s", resp.status, await resp.text())
                    return False
                return True
        except aiohttp.ClientError:
            LOGGER.exception("Wheel API unreachable")
            return False

    @commands.command(name="addwheel")
    async def add_wheel_entry(self, ctx: commands.Context, *, entry_text: str) -> None:
        """Add an entry to the Wheel of Names wheel."""
        self._entries.append({"text": entry_text, "enabled": True})
        LOGGER.info("Adding entry %r to wheel %s", entry_text, config.WHEEL_NAME)

        if await self._push():
            await ctx.reply(f"l'entrée '{entry_text}' a été ajoutée à la roue.")
        else:
            self._entries.pop()  # Don't keep an entry the API rejected.
            await ctx.reply(GENERIC_ERROR)

    @commands.command(name="1v1")
    async def one_v_one(self, ctx: commands.Context) -> None:
        """Add the viewer's name to the wheel, unless already present."""
        username = ctx.chatter.name or ctx.chatter.display_name

        if any(str(e["text"]).lower() == username.lower() for e in self._entries):
            await ctx.reply("tu es déjà dans la roue pour un 1v1 !")
            return

        self._entries.append({"text": username, "enabled": True})
        LOGGER.info("Adding %r to wheel %s via !1v1", username, config.WHEEL_NAME)

        if await self._push():
            await ctx.reply("tu as été ajouté à la roue pour un 1v1 !")
        else:
            self._entries.pop()
            await ctx.reply(GENERIC_ERROR)

    @commands.command(name="resetwheel")
    @commands.is_moderator()
    async def reset_wheel(self, ctx: commands.Context) -> None:
        """Clear the wheel (moderators only)."""
        previous, self._entries = self._entries, []

        if await self._push():
            await ctx.send("La roue a été réinitialisée !")
        else:
            self._entries = previous
            await ctx.send(GENERIC_ERROR)

    @commands.command(name="remove")
    @commands.is_moderator()
    async def remove_entry(self, ctx: commands.Context, *, entry_text: str) -> None:
        """Remove an entry from the wheel (moderators only)."""
        index = next(
            (i for i, e in enumerate(self._entries) if str(e["text"]).lower() == entry_text.lower()),
            None,
        )
        if index is None:
            await ctx.send(f"L'entrée '{entry_text}' n'existe pas dans la roue.")
            return

        removed = self._entries.pop(index)
        if await self._push():
            await ctx.send(f"L'entrée '{removed['text']}' a été retirée de la roue.")
        else:
            self._entries.insert(index, removed)
            await ctx.send(GENERIC_ERROR)
