from fastmcp import FastMCP
import discord
from src.discord_client import ensure_ready, format_error
from pydantic import BaseModel, Field
import json

mcp = FastMCP("discord-pilot-guilds")


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_list_guilds() -> str:
    """Liste tous les serveurs Discord où le bot DiscordPilot est présent.

    Retourne pour chaque serveur : son ID, son nom, le nombre de membres,
    la date de création, et si le bot est owner.
    Utilise cet outil pour découvrir les guild_id disponibles avant
    d'appeler d'autres tools.
    """
    try:
        client = await ensure_ready()

        guilds = []
        for guild in client.guilds:
            guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count,
                "created_at": guild.created_at.isoformat(),
                "owner_id": str(guild.owner_id),
            })

        return json.dumps(guilds, indent=2, ensure_ascii=False)

    except Exception as e:
        return format_error(e)

# Itère sur le cache local client.guilds (pas d'appel API) — rapide
# et suffisant pour lister les serveurs connus du bot.


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_get_guild_info(
    guild_id: str = Field(
        description="L'ID numérique du serveur Discord. Ex: '123456789012345678'"
    ),
) -> str:
    """Récupère les informations détaillées d'un serveur Discord spécifique.

    Retourne : nom, description, nombre de membres, nombre de salons,
    nombre de rôles, niveau de vérification, date de création, icône URL.
    Nécessite un guild_id valide obtenu via discord_list_guilds.
    """
    try:
        client = await ensure_ready()

        guild = await client.fetch_guild(int(guild_id), with_counts=True)

        icon_url = str(guild.icon.url) if guild.icon else None

        info = {
            "id": str(guild.id),
            "name": guild.name,
            "description": guild.description,
            "member_count": guild.approximate_member_count,
            "online_count": guild.approximate_presence_count,
            "channel_count": len(guild.channels) if hasattr(guild, "channels") else None,
            "role_count": len(guild.roles) if hasattr(guild, "roles") else None,
            "verification_level": str(guild.verification_level),
            "created_at": guild.created_at.isoformat(),
            "owner_id": str(guild.owner_id),
            "icon_url": icon_url,
        }

        return json.dumps(info, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Serveur introuvable (guild_id={guild_id}). Vérifiez l'ID avec discord_list_guilds."
    except discord.Forbidden:
        return f"❌ Accès refusé au serveur (guild_id={guild_id}). Le bot n'a pas les permissions nécessaires."
    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# fetch_guild() fait un appel API direct — plus précis que le cache local,
# avec with_counts=True pour récupérer le nombre de membres et d'online.
