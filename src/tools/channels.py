from fastmcp import FastMCP
import discord
from discord import ChannelType
from src.discord_client import ensure_ready, format_error
from pydantic import Field
from typing import Optional
import json

mcp = FastMCP("discord-pilot-channels")

# Mapping nom lisible → ChannelType Discord
_CHANNEL_TYPE_MAP: dict[str, ChannelType] = {
    "text": ChannelType.text,
    "voice": ChannelType.voice,
    "forum": ChannelType.forum,
    "announcement": ChannelType.news,
}

# Mapping inverse ChannelType → label lisible
_TYPE_LABEL: dict[ChannelType, str] = {
    ChannelType.text: "text",
    ChannelType.voice: "voice",
    ChannelType.forum: "forum",
    ChannelType.news: "announcement",
    ChannelType.category: "category",
    ChannelType.stage_voice: "stage",
    ChannelType.public_thread: "thread",
    ChannelType.private_thread: "private_thread",
}


def _type_label(ch: discord.abc.GuildChannel) -> str:
    """Retourne le label lisible du type d'un salon."""
    return _TYPE_LABEL.get(ch.type, str(ch.type))


def _is_nsfw(ch: discord.abc.GuildChannel) -> bool:
    """Retourne True si le salon est marqué NSFW, False sinon."""
    return ch.is_nsfw() if isinstance(ch, (discord.TextChannel, discord.ForumChannel)) else False


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_list_channels(
    guild_id: str = Field(description="ID du serveur Discord"),
    channel_type: Optional[str] = Field(
        default=None,
        description="Filtrer par type : 'text', 'voice', 'forum', 'announcement'. None = tous les types",
    ),
) -> str:
    """Liste tous les salons d'un serveur Discord, groupés par catégorie.

    Retourne pour chaque salon : id, name, type (text/voice/forum/announcement),
    topic, position, is_nsfw, category_name.
    Utilise cet outil pour obtenir les channel_id avant d'envoyer des messages.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id))
        if guild is None:
            return (
                f"❌ Serveur introuvable dans le cache (guild_id={guild_id}). "
                "Utilisez discord_list_guilds pour vérifier les IDs disponibles."
            )

        # Exclure les catégories de la liste principale
        channels: list[discord.abc.GuildChannel] = [
            ch for ch in guild.channels
            if not isinstance(ch, discord.CategoryChannel)
        ]

        # Filtre optionnel par type
        if channel_type:
            filter_type = _CHANNEL_TYPE_MAP.get(channel_type.lower())
            if filter_type is None:
                return (
                    f"❌ Type inconnu '{channel_type}'. "
                    f"Valeurs valides : {list(_CHANNEL_TYPE_MAP.keys())}"
                )
            channels = [ch for ch in channels if ch.type == filter_type]

        channels.sort(key=lambda ch: ch.position)

        # Groupement par catégorie
        grouped: dict[str, list[dict]] = {}
        for ch in channels:
            cat_name = ch.category.name if ch.category else "Sans catégorie"
            grouped.setdefault(cat_name, []).append({
                "id": str(ch.id),
                "name": ch.name,
                "type": _type_label(ch),
                "topic": getattr(ch, "topic", None),
                "position": ch.position,
                "is_nsfw": _is_nsfw(ch),
                "category_name": cat_name,
            })

        return json.dumps(grouped, indent=2, ensure_ascii=False)

    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# Utilise le cache local (client.get_guild) pour éviter des appels API inutiles.
# Le cache est maintenu à jour par le gateway Discord grâce aux intents guilds.


@mcp.tool(annotations={"destructiveHint": False})
async def discord_create_channel(
    guild_id: str = Field(description="ID du serveur Discord"),
    name: str = Field(description="Nom du salon en minuscules avec tirets. Ex: 'general-discussion'"),
    channel_type: str = Field(
        default="text",
        description="Type : 'text', 'voice', 'announcement', 'forum'",
    ),
    topic: Optional[str] = Field(
        default=None,
        description="Description/sujet du salon (max 1024 chars)",
    ),
    category_id: Optional[str] = Field(
        default=None,
        description="ID de la catégorie parente (optionnel)",
    ),
    position: Optional[int] = Field(
        default=None,
        description="Position dans la liste (0 = premier)",
    ),
) -> str:
    """Crée un nouveau salon dans un serveur Discord.

    Peut créer des salons textuels, vocaux ou des annonces.
    Le nom doit être en minuscules avec des tirets (ex: 'mon-salon').
    Retourne l'ID et le nom du salon créé.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        category: Optional[discord.CategoryChannel] = None
        if category_id:
            raw = guild.get_channel(int(category_id))
            if isinstance(raw, discord.CategoryChannel):
                category = raw

        kwargs: dict = {"name": name}
        if category is not None:
            kwargs["category"] = category
        if position is not None:
            kwargs["position"] = position

        channel_type_lower = channel_type.lower()

        if channel_type_lower == "text":
            kwargs["topic"] = topic
            channel = await guild.create_text_channel(**kwargs)

        elif channel_type_lower == "voice":
            channel = await guild.create_voice_channel(**kwargs)

        elif channel_type_lower == "announcement":
            # Nécessite que le serveur ait la fonctionnalité Community activée
            kwargs["topic"] = topic
            channel = await guild.create_text_channel(**kwargs)

        elif channel_type_lower == "forum":
            channel = await guild.create_forum(**kwargs)

        else:
            valid = list(_CHANNEL_TYPE_MAP.keys())
            return f"❌ Type invalide '{channel_type}'. Valeurs valides : {valid}"

        result = {
            "id": str(channel.id),
            "name": channel.name,
            "type": channel_type_lower,
            "topic": getattr(channel, "topic", None),
            "url": f"https://discord.com/channels/{guild_id}/{channel.id}",
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les salons'."
    except ValueError:
        return f"❌ ID invalide. guild_id et category_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# guild.create_text_channel / create_voice_channel / create_forum font des appels
# HTTP vers l'API Discord — le salon est immédiatement visible dans le serveur.


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_edit_channel(
    channel_id: str = Field(description="ID du salon à modifier"),
    name: Optional[str] = Field(default=None, description="Nouveau nom du salon"),
    topic: Optional[str] = Field(default=None, description="Nouveau sujet/description"),
    slowmode_delay: Optional[int] = Field(
        default=None,
        description="Délai en secondes entre messages (0-21600)",
    ),
    position: Optional[int] = Field(default=None, description="Nouvelle position"),
) -> str:
    """Modifie les propriétés d'un salon existant (nom, topic, position, slowmode).

    Seuls les champs fournis sont modifiés, les autres restent inchangés.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))

        kwargs: dict = {}
        if name is not None:
            kwargs["name"] = name
        if topic is not None:
            kwargs["topic"] = topic
        if slowmode_delay is not None:
            kwargs["slowmode_delay"] = slowmode_delay
        if position is not None:
            kwargs["position"] = position

        if not kwargs:
            return "⚠️ Aucune modification spécifiée. Fournissez au moins un champ à modifier."

        await channel.edit(**kwargs)

        result = {
            "id": str(channel.id),
            "name": channel.name,
            "topic": getattr(channel, "topic", None),
            "position": channel.position,
            "slowmode_delay": getattr(channel, "slowmode_delay", None),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Salon introuvable (channel_id={channel_id})."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les salons'."
    except ValueError:
        return f"❌ channel_id invalide : '{channel_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# Seuls les kwargs non-None sont envoyés à channel.edit() — les champs omis
# restent à leur valeur actuelle côté Discord.


@mcp.tool(annotations={"destructiveHint": True})
async def discord_delete_channel(
    channel_id: str = Field(description="ID du salon à supprimer"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la suppression (apparaît dans les logs d'audit du serveur)",
    ),
) -> str:
    """Supprime définitivement un salon Discord. ATTENTION : action irréversible.

    Confirme toujours avant d'utiliser cet outil.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))
        name_backup = channel.name
        id_backup = str(channel.id)

        await channel.delete(reason=reason)

        return json.dumps({
            "deleted": True,
            "id": id_backup,
            "name": name_backup,
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Salon introuvable (channel_id={channel_id}). Peut-être déjà supprimé."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les salons'."
    except ValueError:
        return f"❌ channel_id invalide : '{channel_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# Le nom et l'ID sont sauvegardés avant la suppression pour confirmer
# l'action dans la réponse, car le salon n'existe plus après delete().


@mcp.tool(annotations={"destructiveHint": False})
async def discord_create_category(
    guild_id: str = Field(description="ID du serveur Discord"),
    name: str = Field(description="Nom de la catégorie. Ex: 'GÉNÉRAL'"),
    position: Optional[int] = Field(
        default=None,
        description="Position de la catégorie dans la liste (0 = premier)",
    ),
) -> str:
    """Crée une nouvelle catégorie pour organiser les salons d'un serveur."""
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        kwargs: dict = {"name": name}
        if position is not None:
            kwargs["position"] = position

        category = await guild.create_category(**kwargs)

        result = {
            "id": str(category.id),
            "name": category.name,
            "position": category.position,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les salons'."
    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# Une catégorie est un type de salon particulier (CategoryChannel) —
# elle sert de conteneur visuel pour regrouper d'autres salons.
