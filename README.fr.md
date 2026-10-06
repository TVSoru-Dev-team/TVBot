# TVBot

Bot Twitch de la chaîne **tvsoru**, écrit en Python avec [twitchio 3](https://twitchio.dev).

*🇬🇧 [English version](README.md)*

## Commandes

| Commande | Qui | Effet |
| --- | --- | --- |
| `!test` | tout le monde | Vérifie que le bot répond |
| `!commandes` (`!aide`) | tout le monde | Liste les commandes disponibles |
| `!song` (`!musique`) | tout le monde | Affiche le morceau Spotify en cours |
| `!queue [nombre]` (`!file`) | tout le monde | Affiche les prochains morceaux dans la file (cooldown plus long que `!song`) |
| `!1v1` | tout le monde | S'ajoute à la roue des 1v1 |
| `!addwheel <texte>` | tout le monde | Ajoute une entrée à la roue |
| `!remove <texte>` | modérateurs | Retire une entrée de la roue |
| `!resetwheel` | modérateurs | Vide la roue |
| `!createsongreward [coût]` | streamer | Crée la récompense de points de chaîne « Demande de musique » |
| `!addcom <nom> <texte>` | modérateurs | Crée ou met à jour une commande personnalisée (ex. `!addcom youtube https://...`) |
| `!delcom <nom>` | modérateurs | Supprime une commande personnalisée |
| `!listcom` | tout le monde | Liste les commandes personnalisées existantes |

Les réponses dans le chat sont en français, comme le public de la chaîne ; le code, les commentaires et les logs sont en anglais.

Les demandes de musique se font uniquement via une **récompense de points de chaîne** : le viewer dépense ses points et colle le lien Spotify dans le champ de saisie. Si le lien est invalide, le morceau trop long ou Spotify indisponible, le bot **rembourse automatiquement** les points. `!song` et `!queue` ne servent qu'à consulter ce qui joue / va jouer, pas à faire une demande.

Les commandes personnalisées (`!addcom`) permettent d'ajouter des réponses texte fixes sans toucher au code — typiquement des liens (YouTube, Discord, Instagram, TikTok, don, VOD de la chaîne...). Elles sont stockées dans `custom_commands.json` (créé automatiquement, git-ignoré) et rechargées à chaque démarrage.

## Installation

```bash
poetry lock       # nécessaire : le lockfile est antérieur à la migration twitchio 3
poetry install
cp .env.example .env   # puis remplir le .env
```

## Configuration

### 1. Application Twitch

Sur <https://dev.twitch.tv/console/apps>, créer une application avec `http://localhost:4343/oauth/callback` comme **OAuth Redirect URL**. Reporter le Client ID et le Client Secret dans le `.env`.

Renseigner aussi `TWITCH_BOT_ID` (compte du bot) et `TWITCH_OWNER_ID` (compte du streamer) : twitchio 3 travaille avec des IDs numériques, plus avec des pseudos.

### 2. Autoriser les deux comptes Twitch

Le bot a besoin d'un token pour le compte du bot **et** d'un token pour le compte du streamer (les points de chaîne appartiennent au streamer). Lancer le bot :

```bash
poetry run python main.py
```

puis ouvrir <http://localhost:4343/oauth> **une fois connecté avec le compte du bot**, et une seconde fois **connecté avec le compte du streamer**. Les tokens sont enregistrés dans `.tio.tokens.json` et rafraîchis automatiquement ensuite : cette étape n'est à refaire que si les scopes changent.

### 3. Spotify

Sur <https://developer.spotify.com/dashboard>, créer une application avec `http://127.0.0.1:8888/callback` comme **Redirect URI** (Spotify n'accepte plus `localhost`, il faut l'IP de loopback). Reporter Client ID / Client Secret dans le `.env`, puis, **sur la machine du streamer et connecté à son compte Spotify** :

```bash
poetry run python scripts/authorize_spotify.py
```

Le script affiche un `SPOTIFY_REFRESH_TOKEN` à coller dans le `.env`. Vérification :

```bash
poetry run python -m spotify "https://open.spotify.com/track/..."
```

> Le compte Spotify doit être **Premium** : l'API de contrôle de lecture refuse
> les comptes gratuits. Spotify doit aussi être en train de jouer sur un appareil,
> sinon il n'y a pas de file d'attente où ajouter le morceau.

### 4. Récompense de points de chaîne

Une fois le bot lancé et Spotify configuré, taper dans le chat (en tant que streamer) :

```
!createsongreward 500
```

L'ID de la récompense s'affiche dans la console du bot. Le mettre dans `SPOTIFY_REWARD_ID` puis redémarrer le bot.

La récompense est créée *sans* « passer la file d'attente » : c'est ce qui permet au bot de rembourser les points quand une demande échoue.

## Lancement

```bash
poetry run python main.py
```

## Le son sur le stream

Il n'y a rien à configurer côté OBS : Spotify tourne sur le PC du streamer et OBS en capte déjà l'audio. Le bot ajoute les morceaux à la file d'attente Spotify, la lecture enchaîne donc toute seule. Le bot n'affiche rien à l'écran.

## Structure

```
main.py                        Point d'entrée : configuration du bot, EventSub, gestion d'erreurs
config.py                      Chargement et validation du .env
spotify.py                     Client Spotify (OAuth, parsing de liens, file d'attente)
components/general.py          !test, !commandes
components/custom_commands.py  !addcom, !delcom, !listcom
components/music.py            !song, !queue et la récompense de points de chaîne
components/wheel.py            Commandes Wheel of Names
scripts/authorize_spotify.py   Autorisation Spotify, à lancer une fois
data/                          État runtime écrit par le bot (voir ci-dessous), ignoré par git
```

Chaque groupe de commandes est un `commands.Component` : c'est le seul mécanisme d'enregistrement en twitchio 3 : une commande définie directement sur la classe `Bot` est **ignorée silencieusement**.

Tout ce que le bot écrit au runtime — `.tio.tokens.json` (tokens OAuth Twitch)
et `custom_commands.json` (via `!addcom`) — vit dans `data/` plutôt qu'à la
racine du projet, pour qu'un déploiement n'ait qu'un seul dossier à persister
au lieu de suivre chaque fichier individuellement.

## Docker

```bash
docker build -t tvbot .
docker run -d --name tvbot -p 4343:4343 \
  -v "$(pwd)/.env:/app/.env" \
  -v "$(pwd)/data:/app/data" \
  tvbot
```

`data/` doit persister entre redémarrages/redéploiements (il contient les
tokens OAuth et les commandes personnalisées) — à monter en volume, comme sur
n'importe quel orchestrateur (Komodo, Portainer, un simple
`docker-compose.yml`...). Pour `.env`, monter un fichier est le plus simple en
Docker local ; sur un orchestrateur qui a son propre stockage de
secrets/variables (le champ `environment` de Komodo, par exemple), définissez-y
directement les variables et ne montez pas `.env` du tout — `config.py` lit de
toute façon les variables d'environnement du process, peu importe leur origine.

