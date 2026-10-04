"""End-to-end: drive the server over a real stdio JSON-RPC session.

This is the check that tool schemas are actually exposed and that stdout stays a
clean protocol stream, which unit tests on the functions cannot prove.
"""

import json
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

PROTOCOL_VERSION = "2024-11-05"
BUDGET_SECONDS = 30


@pytest.fixture
def server(tmp_path: Path):
    """A real `python -m mixcloud_mcp_server` process, wired to a throwaway config."""
    env = {
        **os.environ,
        "MIXCLOUD_ENV_FILE": str(tmp_path / ".env"),
        "MIXCLOUD_UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    env.pop("MIXCLOUD_TOKEN", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "mixcloud_mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    yield process
    process.kill()
    process.wait(timeout=BUDGET_SECONDS)


def send(process, message: dict) -> None:
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def rpc(process, message: dict) -> dict:
    """Send a message and return its reply.

    A bare readline() blocks forever if the server never answers, which would hang
    the suite instead of failing it, so every read is bounded.
    """
    send(process, message)
    while True:
        readable, _, _ = select.select([process.stdout], [], [], BUDGET_SECONDS)
        if not readable:
            pytest.fail(f"no reply to {message['method']} within {BUDGET_SECONDS}s")
        line = process.stdout.readline()
        if not line:
            pytest.fail(f"stdout closed: {process.stderr.read()[:2000]}")
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)  # raises if anything but protocol reached stdout
        if payload.get("id") == message["id"]:
            return payload


def handshake(process) -> dict:
    reply = rpc(
        process,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )
    send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return reply


def call_tool(process, tool_id: int, name: str, arguments: dict) -> dict:
    reply = rpc(
        process,
        {
            "jsonrpc": "2.0",
            "id": tool_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    return reply["result"]


def test_tools_are_listed_over_stdio(server):
    reply = handshake(server)
    assert reply["result"]["serverInfo"]["name"] == "mixcloud"

    listed = rpc(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listed["result"]["tools"]
    assert len(tools) == 22
    assert {"search", "upload_show", "auth_url", "oembed"} <= {tool["name"] for tool in tools}
    assert all(tool.get("description") for tool in tools)


def test_optional_arguments_are_optional_in_the_schema(server):
    """upload_show has eleven optional parameters; they must not be required."""
    handshake(server)
    listed = rpc(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    upload = next(t for t in listed["result"]["tools"] if t["name"] == "upload_show")
    assert upload["inputSchema"]["required"] == ["audio_path", "name"]


def test_validation_runs_before_any_network_call(server):
    handshake(server)
    result = call_tool(server, 3, "oembed", {"url": "https://evil.example.com/x/"})
    assert result["isError"] is True
    assert "mixcloud.com" in result["content"][0]["text"]


def test_a_missing_token_is_reported_as_a_tool_error(server):
    """An auth failure is a tool error, not a protocol crash."""
    handshake(server)
    result = call_tool(server, 4, "me", {})
    assert result["isError"] is True
    assert "exchange_code" in result["content"][0]["text"]


def test_the_server_stays_alive_after_an_error(server):
    """One bad call must not poison the session."""
    handshake(server)
    call_tool(server, 5, "me", {})
    listed = rpc(server, {"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 22
