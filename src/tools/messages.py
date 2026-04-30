from fastmcp import FastMCP
import discord
from src.discord_client import ensure_ready, format_error
from pydantic import Field
from typing import Optional
import json

mcp = FastMCP("discord-pilot-messages")


def _serialize_message(msg: discord.Message) -> dict:
    """Sérialise un discord.Message en dict JSON-friendly."""
    return {
        "id": str(msg.id),
        "content": msg.content,
        "author_id": str(msg.author.id),
        "author_name": str(msg.author),
        "channel_id": str(msg.channel.id),
        "created_at": msg.created_at.isoformat(),
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "pinned": msg.pinned,
        "has_attachments": len(msg.attachments) > 0,
        "attachment_urls": [a.url for a in msg.attachments],
        "reaction_count": sum(r.count for r in msg.reactions),
        "url": msg.jump_url,
    }


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_send_message(
    channel_id: str = Field(description="ID du salon où envoyer le message"),
    content: str = Field(description="Contenu du message (max 2000 caractères)"),
    reply_to_message_id: Optional[str] = Field(
        default=None,
        description="ID d'un message auquel répondre (crée un fil de réponse)",
    ),
    silent: bool = Field(
        default=False,
        description="Si True, envoie sans notification push pour les membres",
    ),
) -> str:
    """Envoie un message texte dans un salon Discord.

    Supporte les réponses à un message existant et l'envoi silencieux.
    Retourne l'ID, le contenu et l'URL du message envoyé.
    Utilise discord_list_channels pour obtenir un channel_id valide.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel | discord.Thread | discord.DMChannel):
            return f"❌ Le salon (channel_id={channel_id}) ne supporte pas l'envoi de messages texte."

        kwargs: dict = {"content": content}

        if reply_to_message_id:
            ref_msg = await channel.fetch_message(int(reply_to_message_id))
            kwargs["reference"] = ref_msg

        if silent:
            kwargs["silent"] = True

        sent = await channel.send(**kwargs)

        return json.dumps(_serialize_message(sent), indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Salon ou message de référence introuvable (channel_id={channel_id})."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Envoyer des messages' dans ce salon."
    except ValueError:
        return "❌ IDs invalides : channel_id et reply_to_message_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# channel.send() accepte silent=True depuis discord.py 2.4 (correspond au flag
# SUPPRESS_NOTIFICATIONS de l'API Discord).


@mcp.tool(annotations={"readOnlyHint": True})
async def discord_get_messages(
    channel_id: str = Field(description="ID du salon à lire"),
    limit: int = Field(
        default=25,
        description="Nombre de messages à récupérer (1-100)",
    ),
    before_message_id: Optional[str] = Field(
        default=None,
        description="Récupère les messages antérieurs à cet ID (pagination)",
    ),
    after_message_id: Optional[str] = Field(
        default=None,
        description="Récupère les messages postérieurs à cet ID (pagination)",
    ),
) -> str:
    """Récupère l'historique des messages d'un salon Discord.

    Retourne jusqu'à 100 messages avec leur contenu, auteur, date et réactions.
    Utilise before_message_id / after_message_id pour paginer dans l'historique.
    Les messages sont retournés du plus récent au plus ancien.
    """
    try:
        client = await ensure_ready()

        limit = max(1, min(limit, 100))

        channel = await client.fetch_channel(int(channel_id))

        kwargs: dict = {"limit": limit}
        if before_message_id:
            kwargs["before"] = discord.Object(id=int(before_message_id))
        if after_message_id:
            kwargs["after"] = discord.Object(id=int(after_message_id))

        messages = [msg async for msg in channel.history(**kwargs)]

        result = [_serialize_message(msg) for msg in messages]
        return json.dumps(result, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Salon introuvable (channel_id={channel_id})."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Lire l'historique des messages'."
    except ValueError:
        return "❌ IDs invalides : channel_id et before/after_message_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# channel.history() retourne un AsyncIterator — la list comprehension async
# collecte tous les messages en une seule passe sans les stocker côté Discord.


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_edit_message(
    channel_id: str = Field(description="ID du salon contenant le message"),
    message_id: str = Field(description="ID du message à modifier"),
    new_content: str = Field(description="Nouveau contenu du message (max 2000 caractères)"),
) -> str:
    """Modifie le contenu d'un message envoyé par le bot.

    Seuls les messages dont le bot est l'auteur peuvent être modifiés.
    Retourne le message mis à jour avec sa date d'édition.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))

        if message.author.id != client.user.id:
            return (
                f"❌ Impossible de modifier ce message : "
                f"il appartient à '{message.author}', pas au bot."
            )

        edited = await message.edit(content=new_content)

        return json.dumps(_serialize_message(edited), indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Message introuvable (message_id={message_id} dans channel_id={channel_id})."
    except discord.Forbidden:
        return "❌ Permission refusée pour modifier ce message."
    except ValueError:
        return "❌ IDs invalides : channel_id et message_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# Discord n'autorise l'édition que des messages dont on est l'auteur —
# la vérification préventive évite une Forbidden peu claire.


@mcp.tool(annotations={"destructiveHint": True})
async def discord_delete_message(
    channel_id: str = Field(description="ID du salon contenant le message"),
    message_id: str = Field(description="ID du message à supprimer"),
    reason: Optional[str] = Field(
        default=None,
        description="Raison de la suppression (logs d'audit)",
    ),
) -> str:
    """Supprime un message dans un salon Discord. ATTENTION : action irréversible.

    Le bot peut supprimer ses propres messages ou ceux d'autres membres
    s'il a la permission 'Gérer les messages'.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))

        author_name = str(message.author)
        content_preview = message.content[:80] + "…" if len(message.content) > 80 else message.content

        await message.delete(reason=reason)

        return json.dumps({
            "deleted": True,
            "message_id": message_id,
            "author": author_name,
            "content_preview": content_preview,
            "reason": reason,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Message introuvable (message_id={message_id}). Peut-être déjà supprimé."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir 'Gérer les messages' pour supprimer les messages d'autres membres."
    except ValueError:
        return "❌ IDs invalides : channel_id et message_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# L'aperçu du contenu est capturé avant delete() car le message n'existe
# plus après — utile pour confirmer quelle action a été effectuée.


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_add_reaction(
    channel_id: str = Field(description="ID du salon contenant le message"),
    message_id: str = Field(description="ID du message auquel réagir"),
    emoji: str = Field(
        description="Emoji Unicode ou nom d'emoji custom. Ex: '👍', '🎉', ou ':nom_emoji:' pour les emojis custom"
    ),
) -> str:
    """Ajoute une réaction emoji à un message Discord.

    Accepte les emojis Unicode standard (👍, 🎉) et les emojis custom du serveur (:nom:).
    Retourne une confirmation avec le message et l'emoji utilisé.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))

        await message.add_reaction(emoji)

        return json.dumps({
            "success": True,
            "message_id": message_id,
            "emoji": emoji,
            "message_url": message.jump_url,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Message ou emoji introuvable (message_id={message_id}, emoji='{emoji}')."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir la permission 'Ajouter des réactions'."
    except discord.InvalidArgument:
        return f"❌ Emoji invalide : '{emoji}'. Utilisez un emoji Unicode ou le nom exact d'un emoji custom."
    except ValueError:
        return "❌ IDs invalides : channel_id et message_id doivent être des entiers numériques."
    except Exception as e:
        return format_error(e)

# Les emojis custom doivent être accessibles au bot (présents sur le même serveur
# ou un serveur où le bot a accès). Format custom : '<:nom:ID>' ou juste ':nom:'.


@mcp.tool(annotations={"readOnlyHint": False})
async def discord_send_embed(
    channel_id: str = Field(description="ID du salon où envoyer l'embed"),
    title: str = Field(description="Titre de l'embed (max 256 caractères)"),
    description: Optional[str] = Field(
        default=None,
        description="Corps principal de l'embed (max 4096 caractères, supporte le Markdown)",
    ),
    color: Optional[str] = Field(
        default=None,
        description="Couleur de la barre latérale en hex. Ex: '#5865F2' (bleu Discord)",
    ),
    footer: Optional[str] = Field(
        default=None,
        description="Texte de pied de page de l'embed",
    ),
    image_url: Optional[str] = Field(
        default=None,
        description="URL d'une image à afficher dans l'embed",
    ),
    fields: Optional[str] = Field(
        default=None,
        description='Champs additionnels en JSON. Ex: \'[{"name":"Clé","value":"Valeur","inline":true}]\'',
    ),
) -> str:
    """Envoie un message embed riche dans un salon Discord.

    Les embeds permettent un formatage avancé avec titre, description,
    couleur, image et champs structurés. Idéal pour les annonces et rapports.
    Retourne l'ID et l'URL du message embed envoyé.
    """
    try:
        client = await ensure_ready()

        channel = await client.fetch_channel(int(channel_id))

        embed_color = discord.Color.blurple()
        if color:
            try:
                cleaned = color.lstrip("#").strip()
                embed_color = discord.Color(int(cleaned, 16))
            except ValueError:
                return f"❌ Couleur hex invalide : '{color}'. Format attendu : '#RRGGBB'."

        embed = discord.Embed(
            title=title,
            description=description,
            color=embed_color,
        )

        if footer:
            embed.set_footer(text=footer)

        if image_url:
            embed.set_image(url=image_url)

        if fields:
            try:
                parsed_fields: list[dict] = json.loads(fields)
                for f in parsed_fields:
                    embed.add_field(
                        name=f.get("name", ""),
                        value=f.get("value", ""),
                        inline=f.get("inline", False),
                    )
            except json.JSONDecodeError:
                return "❌ Le paramètre 'fields' doit être un JSON valide. Ex: '[{\"name\":\"Titre\",\"value\":\"Texte\"}]'"

        sent = await channel.send(embed=embed)

        return json.dumps({
            "id": str(sent.id),
            "url": sent.jump_url,
            "channel_id": channel_id,
            "embed_title": title,
        }, indent=2, ensure_ascii=False)

    except discord.NotFound:
        return f"❌ Salon introuvable (channel_id={channel_id})."
    except discord.Forbidden:
        return "❌ Permission refusée. Le bot doit avoir 'Envoyer des messages' et 'Intégrer des liens'."
    except ValueError:
        return f"❌ channel_id invalide : '{channel_id}' doit être un entier numérique."
    except Exception as e:
        return format_error(e)

# Les embeds nécessitent la permission 'Embed Links' en plus de 'Send Messages'.
# Le paramètre fields accepte un JSON string car FastMCP ne supporte pas
# nativement les listes d'objets comme paramètre de tool.
