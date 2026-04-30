# DiscordPilot MCP 🚀

> An MCP (Model Context Protocol) server that connects Claude Code to Discord, allowing you to manage servers (guilds), channels, members, roles, messages, and moderation directly from your terminal.

## Features

This MCP server provides a wide array of Discord tools organized into specific namespaces:
- **`guilds_*`**: Manage your Discord servers (e.g., list guilds).
- **`channels_*`**: Manage channels (create, delete, edit, fetch lists).
- **`messages_*`**: Send, edit, delete, and read messages in channels.
- **`members_*`**: Manage server members (kick, ban, fetch lists).
- **`roles_*`**: Create, assign, and manage roles.
- **`moderation_*`**: Moderation utilities.

## Setup Instructions

### 1. Prerequisites
- Python 3.10+
- A Discord Bot Token (with appropriate intents enabled in the Discord Developer Portal)

### 2. Installation
Clone the project and set up a virtual environment:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the example environment file and add your token:

```bash
cp .env.example .env
```
Open `.env` and paste your Discord bot token:
```env
DISCORD_BOT_TOKEN=your_token_here
```

### 4. Running the Server Locally
To run the server manually, execute:
```bash
python src/server.py
```

## Connecting to Claude Code

To add this MCP server to Claude Code, run the following command inside the `DiscordPilot` project directory:

```bash
# On Windows:
claude mcp add discord-pilot .venv\Scripts\python.exe src\server.py

# On macOS/Linux:
claude mcp add discord-pilot .venv/bin/python src/server.py
```

*(Note: Claude Code will automatically pick up your `DISCORD_BOT_TOKEN` from the `.env` file since the server uses `dotenv`)*

To verify the server is connected, run:
```bash
claude mcp list
```

## License
MIT
