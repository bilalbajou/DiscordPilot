from fastmcp import FastMCP
import discord
from src.discord_client import ensure_ready, format_error
from pydantic import Field
from typing import Optional
import json

mcp = FastMCP("discord-pilot-roles")


def _color_to_hex(color: discord.Color) -> str:
    """Convertit un discord.Color en chaîne hexadécimale #RRGGBB."""
    return f"#{color.value:06X}"


def _parse_color(hex_str: str) -> discord.Color:
    """Convertit une chaîne hex ('FF5733' ou '#FF5733') en discord.Color.

    Raises:
        ValueError: Si la chaîne n'est pas un hex valide.
    """
    cleaned = hex_str.lstrip("#").strip()
    if len(cleaned) != 6:
        raise ValueError(f"Couleur hex invalide : '{hex_str}'. Format attendu : '#RRGGBB' ou 'RRGGBB'.")
    return discord.Color(int(cleaned, 16))


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_list_roles(
    guild_id: str = Field(description="ID du serveur Discord"),
) -> str:
    """Liste tous les rôles d'un serveur Discord, triés par position hiérarchique.

    Retourne : id, name, color (hex), hoist (affiché séparément),
    mentionable, managed (bot role), position, member_count estimé.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id))
        if guild is None:
            return (
                f"❌ Serveur introuvable dans le cache (guild_id={guild_id}). "
                "Utilisez discord_list_guilds pour vérifier les IDs disponibles."
            )

        # Tri décroissant par position (rôle le plus haut en premier)
        # Exclut @everyone (toujours à la position 0)
        roles = sorted(
            [r for r in guild.roles if r.name != "@everyone"],
            key=lambda r: r.position,
            reverse=True,
        )

        result = []
        for role in roles:
            result.append({
                "id": str(role.id),
                "name": role.name,
                "color": _color_to_hex(role.color),
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "managed": role.managed,
                "position": role.position,
                "member_count": len(role.members),
            })

        return json.dumps(result, indent=2, ensure_ascii=False)

    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# guild.roles utilise le cache local maintenu par le gateway Discord.
# role.members nécessite l'intent members (activé dans discord_client.py).


@mcp.tool(annotations={"destructiveHint": False})
async def discord_create_role(
    guild_id: str = Field(description="ID du serveur Discord"),
    name: str = Field(description="Nom du rôle"),
    color: Optional[str] = Field(
        default=None,
        description="Couleur en hex. Ex: '#FF5733' ou 'FF5733'",
    ),
    hoist: bool = Field(
        default=False,
        description="Afficher le rôle séparément dans la liste des membres",
    ),
    mentionable: bool = Field(
        default=False,
        description="Permettre à tous de mentionner ce rôle",
    ),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la création (logs d'audit)",
    ),
) -> str:
    """Crée un nouveau rôle dans un serveur Discord.

    Le rôle est créé en bas de la hiérarchie par défaut.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        discord_color = discord.Color.default()
        if color:
            try:
                discord_color = _parse_color(color)
            except ValueError as ve:
                return f"❌ {ve}"

        role = await guild.create_role(
            name=name,
            color=discord_color,
            hoist=hoist,
            mentionable=mentionable,
            reason=reason,
        )

        result = {
            "id": str(role.id),
            "name": role.name,
            "color": _color_to_hex(role.color),
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les rôles'."
    except ValueError:
        return f"❌ guild_id invalide : '{guild_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# guild.create_role() place le rôle en position 1 (juste au-dessus de @everyone).
# Pour le repositionner, utilisez role.edit(position=N) après création.


@mcp.tool(annotations={"destructiveHint": False})
async def discord_add_role_to_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur Discord"),
    role_id: str = Field(description="ID du rôle à attribuer"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de l'attribution (logs d'audit)",
    ),
) -> str:
    """Attribue un rôle à un membre d'un serveur Discord.

    Le bot doit avoir un rôle supérieur au rôle à attribuer dans la hiérarchie.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
        role = guild.get_role(int(role_id))

        if role is None:
            return f"❌ Rôle introuvable (role_id={role_id}). Vérifiez l'ID avec discord_list_roles."

        await member.add_roles(role, reason=reason)

        return json.dumps({
            "success": True,
            "action": "role_added",
            "user_id": str(member.id),
            "username": str(member),
            "role_id": str(role.id),
            "role_name": role.name,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les rôles' "
            "et son rôle doit être supérieur au rôle à attribuer."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id, user_id et role_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# member.add_roles() est idempotent : attribuer un rôle déjà présent ne lève pas d'erreur.


@mcp.tool(annotations={"destructiveHint": False})
async def discord_remove_role_from_member(
    guild_id: str = Field(description="ID du serveur Discord"),
    user_id: str = Field(description="ID de l'utilisateur Discord"),
    role_id: str = Field(description="ID du rôle à retirer"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison du retrait (logs d'audit)",
    ),
) -> str:
    """Retire un rôle d'un membre.

    Le bot doit avoir un rôle supérieur au rôle à retirer dans la hiérarchie.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        member = guild.get_member(int(user_id)) or await guild.fetch_member(int(user_id))
        role = guild.get_role(int(role_id))

        if role is None:
            return f"❌ Rôle introuvable (role_id={role_id}). Vérifiez l'ID avec discord_list_roles."

        await member.remove_roles(role, reason=reason)

        return json.dumps({
            "success": True,
            "action": "role_removed",
            "user_id": str(member.id),
            "username": str(member),
            "role_id": str(role.id),
            "role_name": role.name,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Membre introuvable (user_id={user_id}) sur ce serveur."
    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les rôles' "
            "et son rôle doit être supérieur au rôle à retirer."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id, user_id et role_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# member.remove_roles() est idempotent : retirer un rôle absent ne lève pas d'erreur.


@mcp.tool(annotations={"destructiveHint": True})
async def discord_delete_role(
    guild_id: str = Field(description="ID du serveur Discord"),
    role_id: str = Field(description="ID du rôle à supprimer"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la suppression (logs d'audit)",
    ),
) -> str:
    """Supprime définitivement un rôle du serveur. ATTENTION : irréversible.

    Les membres ayant ce rôle le perdront automatiquement.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        role = guild.get_role(int(role_id))
        if role is None:
            return f"❌ Rôle introuvable (role_id={role_id}). Vérifiez l'ID avec discord_list_roles."

        if role.managed:
            return (
                f"❌ Le rôle '{role.name}' est géré par une intégration bot/externe "
                "et ne peut pas être supprimé manuellement."
            )

        name_backup = role.name
        id_backup = str(role.id)
        affected_members = len(role.members)

        await role.delete(reason=reason)

        return json.dumps({
            "deleted": True,
            "id": id_backup,
            "name": name_backup,
            "affected_members": affected_members,
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les rôles' "
            "et son rôle doit être supérieur au rôle à supprimer."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et role_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# Les rôles managed=True (intégrations, bots) sont protégés — Discord refuse
# leur suppression via API, d'où la vérification préventive avant role.delete().


@mcp.tool(annotations={"destructiveHint": False})
async def discord_update_role_permissions(
    guild_id: str = Field(description="ID du serveur Discord"),
    role_id: str = Field(description="ID du rôle à modifier"),
    permissions: dict[str, bool] = Field(
        description="Dictionnaire des permissions à modifier (ex: {'manage_messages': true, 'kick_members': false})"
    ),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la modification (logs d'audit)",
    ),
) -> str:
    """Met à jour les permissions d'un rôle.

    Les permissions non spécifiées dans le dictionnaire resteront inchangées.
    Noms de permissions valides (snake_case) : administrator, manage_guild, manage_channels, manage_roles, manage_messages, kick_members, ban_members, etc.
    """
    try:
        client = await ensure_ready()

        guild = client.get_guild(int(guild_id)) or await client.fetch_guild(int(guild_id))

        role = guild.get_role(int(role_id))
        if role is None:
            return f"❌ Rôle introuvable (role_id={role_id}). Vérifiez l'ID avec discord_list_roles."

        perms = role.permissions
        
        # update() on discord.Permissions updates the values based on kwargs
        try:
            perms.update(**permissions)
        except TypeError as e:
            return f"❌ Nom de permission invalide : {str(e)}"

        await role.edit(permissions=perms, reason=reason)

        return json.dumps({
            "success": True,
            "id": str(role.id),
            "name": role.name,
            "updated_permissions": permissions
        }, indent=2, ensure_ascii=False)

    except discord.Forbidden:
        return (
            "❌ Permission refusée. Le bot doit avoir la permission 'Gérer les rôles' "
            "et son rôle doit être supérieur au rôle à modifier."
        )
    except ValueError:
        return "❌ IDs invalides : guild_id et role_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)
