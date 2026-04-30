import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when launched via MCP (cwd may differ)
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
from fastmcp import FastMCP

from src.tools.guilds import mcp as guilds_mcp
from src.tools.channels import mcp as channels_mcp
from src.tools.messages import mcp as messages_mcp
from src.tools.members import mcp as members_mcp
from src.tools.roles import mcp as roles_mcp
from src.tools.moderation import mcp as moderation_mcp

load_dotenv(dotenv_path=Path(_project_root) / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("discordpilot")

mcp = FastMCP(
    name="DiscordPilot",
    instructions=(
        "MCP server that connects Claude Code to Discord. "
        "Manage servers (guilds), channels, members, roles, messages and moderation "
        "directly from your terminal. "
        "Start with discord_list_guilds to discover available guild_id values, "
        "then use the appropriate namespaced tools (guilds_*, channels_*, messages_*, "
        "members_*, roles_*, moderation_*)."
    ),
    version="1.0.0",
)

# Chaque sub-server est monté avec un namespace :
# les tools deviennent guilds_discord_list_guilds, channels_discord_send_message, etc.
mcp.mount(guilds_mcp,     namespace="guilds")
mcp.mount(channels_mcp,   namespace="channels")
mcp.mount(messages_mcp,   namespace="messages")
mcp.mount(members_mcp,    namespace="members")
mcp.mount(roles_mcp,      namespace="roles")
mcp.mount(moderation_mcp, namespace="moderation")


async def _log_tools() -> int:
    """Retourne le nombre de tools enregistrés et les affiche dans les logs."""
    tools = await mcp.list_tools()
    for tool in sorted(tools, key=lambda t: t.name):
        logger.info("  📌 %s", tool.name)
    return len(tools)


if __name__ == "__main__":
    logger.info("🚀 DiscordPilot MCP Server démarré")
    logger.info("   Montage des sub-servers : guilds, channels, messages, members, roles, moderation")

    tool_count = asyncio.run(_log_tools())
    logger.info("   ✅ %d tools disponibles", tool_count)
    logger.info("   Transport : stdio (Claude Code)")
    logger.info("   ─────────────────────────────────────────")

    mcp.run(transport="stdio")
