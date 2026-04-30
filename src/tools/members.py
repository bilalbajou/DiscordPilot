from fastmcp import FastMCP
import discord
from src.discord_client import ensure_ready, format_error
from pydantic import Field
from typing import Optional
import json

mcp = FastMCP("discord-pilot-members")


def _serialize_member(member: discord.Member) -> dict:
    """Sérialise un discord.Member en dict JSON-friendly."""
    roles = [
        {"id": str(r.id), "name": r.name}
        for r in sorted(member.roles, key=lambda r: r.position, reverse=True)
        if r.name != "@everyone"
    ]
    return {
        "id": str(member.id),
        "username": member.name,
        "display_name": member.display_name,
        "nickname": member.nick,
        "bot": member.bot,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "account_created_at": member.created_at.isoformat(),
        "top_role": roles[0]["name"] if roles else "@everyone",
        "roles": roles,
        "role_count": len(roles),
        "is_booster": member.premium_since is not None,
        "boosting_since": member.premium_since.isoformat() if member.premium_since else None,
        "pending_verification": member.pending,
        "avatar_url": str(member.display_avatar.url),
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_list_members(
    guild_id: str = Field(description="ID du serveur Discord"),
    limit: int = Field(
        default=50,
        description="Nombre maximum de membres à retourner (1-500)",
    ),
    role_id: Optional[str] = Field(
        default=None,
        description="Filtrer par rôle : retourne uniquement les membres ayant ce rôle",
    ),
    bots_only: bool = Field(
        default=False,
        description="Si True, retourne uniquement les bots du serveur",
    ),
    humans_only: bool = Field(
        default=False,
        description="Si True, exclut les bots et retourne uniquement les membres humains",
    ),
) -> str:
    """Liste les membres d'un serveur Discord avec filtres optionnels.

    Retourne : id, username, display_name, nickname, roles, date d'arrivée.
    Utilise role_id pour lister les membres d'un rôle spécifique.
    Pour les grands serveurs (>1000 membres), préférez discord_search_members.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id))
        if guild is None:
            return (
                f"❌ Serveur introuvable dans le cache (guild_id={guild_id}). "
                "Utilisez discord_list_guilds pour vérifier les IDs disponibles."
            )

        limit = max(1, min(limit, 500))

        # Filtre par rôle via le cache si disponible, sinon via fetch
        filter_role: Optional[discord.Role] = None
        if role_id:
            filter_role = guild.get_role(int(role_id))
            if filter_role is None:
                return f"❌ Rôle introuvable (role_id={role_id}). Vérifiez l'ID avec discord_list_roles."

        # Récupération des membres depuis le cache (membres intent activé)
        members = list(guild.members)

        if filter_role:
            members = [m for m in members if filter_role in m.roles]
        if bots_only:
            members = [m for m in members if m.bot]
        elif humans_only:
            members = [m for m in members if not m.bot]

        # Tri par date d'arrivée (les plus récents en premier)
        members.sort(key=lambda m: m.joined_at or m.created_at, reverse=True)
        members = members[:limit]

        result = [_serialize_member(m) for m in members]
        return json.dumps(result, indent=2, ensure_ascii=False)

    except ValueError:
        return "❌ IDs invalides : guild_id et role_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# guild.members utilise le cache gateway (intent members requis).
# Sur les grands serveurs, le cache peut être incomplet si le bot vient
# de redémarrer — attendez que on_ready soit déclenché complètement.


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_get_member_info(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur Discord"),
) -> str:
    """Récupère les informations détaillées d'un membre spécifique.

    Retourne : username, display_name, nickname, tous ses rôles (triés par
    hiérarchie), dates d'arrivée et de création du compte, statut booster,
    avatar URL. Utilise cet outil avant d'attribuer ou retirer un rôle.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        # Essaie le cache, sinon appel API
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

        return json.dumps(_serialize_member(member), indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# fetch_member() fait un appel API et retourne un objet complet même si le
# membre n'est pas dans le cache local — utile après un redémarrage du bot.


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_search_members(
    guild_id: str = Field(description="ID du serveur Discord"),
    query: str = Field(
        description="Texte à rechercher dans le username ou le nickname (min 2 caractères)"
    ),
    limit: int = Field(
        default=10,
        description="Nombre maximum de résultats (1-100)",
    ),
) -> str:
    """Recherche des membres par username ou nickname sur un serveur Discord.

    La recherche est insensible à la casse et correspond aux préfixes.
    Retourne les membres dont le username ou nickname commence par la query.
    Idéal pour trouver l'ID d'un membre avant d'effectuer une action.
    """
    try:
        client = await ensure_ready()

        if len(query.strip()) < 2:
            return "❌ La recherche doit contenir au moins 2 caractères."

        limit = max(1, min(limit, 100))

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        # guild.search_members() fait un appel API optimisé (discord.py 2.0+)
        members = await guild.search_members(query=query, limit=limit)

        if not members:
            return json.dumps({"results": [], "query": query, "count": 0}, indent=2)

        result = {
            "query": query,
            "count": len(members),
            "results": [_serialize_member(m) for m in members],
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# guild.search_members() utilise l'endpoint /guilds/{id}/members/search
# qui recherche côté serveur Discord — plus fiable que filtrer le cache local
# surtout sur les grands serveurs.


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_edit_member_nickname(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur Discord"),
    nickname: Optional[str] = Field(
        default=None,
        description="Nouveau nickname (max 32 caractères). None ou vide = réinitialise au username",
    ),
    reason: Optional[str] = Field(
        default=None,
        description="Raison du changement (logs d'audit)",
    ),
) -> str:
    """Modifie le surnom (nickname) d'un membre sur un serveur Discord.

    Passer nickname=None ou une chaîne vide réinitialise le surnom
    au username d'origine. Le bot peut modifier son propre surnom
    sans permission spéciale, mais nécessite 'Gérer les pseudonymes'
    pour modifier celui des autres membres.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

        # Chaîne vide → None pour réinitialiser
        new_nick = nickname.strip() if nickname and nickname.strip() else None

        old_nick = member.nick
        await member.edit(nick=new_nick, reason=reason)

        return json.dumps({
            "success": True,
            "user_id": str(member.id),
            "username": member.name,
            "old_nickname": old_nick,
            "new_nickname": new_nick,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les pseudonymes'. "
            "Il ne peut pas non plus modifier le surnom d'un membre avec un rôle supérieur au sien."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# member.edit(nick=None) réinitialise le surnom — passer une string vide
# ne suffit pas, il faut explicitement None pour l'API Discord.


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_get_member_roles(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur Discord"),
) -> str:
    """Retourne la liste détaillée des rôles d'un membre spécifique.

    Triée par position hiérarchique décroissante (rôle le plus élevé en premier).
    Inclut pour chaque rôle : id, name, color, hoist, managed, position.
    Utilise cet outil pour vérifier les permissions d'un membre avant une action.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

        roles = sorted(
            [r for r in member.roles if r.name != "@everyone"],
            key=lambda r: r.position,
            reverse=True,
        )

        result = {
            "user_id": str(member.id),
            "username": member.name,
            "display_name": member.display_name,
            "role_count": len(roles),
            "top_role": roles[0].name if roles else "@everyone",
            "roles": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "color": f"#{r.color.value:06X}",
                    "hoist": r.hoist,
                    "managed": r.managed,
                    "position": r.position,
                }
                for r in roles
            ],
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# member.roles inclut @everyone — filtré ici car il est implicite pour tous
# les membres et n'apporte pas d'information utile dans ce contexte.
