from twitchio.ext import commands
from dotenv import load_dotenv
import os
import http.client
import json

# --- Configuration ---
load_dotenv()

TWITCH_TOKEN = os.getenv('TWITCH_TOKEN')
TWITCH_NICK = 'tvsorubot'
TWITCH_CHANNEL = 'tvsoru' 
WHEEL_NAME = os.getenv('WHEEL_NAME')

WHEEL_API_URL = "https://wheelofnames.com/api/v1/wheels/"

WHEEL_API_KEY = os.getenv('WHEEL_API_KEY')
headers = {
    'x-api-key': WHEEL_API_KEY,
    'Content-Type': "application/json",
    'Accept': "application/json, application/xml"
}

payload = {
    "wheelConfig": {
        "description": "Roue de test",
        "title": "Roue de test",
        "entries": [
        ],
    },
    "shareMode": "gallery"
}

# --- Bot Class ---
# Known Issues:
# There is an issue with the first entry, it is sometimes not added to the wheel but 

# TODO : Either use multiple subclasses or decorators to easely choose wich commands to enable when running the bot
# TODO : Group sets of commands (wheel related, etc) 
# TODO : Host the bot on a server to keep it running 24/7


class Bot(commands.Bot):

    def __init__(self):
        super().__init__(token=TWITCH_TOKEN, prefix='!', initial_channels=[TWITCH_CHANNEL])

    # Event called when the bot is ready and the channel online
    async def event_ready(self):
        print(f"Connecté en tant que {self.nick}")
        print(f"ID utilisateur : {self.user_id}")
        self.conn = http.client.HTTPSConnection("wheelofnames.com")
        channel = self.get_channel(TWITCH_CHANNEL)
        if channel:
            await channel.send(f"Salut, je suis {self.nick} ! Utilisez !1v1 pour vous ajouter automatiquement à la roue des 1v1.")
            print(f"Bot prêt et connecté au canal {TWITCH_CHANNEL}.")
        else:
            print(f"Impossible de trouver le canal {TWITCH_CHANNEL}. Assurez-vous que le bot est autorisé à rejoindre ce canal.")

    async def event_message(self, message):
        if message.echo:
            return
        print(f"{message.author.name}: {message.content}")
        await self.handle_commands(message)

    # Custom commands

    # Command that send a message to the channel when the bot is ready
    @commands.command(name='test')
    async def test_command(self, ctx: commands.Context):
        """Test command to check if the bot is working."""
        await ctx.send(f"@{ctx.author.name}, le bot est en ligne et fonctionne correctement !")
        print(f"Commande test exécutée par {ctx.author.name}")
    

    ## AutoWheel Commands

    # Command to add an entry to the AutoWheel
    @commands.command(name='addwheel')
    async def add_wheel_entry(self, ctx: commands.Context, *, entry_text: str):
        """Ajoute une entrée à la roue Wheel of Names."""
        if not entry_text:
            await ctx.send(f"@{ctx.author.name}, veuillez spécifier le texte à ajouter. Exemple: !addwheel Mon Entrée")
            return
        try:
            payload['wheelConfig']['entries'].append({
                "text": entry_text,
                "enabled": True
            })
            print(f"Ajout de l'entrée : {entry_text} à la roue {WHEEL_NAME}")
            self.conn.request("PUT", f"/api/v1/wheels/{WHEEL_NAME}", json.dumps(payload), headers)
            response = self.conn.getresponse()
            data = response.read().decode('utf-8')
            print(f"Réponse de l'API : {data}")
            if response.status == 200:
                await ctx.send(f"@{ctx.author.name}, l'entrée '{entry_text}' a été ajoutée à la roue.")
            else:
                await ctx.send(f"@{ctx.author.name}, une erreur s'est produite lors de l'ajout de l'entrée : {data}")
        except Exception as e:
            print(f"Erreur lors de l'ajout de l'entrée : {e}")
            await ctx.send(f"@{ctx.author.name}, une erreur s'est produite lors de l'ajout de l'entrée. Veuillez réessayer.")

    # Command to add the viewer's username to the wheel
    @commands.command(name='1v1')
    async def one_v_one(self, ctx: commands.Context):
        """Ajoute le nom d'utilisateur du viewer à la roue Wheel of Names via !1v1, si non déjà présent."""
        username = ctx.author.name
        entries = payload['wheelConfig']['entries']
        # Verify if the user is already in the wheel
        if any(e["text"].lower() == username.lower() for e in entries):
            await ctx.send(f"@{username}, tu es déjà dans la roue pour un 1v1 !")
            return
        try:
            entries.append({
                "text": username,
                "enabled": True
            })
            print(f"Ajout de l'entrée : {username} à la roue {WHEEL_NAME} via !1v1")
            self.conn.request("PUT", f"/api/v1/wheels/{WHEEL_NAME}", json.dumps(payload), headers)
            response = self.conn.getresponse()
            data = response.read().decode('utf-8')
            print(f"Réponse de l'API : {data}")
            if response.status == 200:
                await ctx.send(f"@{username}, tu as été ajouté à la roue pour un 1v1 !")
            else:
                await ctx.send(f"@{username}, une erreur s'est produite lors de l'ajout à la roue : {data}")
        except Exception as e:
            print(f"Erreur lors de l'ajout de l'entrée via !1v1 : {e}")
            await ctx.send(f"@{username}, une erreur s'est produite lors de l'ajout à la roue. Veuillez réessayer.")

    # Command to reset the wheel (only for moderators)
    @commands.command(name='resetwheel')
    async def reset_wheel(self, ctx: commands.Context):
        """Réinitialise la roue (modérateurs uniquement)."""
        # Vérifie id the user is a moderator or the broadcaster
        if not (ctx.author.is_mod or ctx.author.name.lower() == TWITCH_CHANNEL.lower()):
            await ctx.send(f"@{ctx.author.name}, tu dois être modérateur pour réinitialiser la roue.")
            return
        try:
            payload['wheelConfig']['entries'] = []
            self.conn.request("PUT", f"/api/v1/wheels/{WHEEL_NAME}", json.dumps(payload), headers)
            response = self.conn.getresponse()
            data = response.read().decode('utf-8')
            print(f"Réinitialisation de la roue : {data}")
            if response.status == 200:
                await ctx.send("La roue a été réinitialisée !")
            else:
                await ctx.send(f"Erreur lors de la réinitialisation : {data}")
        except Exception as e:
            print(f"Erreur lors de la réinitialisation de la roue : {e}")
            await ctx.send("Une erreur est survenue lors de la réinitialisation de la roue.")

    # Command to remove an entry from the wheel (only for moderators)
    @commands.command(name='remove')
    async def remove_entry(self, ctx: commands.Context, *, entry_text: str):
        """Enlève une entrée de la roue (modérateurs uniquement)."""
        # Vérifye if the user is a moderator or the broadcaster
        if not (ctx.author.is_mod or ctx.author.name.lower() == TWITCH_CHANNEL.lower()):
            await ctx.send(f"@{ctx.author.name}, tu dois être modérateur pour enlever une entrée.")
            return
        try:
            entries = payload['wheelConfig']['entries']
            # Find the index of the entry to remove
            index_to_remove = next((i for i, e in enumerate(entries) if e["text"].lower() == entry_text.lower()), None)
            if index_to_remove is not None:
                removed = entries.pop(index_to_remove)
                self.conn.request("PUT", f"/api/v1/wheels/{WHEEL_NAME}", json.dumps(payload), headers)
                response = self.conn.getresponse()
                data = response.read().decode('utf-8')
                print(f"Entrée supprimée : {removed['text']} | Réponse API : {data}")
                if response.status == 200:
                    await ctx.send(f"L'entrée '{removed['text']}' a été retirée de la roue.")
                else:
                    await ctx.send(f"Erreur lors de la suppression : {data}")
            else:
                await ctx.send(f"L'entrée '{entry_text}' n'existe pas dans la roue.")
        except Exception as e:
            print(f"Erreur lors de la suppression de l'entrée : {e}")
            await ctx.send("Une erreur est survenue lors de la suppression de l'entrée.")


if __name__ == "__main__":
    bot = Bot()
    bot.run()