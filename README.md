![Mixcloud MCP Server](public/mixcloud.svg)

<div align="center" style="line-height: 1;">
    <a href="https://github.com/modelcontextprotocol/servers" target="_blank" style="margin: 2px;">
        <img alt="MCP Server" src="https://badge.mcpx.dev?type=server" style="display: inline-block; vertical-align: middle;"/>
    </a>
    <a href="https://pypi.org/project/mixcloud-mcp-server/" target="_blank" style="margin: 2px;">
        <img alt="PyPI" src="https://img.shields.io/pypi/dw/mixcloud-mcp-server" style="display: inline-block; vertical-align: middle;"/>
    </a>
    <a href="https://github.com/djornii/mixcloud-mcp-server/blob/main/LICENSE" target="_blank" style="margin: 2px;">
        <img alt="MIT License" src="https://img.shields.io/github/license/djornii/mixcloud-mcp-server" style="display: inline-block; vertical-align: middle;"/>
    </a>
</div>

---

An [MCP](https://modelcontextprotocol.io) server for the [Mixcloud](https://www.mixcloud.com) API.
Any MCP client can drive it: search and browse shows, follow/favorite/repost, and upload or edit
your own shows — including scheduled publishing.

- [Installation](#installation)
- [Client setup](#client-setup)
- [Configuration](#configuration)
- [Authorization](#authorization)
- [Tools](#tools)
  - [Read (no token)](#read-no-token)
  - [Account actions (token)](#account-actions-token)
  - [Upload and edit (token)](#upload-and-edit-token)
  - [OAuth](#oauth)
- [Safety](#safety)

## Installation

```bash
uv tool install mixcloud-mcp-server
```

Check the installation:

```sh
mixcloud-mcp-server --print-config   # resolved paths and which credentials exist, no secrets
mixcloud-mcp-server --version
```

## Client setup

The server speaks **stdio**. The commands below use `uvx`, which runs the server straight from PyPI without a separate install.

### Claude Code

```bash
claude mcp add mixcloud -- uvx mixcloud-mcp-server
```

### Codex CLI

```bash
codex mcp add mixcloud -- uvx mixcloud-mcp-server
```

### OpenCode

```bash
opencode mcp add mixcloud -- uvx mixcloud-mcp-server
```

Or manually in `opencode.json`:

```json
{
    "mcp": {
        "servers": {
            "mixcloud": {
                "type": "local",
                "command": ["uvx", "mixcloud-mcp-server"]
            }
        }
    }
}
```

### Pi

Pi reads MCP servers through the `pi-mcp-adapter` package:

```bash
pi install npm:pi-mcp-adapter
pi mcp add mixcloud -- uvx mixcloud-mcp-server
```

Use `-l` to write the entry into the project configuration instead of the user-level one. Pass
the env file with `--env MIXCLOUD_ENV_FILE=...`.

### Hermes Agent

```sh
hermes mcp add mixcloud --command uvx --args mixcloud-mcp-server
```

In `.hermes/config.yaml` recommended to set Hermes Agent's env file:

```yaml
mcp_servers:
    mixcloud:
        command: uvx
        args: ["mixcloud-mcp-server"]
        env:
            MIXCLOUD_ENV_FILE: "/home/you/.config/mixcloud-mcp-server/.env"
```

Then check with `hermes mcp list`.

### Any other client

Run `uvx mixcloud-mcp-server` and pass `MIXCLOUD_ENV_FILE` in its environment.

## Configuration


| Variable                 | Default                                                            | Purpose                                                    |
| ------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| `MIXCLOUD_ENV_FILE`      | `$XDG_CONFIG_HOME/mixcloud-mcp-server/.env` (~`~/.config/…`)       | Token store: loaded at startup, written by `exchange_code` |
| `MIXCLOUD_UPLOAD_DIR`    | `$XDG_DATA_HOME/mixcloud-mcp-server/uploads` (~`~/.local/share/…`) | The **only** directory uploads may read files from         |
| `MIXCLOUD_CLIENT_ID`     | —                                                                  | OAuth app id, needed once for authorization                |
| `MIXCLOUD_CLIENT_SECRET` | —                                                                  | OAuth secret, needed once for authorization                |
| `MIXCLOUD_TOKEN`         | —                                                                  | Access token; written for you by `exchange_code`           |


## Authorization

Go to https://www.mixcloud.com/developers/create/ and create an app. You will get the `CLIENT ID` and `CLIENT SECRET`, write them in your `.env`.

Ask the agent:

1. `auth_url()` — returns a link to open in a browser
2. Open it, allow access, copy the code
3. `exchange_code(code)` — stores the token in the env file and never returns it

`check_token()` verifies the token; `clear_token()` forgets it locally. Mixcloud exposes no
revoke endpoint.

## Tools

### Read (no token)

- `search` - Search shows, users, or tags by query; supports result type and pagination.
- `get_object` - Fetch a show, user, tag, or city by Mixcloud key or URL; optionally include metadata or authenticated fields.
- `get_show` - Fetch a show's key details, including its description, play and favorite counts, and tags.
- `get_user` - Fetch a user profile by key or URL.
- `get_tag` - Fetch a genre, city, or a genre combined with a city.
- `list_connection` - List an object's followers, following, favorites, shows, or listens; supports pagination and date filters.
- `user_shows` - List a user's shows with pagination and optional date filters.
- `browse` - List site-wide popular, hot, or new shows.
- `genre_shows` - List shows for a genre using one of the lists available for that tag.
- `embed_html` - Generate the HTML player embed for a show, with optional size and color.
- `oembed` - Get oEmbed data for a Mixcloud show URL.

### Account actions (token)

- `me` - Fetch the authorized user's profile; optionally include metadata.
- `follow_user` - Follow a user, or unfollow them with `undo=true`.
- `favorite_show` - Favorite a show, or remove it from favorites with `undo=true`.
- `repost_show` - Repost a show, or remove the repost with `undo=true`.
- `listen_later` - Add a show to Listen Later, or remove it with `undo=true`.

### Upload and edit (token)

- `upload_show` - Upload an audio show with optional artwork and metadata; files must be in `MIXCLOUD_UPLOAD_DIR`, and visibility defaults to unlisted.
- `edit_show` - Edit an uploaded show’s metadata, artwork, or visibility; tags, sections, and hosts are replaced wholesale when supplied.

### OAuth

- `auth_url` - Generate the Mixcloud authorization URL; optionally specify a redirect URI.
- `exchange_code` - Exchange an OAuth code for an access token, then save the token locally without revealing it.
- `check_token` - Check whether the saved access token is valid and identify the authorized account.
- `clear_token` - Forget the access token locally; optionally remove it from the env file (does not revoke access on Mixcloud).

Objects are addressed by Mixcloud key: shows `/username/show-name/`, users `/username/`,
tags `/genres/funk/`, cities `/genres/city:athens/`. Full URLs are accepted everywhere a key is.

## Safety

- Uploads are sandboxed to `MIXCLOUD_UPLOAD_DIR` with an extension and size allowlist, so a
  prompt-injected path cannot exfiltrate arbitrary files from the machine.
- The access token is sent as a query parameter, so it is never logged and never included in
  error messages. Tools return a masked preview (`...abcd`) only.
- The client secret is read from the environment and never returned to the model.
- Redirects are not followed for authenticated calls, so a token cannot be replayed to
  another host.
- If you don't use some tools, it's recommended to turn them off in your agent.
