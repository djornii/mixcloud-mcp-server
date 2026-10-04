"""The bridge to the SDK's ToolError.

mcp 2.x masks the text of any exception that is not a ToolError, so without this
bridge a model gets "Error executing tool oembed" and no idea what to fix.
"""

import asyncio
import inspect

import pytest

from mixcloud_mcp_server.errors import MixcloudError, ToolError, as_tool_error
from mixcloud_mcp_server.server import mcp


def schema_of(name: str) -> dict:
    """The input schema a client sees for a registered tool."""
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    schema = tools[name].input_schema
    assert isinstance(schema, dict), schema
    return schema


def test_tool_error_is_importable_from_the_installed_sdk():
    """The shim must resolve on whichever major version is installed."""
    assert issubclass(ToolError, Exception)


class TestAsToolError:
    def test_mixcloud_error_message_reaches_the_caller(self):
        @as_tool_error
        def failing():
            raise MixcloudError("API error 401 auth: invalid access token")

        with pytest.raises(ToolError, match="invalid access token"):
            failing()

    def test_value_error_message_reaches_the_caller(self):
        @as_tool_error
        def failing():
            raise ValueError("color must be a 6-digit hex without '#'")

        with pytest.raises(ToolError, match="6-digit hex"):
            failing()

    def test_a_crash_is_left_untouched(self):
        """An unanticipated exception must stay masked and get its traceback logged."""

        @as_tool_error
        def crashing():
            raise KeyError("some internal detail")

        with pytest.raises(KeyError):
            crashing()

    def test_tool_error_is_not_double_wrapped(self):
        @as_tool_error
        def failing():
            raise ToolError("already a tool error")

        with pytest.raises(ToolError, match="already a tool error") as caught:
            failing()
        assert caught.value.__cause__ is None

    def test_success_passes_through(self):
        @as_tool_error
        def fine(value: int) -> int:
            return value * 2

        assert fine(21) == 42

    def test_signature_survives(self):
        """A wrapper must not hide the parameters the tool schema is built from."""

        @as_tool_error
        def a_tool(query: str, limit: int = 10) -> list[dict]:
            """A docstring the model needs."""
            return [{"query": query, "limit": limit}]

        assert a_tool.__name__ == "a_tool"
        assert a_tool.__doc__ == "A docstring the model needs."
        assert list(inspect.signature(a_tool).parameters) == ["query", "limit"]

    def test_a_wrapped_tool_registers_with_the_right_schema(self):
        @as_tool_error
        def sample_tool(query: str, limit: int = 10) -> list[dict]:
            """Sample."""
            return []

        mcp.add_tool(sample_tool, name="_test_sample")
        try:
            schema = schema_of("_test_sample")
            assert list(schema["properties"]) == ["query", "limit"]
            assert schema.get("required", []) == ["query"]
        finally:
            mcp.remove_tool("_test_sample")


class TestRegisteredTools:
    def test_a_bad_argument_is_reported_with_its_reason(self):
        """What a model actually sees for a typo'd argument."""
        with pytest.raises(ToolError, match=r"mixcloud\.com"):
            asyncio.run(mcp.call_tool("oembed", {"url": "https://evil.example.com/x/"}))

    def test_a_missing_token_is_reported_with_how_to_fix_it(self):
        with pytest.raises(ToolError, match="exchange_code"):
            asyncio.run(mcp.call_tool("me", {}))

    def test_schemas_kept_optional_arguments_optional(self):
        schema = schema_of("upload_show")
        assert schema.get("required", []) == ["audio_path", "name"]
        assert "sections" in schema["properties"]
        assert schema["properties"]["sections"]["default"] is None

    def test_every_tool_has_a_description_for_the_model(self):
        for tool in asyncio.run(mcp.list_tools()):
            assert tool.description, tool.name
