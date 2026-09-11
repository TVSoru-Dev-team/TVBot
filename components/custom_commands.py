"""Broadcaster/mod-managed custom text commands: !addcom, !delcom, !listcom.

Definitions persist in custom_commands.json so they survive restarts. Each one
is registered directly on the bot (bypassing this component's own command
table), so it shows up in !commandes and gets the same collision checks as any
built-in command.

Chat-facing strings are in French, matching the channel's audience.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from twitchio.ext import commands

LOGGER = logging.getLogger(__name__)

STORE_PATH = Path("custom_commands.json")


class CustomCommandsComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._commands: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not STORE_PATH.exists():
            return {}
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            LOGGER.exception("Could not read %s, starting with no custom commands", STORE_PATH)
            return {}

    def _save(self) -> None:
        STORE_PATH.write_text(json.dumps(self._commands, ensure_ascii=False, indent=2), encoding="utf-8")

    def _register(self, name: str, text: str) -> None:
        async def _respond(ctx: commands.Context) -> None:
            await ctx.reply(text)

        self.bot.add_command(commands.Command(_respond, name=name))

    async def component_load(self) -> None:
        for name, text in self._commands.items():
            try:
                self._register(name, text)
            except commands.CommandExistsError:
                LOGGER.error("Custom command %r collides with a built-in command, skipping", name)

    @commands.command(name="addcom")
    @commands.is_moderator()
    async def add_command(self, ctx: commands.Context, name: str | None = None, *, text: str | None = None) -> None:
        """Create or update a custom command: !addcom <nom> <texte> (modérateurs)"""
        if not name or not text:
            await ctx.reply("usage : !addcom <nom> <texte>")
            return

        name = name.lower().lstrip("!")

        if name in self._commands:
            # One of ours: safe to replace, it has no aliases to disturb.
            self.bot.remove_command(name)
        elif self.bot.get_command(name) is not None:
            await ctx.reply(f"« !{name} » est déjà une commande du bot, choisis un autre nom.")
            return

        self._register(name, text)
        self._commands[name] = text
        self._save()
        await ctx.reply(f"commande !{name} enregistrée.")

    @commands.command(name="delcom")
    @commands.is_moderator()
    async def delete_command(self, ctx: commands.Context, name: str | None = None) -> None:
        """Delete a custom command: !delcom <nom> (modérateurs)"""
        if not name:
            await ctx.reply("usage : !delcom <nom>")
            return

        name = name.lower().lstrip("!")
        if name not in self._commands:
            await ctx.reply(f"« !{name} » n'existe pas.")
            return

        del self._commands[name]
        self._save()
        self.bot.remove_command(name)
        await ctx.reply(f"commande !{name} supprimée.")

    @commands.command(name="listcom")
    async def list_command(self, ctx: commands.Context) -> None:
        """List the custom commands: !listcom"""
        if not self._commands:
            await ctx.reply("aucune commande personnalisée pour le moment.")
            return

        names = ", ".join(f"!{name}" for name in sorted(self._commands))
        await ctx.reply(f"commandes personnalisées : {names}")
