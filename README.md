# mixcloud-mcp-server

An [MCP](https://modelcontextprotocol.io) server for the [Mixcloud](https://www.mixcloud.com) API.
Any MCP client can drive it: search and browse shows, follow/favourite/repost, and upload or edit
your own shows — including scheduled publishing.

Talk to it in plain language: *"find me a 90-minute Chicago house set from last year"* or
*"upload `set.mp3` as an unlisted show, chapters at 0:00 and 10:00"*.

## Install

```bash
uv tool install git+https://github.com/djornii/mixcloud-mcp-server
# or, from a clone:
uv tool install .
```

Requires Python 3.10+. The only runtime dependencies are `mcp`, `httpx` and `python-dotenv`.

Check the installation:

```bash
mixcloud-mcp-server --print-config   # resolved paths and which credentials exist, no secrets
mixcloud-mcp-server --version
```

## Client setup

The server speaks **stdio**, so every client config is just "run this command".

**Claude Desktop** — `claude_desktop_config.json`:

```json
{ "mcpServers": { "mixcloud": { "command": "mixcloud-mcp-server", "env": { "MIXCLOUD_ENV_FILE": "/home/you/.config/mixcloud-mcp-server/.env" } } } }
```

**Claude Code**

```bash
claude mcp add mixcloud -- mixcloud-mcp-server
```

**OpenCode** — `opencode.json` (V2 puts local servers under `mcp.servers`):

```json
{ "$schema": "https://opencode.ai/config.json", "mcp": { "servers": { "mixcloud": { "type": "local", "command": ["mixcloud-mcp-server"] } } } }
```

Or from the CLI, which writes the same entry:

```bash
opencode mcp add mixcloud -- mixcloud-mcp-server
```

**Any other client**: run `mixcloud-mcp-server` and pass `MIXCLOUD_ENV_FILE` in its environment.

Running it by hand is normal and silent — it is waiting for JSON-RPC on stdin.

## Configuration

Copy `.env.example` to the path `mixcloud-mcp-server --print-config` reports and fill it in.

| Variable | Default | Purpose |
|---|---|---|
| `MIXCLOUD_ENV_FILE` | `$XDG_CONFIG_HOME/mixcloud-mcp-server/.env` (~`~/.config/…`) | Token store: loaded at startup, written by `exchange_code` |
| `MIXCLOUD_UPLOAD_DIR` | `$XDG_DATA_HOME/mixcloud-mcp-server/uploads` (~`~/.local/share/…`) | The **only** directory uploads may read files from |
| `MIXCLOUD_CLIENT_ID` | — | OAuth app id, needed once for authorisation |
| `MIXCLOUD_CLIENT_SECRET` | — | OAuth secret, needed once for authorisation |
| `MIXCLOUD_TOKEN` | — | Access token; written for you by `exchange_code` |

Create the OAuth app at <https://www.mixcloud.com/settings/applications/>. The redirect URI only
matters if you use one; the default flow shows the code on screen.

### Authorising

Ask the agent, or call the tools directly:

1. `auth_url()` — returns a link to open in a browser
2. open it, allow access, copy the code
3. `exchange_code(code)` — stores the token in the env file (mode `0600`) and never returns it

`check_token()` verifies the token; `clear_token()` forgets it locally. Mixcloud exposes no
revoke endpoint, so revoking access has to be done on mixcloud.com itself.

## Tools

**Read (no token):** `search`, `get_object`, `get_show`, `get_user`, `get_tag`, `list_connection`,
`user_shows`, `browse`, `genre_shows`, `embed_html`, `oembed`

**Account (token):** `me`, `follow_user`, `favorite_show`, `repost_show`, `listen_later`,
`upload_show`, `edit_show`

**OAuth:** `auth_url`, `exchange_code`, `check_token`, `clear_token`

Objects are addressed by Mixcloud key: shows `/username/show-name/`, users `/username/`,
tags `/genres/funk/`, cities `/genres/city:athens/`. Full URLs are accepted everywhere a key is.

Notes that surprise people:

- `upload_show` uploads **unlisted** (private link) unless you pass `unlisted=False`.
- `edit_show` replaces `tags`, `sections` and `hosts` wholesale — re-send the existing ones when
  adding a single chapter.
- `publish_date`, `disable_comments`, `hide_stats` and `hosts` require a Pro account.
- Uploads accept `.mp3` up to 4 GB and pictures up to 10 MB, and the files must live inside
  `MIXCLOUD_UPLOAD_DIR` (relative paths resolve there).

## Safety

- Uploads are sandboxed to `MIXCLOUD_UPLOAD_DIR` with an extension and size allowlist, so a
  prompt-injected path cannot exfiltrate arbitrary files from the machine.
- The access token is sent as a query parameter, so it is never logged and never included in
  error messages. Tools return a masked preview (`...abcd`) only.
- The client secret is read from the environment and never returned to the model.
- Redirects are not followed for authenticated calls, so a token cannot be replayed to
  another host.

Works with both `mcp` 1.x and 2.x.

## Development

See [AGENTS.md](AGENTS.md) for the commands and the invariants this codebase holds to.

```bash
uv sync
uv run pytest
uv run ruff check .
```

## License

MIT