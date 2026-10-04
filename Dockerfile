FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install poetry

# Only the dependency manifest first, so this layer stays cached unless
# dependencies actually change. `poetry lock` regenerates poetry.lock here
# instead of trusting the committed one, which predates the twitchio 3
# migration (see README) and would otherwise install twitchio 2.x.
COPY pyproject.toml ./
RUN poetry lock && poetry install --no-root --only main

COPY . .

# Everything written at runtime (Twitch OAuth tokens, custom commands) lives
# under /app/data: mount a volume there so it survives restarts/redeploys.
# The first run also needs port 4343 published so http://localhost:4343/oauth
# is reachable from the browser used to authorize the bot and streamer accounts.
VOLUME ["/app/data"]
EXPOSE 4343

CMD ["python", "main.py"]