Le port `4343` n'a besoin de rester publié que pour l'autorisation `/oauth`
ponctuelle des deux comptes Twitch (voir Configuration ci-dessus) ; il n'est
pas nécessaire au fonctionnement du bot ensuite, mais le laisser publié
facilite une ré-autorisation si les scopes changent un jour.

### Amorcer `data/` sans toucher à l'hôte

Sur certains orchestrateurs, il n'y a aucun moyen pratique d'écrire
directement dans le volume `data/` (pas d'accès shell à l'hôte ni au
conteneur). En secours, le bot sème `data/.tio.tokens.json` et
`data/custom_commands.json` depuis les variables d'environnement
`TIO_TOKENS_JSON` / `CUSTOM_COMMANDS_JSON` — mais uniquement si le fichier
n'existe pas encore. Collez le contenu brut de chaque fichier dans la
variable correspondante (via le stockage de secrets/variables propre à
l'orchestrateur, ex. le champ `environment` de Komodo), redéployez une fois,
et ensuite ce sont les écritures du bot lui-même (tokens rafraîchis,
`!addcom`/`!delcom`) qui prennent le relais — la variable n'est plus jamais
relue une fois le fichier présent, donc une valeur périmée qui traîne ensuite
dans la config est sans danger.

## Notes de sécurité

- `.env` et `data/` (tokens OAuth Twitch, commandes personnalisées) sont ignorés par git. Ne jamais les committer.
- Les liens fournis par les viewers sont validés par une regex ancrée avant d'atteindre l'API Spotify : seul un ID de morceau base62 de 22 caractères arrive dans une URL.
- Les erreurs des API tierces vont dans les logs, jamais dans le chat public, ce qui éviterait de révéler quel identifiant est cassé.
- Le token Twitch du streamer ne sert qu'à valider ou rembourser la redemption qui l'a déclenché.
- `!addwheel` est ouvert à tout le monde, comme c'était déjà le cas avant la migration twitchio 3 : n'importe quel viewer peut publier du texte arbitraire sur la roue publique du streamer. Ajouter `@commands.is_moderator()` dans `components/wheel.py` pour restreindre.

## TODO

- Héberger le bot sur un serveur pour le garder allumé 24/7.
- `!resetwheel` et `!remove` utilisent `is_moderator()`, qui vérifie le badge de modérateur, le streamer ne l'a pas, il ne peut donc pas utiliser ces commandes. `is_elevated()` couvrirait streamer, modérateurs et VIPs.
- Known issue (antérieure au portage) : la première entrée n'est parfois pas ajoutée à la roue.