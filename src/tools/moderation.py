from fastmcp import FastMCP
import discord
from src.discord_client import ensure_ready, format_error
from pydantic import Field
from typing import Optional
from datetime import timedelta
import json

mcp = FastMCP("discord-pilot-moderation")

# Mapping string lisible → discord.AuditLogAction
_AUDIT_ACTION_MAP: dict[str, discord.AuditLogAction] = {
    "kick": discord.AuditLogAction.kick,
    "ban": discord.AuditLogAction.ban,
    "unban": discord.AuditLogAction.unban,
    "member_update": discord.AuditLogAction.member_update,
    "channel_create": discord.AuditLogAction.channel_create,
    "channel_delete": discord.AuditLogAction.channel_delete,
    "role_create": discord.AuditLogAction.role_create,
    "role_delete": discord.AuditLogAction.role_delete,
    "message_delete": discord.AuditLogAction.message_delete,
}


def _target_str(target) -> Optional[str]:
    """Convertit la cible d'un log d'audit en chaîne lisible."""
    if target is None:
        return None
    if hasattr(target, "name"):
        return f"{target.name} ({target.id})"
    if hasattr(target, "id"):
        return str(target.id)
    return str(target)


@mcp.tool(annotations={"destructiveHint": True})
async def discord_kick_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur à expulser"),
    reason: str = Field(
        default="Aucune raison fournie",
        description="Raison du kick (visible dans les logs d'audit)",
    ),
) -> str:
    """Expulse un membre du serveur Discord (il peut revenir avec une invitation).

    Le bot doit avoir la permission Kick Members.
    La raison apparaît dans les logs d'audit du serveur.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

        if member.id == client.user.id:
            return "❌ Le bot ne peut pas s'expulser lui-même."

        if member.id == guild.owner_id:
            return "❌ Impossible d'expulser le propriétaire du serveur."

        username = str(member)
        await member.kick(reason=reason)

        return json.dumps({
            "success": True,
            "action": "kick",
            "user_id": user_id,
            "username": username,
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Expulser des membres' "
            "et son rôle doit être supérieur à celui du membre ciblé."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# Le kick est réversible : le membre expulsé peut revenir via invitation.
# Pour une sanction permanente, utilisez discord_ban_member.


@mcp.tool(annotations={"destructiveHint": True})
async def discord_ban_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur à bannir"),
    reason: str = Field(
        default="Aucune raison fournie",
        description="Raison du ban (visible dans les logs d'audit)",
    ),
    delete_message_days: int = Field(
        default=0,
        ge=0,
        le=7,
        description="Nombre de jours de messages à supprimer (0-7)",
    ),
) -> str:
    """Bannit définitivement un membre du serveur Discord.

    Le membre banni ne peut plus rejoindre le serveur sauf si le ban est levé.
    Option pour supprimer les messages récents du membre (jusqu'à 7 jours).
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        if int(user_id) == client.user.id:
            return "❌ Le bot ne peut pas se bannir lui-même."

        if int(user_id) == guild.owner_id:
            return "❌ Impossible de bannir le propriétaire du serveur."

        # Tente de récupérer le membre pour son username (peut ne plus être dans le serveur)
        username = f"Utilisateur#{user_id}"
        member = guild.get_member(int(user_id))
        if member:
            username = str(member)

        # discord.Object fonctionne même si l'utilisateur a déjà quitté le serveur
        await guild.ban(
            discord.Object(id=int(user_id)),
            reason=reason,
            delete_message_seconds=delete_message_days * 86400,
        )

        return json.dumps({
            "success": True,
            "action": "ban",
            "user_id": user_id,
            "username": username,
            "reason": reason,
            "messages_deleted_days": delete_message_days,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Utilisateur introuvable (user_id={user_id})."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Bannir des membres' "
            "et son rôle doit être supérieur à celui du membre ciblé."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# guild.ban() accepte discord.Object — pas besoin que le membre soit présent
# sur le serveur. Utile pour bannir quelqu'un qui a déjà fui.


@mcp.tool(annotations={"destructiveHint": False})
async def discord_unban_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur à débannir"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la levée du ban (logs d'audit)",
    ),
) -> str:
    """Lève le bannissement d'un utilisateur Discord.

    L'utilisateur pourra rejoindre le serveur à nouveau via invitation.
    Utilisez discord_get_audit_logs avec action_type='ban' pour trouver
    les user_id des membres bannis.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        # Vérifie que le ban existe avant de tenter le unban
        try:
            ban_entry = await guild.fetch_ban(discord.Object(id=int(user_id)))
            username = str(ban_entry.user)
        except discord.NotFound:
            return f"❌ Aucun ban trouvé pour l'utilisateur (user_id={user_id}) sur ce serveur."

        await guild.unban(discord.Object(id=int(user_id)), reason=reason)

        return json.dumps({
            "success": True,
            "action": "unban",
            "user_id": user_id,
            "username": username,
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Bannir des membres'."
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# guild.fetch_ban() vérifie l'existence du ban avant d'appeler unban() —
# évite une erreur NotFound confuse si l'utilisateur n'était pas banni.


@mcp.tool(annotations={"destructiveHint": False})
async def discord_timeout_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur à mettre en timeout"),
    duration_minutes: int = Field(
        ge=0,
        le=40320,
        description="Durée en minutes (0 = retirer le timeout, max 40320 = 28 jours)",
    ),
    reason: Optional[str] = Field(
        default=None,
        description="Raison du timeout (logs d'audit)",
    ),
) -> str:
    """Met un membre en timeout (silence temporaire) dans le serveur.

    Un membre en timeout ne peut pas parler, réagir ou rejoindre des vocaux.
    Durée max : 28 jours (40320 minutes).
    Pour retirer le timeout, utilise duration_minutes=0.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))
        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))

        if member.id == client.user.id:
            return "❌ Le bot ne peut pas se mettre en timeout lui-même."

        if member.id == guild.owner_id:
            return "❌ Impossible de mettre en timeout le propriétaire du serveur."

        if duration_minutes == 0:
            await member.edit(timed_out_until=None, reason=reason)
            return json.dumps({
                "success": True,
                "action": "timeout_removed",
                "user_id": user_id,
                "username": str(member),
            }, indent=2, ensure_ascii=False)

        until = discord.utils.utcnow() + timedelta(minutes=duration_minutes)
        await member.edit(timed_out_until=until, reason=reason)

        days = duration_minutes // 1440
        hours = (duration_minutes % 1440) // 60
        mins = duration_minutes % 60
        duration_str = f"{days}j {hours}h {mins}m".strip()

        return json.dumps({
            "success": True,
            "action": "timeout_applied",
            "user_id": user_id,
            "username": str(member),
            "duration_minutes": duration_minutes,
            "duration_human": duration_str,
            "expires_at": until.isoformat(),
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Modérer les membres' "
            "et son rôle doit être supérieur à celui du membre ciblé."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et user_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# Le timeout utilise timed_out_until (timestamp UTC) — Discord retire
# automatiquement le silence à l'expiration, sans action supplémentaire.


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_get_audit_logs(
    guild_id: str = Field(description="ID du serveur Discord"),
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Nombre d'entrées à récupérer (1-100)",
    ),
    action_type: Optional[str] = Field(
        default=None,
        description=(
            "Filtrer par type d'action : "
            "'kick', 'ban', 'unban', 'member_update', "
            "'channel_create', 'channel_delete', 'role_create', 'role_delete', 'message_delete'"
        ),
    ),
) -> str:
    """Récupère les logs d'audit du serveur (actions de modération récentes).

    Retourne : action type, utilisateur responsable, cible, raison, date.
    Utile pour auditer les actions de modération et retrouver des user_id bannis.
    Nécessite la permission 'Voir les logs d'audit'.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        kwargs: dict = {"limit": limit}

        if action_type:
            action = _AUDIT_ACTION_MAP.get(action_type.lower())
            if action is None:
                valid = list(_AUDIT_ACTION_MAP.keys())
                return (
                    f"❌ Type d'action inconnu : '{action_type}'. "
                    f"Valeurs valides : {valid}"
                )
            kwargs["action"] = action

        entries = []
        async for entry in guild.audit_logs(**kwargs):
            entries.append({
                "id": str(entry.id),
                "action": str(entry.action).replace("AuditLogAction.", ""),
                "moderator_id": str(entry.user.id) if entry.user else None,
                "moderator_name": str(entry.user) if entry.user else None,
                "target": _target_str(entry.target),
                "reason": entry.reason,
                "created_at": entry.created_at.isoformat(),
            })

        return json.dumps({
            "guild_id": guild_id,
            "count": len(entries),
            "entries": entries,
        }, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Voir les logs d'audit'."
    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# guild.audit_logs() est un AsyncIterator paginé côté API Discord.
# Sans filtre action, retourne toutes les actions triées du plus récent au plus ancien.
