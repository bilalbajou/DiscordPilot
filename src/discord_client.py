import asyncio
import logging
import os
import threading

import discord
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_client: discord.Client | None = None
_ready: asyncio.Event | None = None
_bot_loop: asyncio.AbstractEventLoop | None = None

# threading.Event pour la synchronisation cross-thread dans get_client() (sync)
_thread_ready = threading.Event()
_init_lock = threading.Lock()


def get_client() -> discord.Client:
    """Retourne le client Discord singleton, en le créant si nécessaire.

    Lance le bot dans un thread daemon avec son propre event loop asyncio.
    Bloque jusqu'à ce que le bot soit connecté et prêt (on_ready déclenché).

    Raises:
        ValueError: Si DISCORD_BOT_TOKEN n'est pas défini dans .env.
        RuntimeError: Si le bot ne démarre pas dans les 30 secondes.
    """
    global _client, _ready, _bot_loop

    if _client is not None:
        return _client

    with _init_lock:
        if _client is not None:
            return _client

        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError(
                "DISCORD_BOT_TOKEN non défini. "
                "Copie .env.example vers .env et renseigne ton token."
            )

        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.members = True
        intents.message_content = True
        intents.moderation = True

        client = discord.Client(intents=intents)

        def run_bot():
            """Cible du thread daemon : crée un event loop et démarre le bot."""
            global _bot_loop, _ready, _client

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _bot_loop = loop
            _ready = asyncio.Event()

            @client.event
            async def on_ready():
                logger.info("✅ DiscordPilot connecté en tant que %s", client.user)
                _ready.set()
                _thread_ready.set()

            try:
                loop.run_until_complete(client.start(token))
            except Exception as exc:
                logger.error("❌ Erreur démarrage bot Discord : %s", exc)
                _thread_ready.set()  # débloque get_client() même en cas d'erreur

        _client = client
        thread = threading.Thread(target=run_bot, daemon=True, name="discord-bot")
        thread.start()

        connected = _thread_ready.wait(timeout=30)
        if not connected:
            raise RuntimeError(
                "Timeout : le bot Discord n'a pas démarré dans les 30 secondes. "
                "Vérifie ton DISCORD_BOT_TOKEN."
            )

        return _client


async def ensure_ready() -> discord.Client:
    """Retourne le client Discord une fois qu'il est prêt à recevoir des commandes.

    Appelle get_client() dans un executor pour ne pas bloquer l'event loop
    async (FastMCP), puis attend que le bot soit pleinement connecté.

    Returns:
        Le discord.Client connecté et prêt.
    """
    loop = asyncio.get_event_loop()
    client = await loop.run_in_executor(None, get_client)
    await client.wait_until_ready()
    return client


def format_error(e: Exception) -> str:
    """Formate une exception Discord en message d'erreur lisible pour l'utilisateur.

    Args:
        e: L'exception levée lors d'un appel à l'API Discord.

    Returns:
        Un message d'erreur préfixé ❌ avec le type et la cause.
    """
    if isinstance(e, discord.Forbidden):
        return (
            f"❌ Forbidden: {e.text}. "
            "Vérifiez les permissions du bot sur ce serveur."
        )
    if isinstance(e, discord.NotFound):
        return (
            f"❌ NotFound: {e.text}. "
            "La ressource demandée est introuvable (ID incorrect ?)."
        )
    if isinstance(e, discord.HTTPException):
        return f"❌ HTTPException ({e.status}): {e.text}."
    return f"❌ {type(e).__name__}: {e}"


if __name__ == "__main__":
    async def _test():
        print("Connexion au bot Discord...")
        client = await ensure_ready()
        print(f"✅ Connecté en tant que : {client.user}")
        print(f"   Serveurs accessibles : {len(client.guilds)}")
        for g in client.guilds:
            print(f"   • [{g.id}] {g.name} — {g.member_count} membres")

    asyncio.run(_test())
