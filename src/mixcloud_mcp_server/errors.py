"""Errors shared by every layer, and the bridge to the MCP SDK's own error type.

Why the bridge: mcp 2.x deliberately hides the text of any exception that is not
a ``ToolError``, so a model asking for a bad key would see only "Error executing
tool oembed" and never learn what to fix. ``as_tool_error`` re-wraps our own
failures -- and only those -- so the message survives while a genuine crash stays
masked and gets logged with its traceback.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

try:  # mcp 1.x
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:  # mcp 2.x
    from mcp.server.mcpserver.exceptions import ToolError


class MixcloudError(RuntimeError):
    """A Mixcloud API call failed, or the server is not in a state to make one.

    Messages are safe to hand back to the model: they never contain the request
    URL, query parameters or the access token.
    """


def as_tool_error(func: Callable[..., Any]) -> Callable[..., Any]:
    """Report MixcloudError and ValueError as anticipated tool failures.

    Applied to every tool at registration. Anything else propagating out of a tool
    body is an unanticipated crash and is left for the SDK to mask and log.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except (MixcloudError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    # functools.wraps copies __wrapped__, so signature introspection still sees the
    # original parameters: the tool schema must not gain a *args/**kwargs.
    return wrapper
