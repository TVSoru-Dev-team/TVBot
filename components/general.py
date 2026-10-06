"""General commands, with no external dependency.

Chat-facing strings are in French, matching the channel's audience.
"""

from __future__ import annotations

from twitchio.ext import commands


class GeneralComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="test")
    async def test_command(self, ctx: commands.Context) -> None:
        """Check that the bot responds."""
        await ctx.reply("le bot est en ligne et fonctionne correctement !")

    @commands.command(name="commandes", aliases=["aide"])
    async def list_commands(self, ctx: commands.Context) -> None:
        """List the available commands."""
        # bot.commands holds one entry per alias, so dedupe on the name.
        names = sorted(
            {
                command.name
                for command in self.bot.commands.values()
                # Reward commands are named after the reward ID: they are not
                # callable from chat, so they are left out.
                if not isinstance(command, commands.RewardCommand)
            }
        )
        await ctx.reply("commandes : " + ", ".join(f"!{name}" for name in names))
