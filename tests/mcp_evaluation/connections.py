"""Official Python SDK v2 connections; modern MCP is the default."""
from contextlib import AsyncExitStack
import os
import math
from typing import Any
import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

PROTOCOL = "2026-07-28"

def validate_config(config: dict[str, Any]) -> None:
    if config.get('protocol', PROTOCOL) not in (PROTOCOL, 'auto'):
        raise ValueError('Unsupported protocol mode')
    timeout = float(config.get('timeout_seconds', 30))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout_seconds must be positive and finite')
    transport = config.get('transport')
    if transport == 'stdio':
        if not isinstance(config.get('command'), str) or not config['command']:
            raise ValueError('stdio requires a command')
        for key in ('args', 'env_names'):
            value = config.get(key, [])
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ValueError(f'{key} must be an array of strings')
    elif transport in ('http', 'streamable-http', 'streamable_http'):
        url = config.get('url')
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            raise ValueError('HTTP requires an http(s) URL')
        headers = config.get('headers_env', {})
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise ValueError('headers_env must map header names to environment variable names')
    else:
        raise ValueError('Use stdio or streamable-http')

class MCPConnection:
    def __init__(self, config: dict[str, Any]):
        validate_config(config)
        self.config = config
        self.client: Client | None = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        try:
            mode = self.config.get("protocol", PROTOCOL)
            if mode not in (PROTOCOL, "auto"):
                raise ValueError("protocol must be 2026-07-28 or auto")
            timeout = float(self.config.get("timeout_seconds", 30))
            if timeout <= 0:
                raise ValueError("timeout_seconds must be positive")
            transport = self.config.get("transport")
            if transport == "stdio":
                command = self.config.get("command")
                args = self.config.get("args", [])
                if not isinstance(command, str) or not command:
                    raise ValueError("stdio requires a command")
                if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
                    raise ValueError("args must be an array of strings")
                env = {name: os.environ[name] for name in self.config.get("env_names", [])}
                target = StdioServerParameters(command=command, args=args, env=env)
            elif transport in ("http", "streamable-http", "streamable_http"):
                url = self.config.get("url")
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    raise ValueError("HTTP requires an http(s) URL")
                headers = {key: os.environ[name] for key, name in self.config.get("headers_env", {}).items()}
                http = await self._stack.enter_async_context(httpx2.AsyncClient(
                    headers=headers, timeout=httpx2.Timeout(timeout), follow_redirects=False
                ))
                target = streamable_http_client(url, http_client=http)
            else:
                raise ValueError("Use stdio or streamable-http; legacy SSE is not a modern transport")
            self.client = await self._stack.enter_async_context(
                Client(target, mode=mode, read_timeout_seconds=timeout)
            )
            return self
        except BaseException:
            await self._stack.aclose()
            self._stack = None
            self.client = None
            raise

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._stack:
                await self._stack.__aexit__(exc_type, exc, tb)
        finally:
            self.client = None
            self._stack = None

    @property
    def protocol_version(self) -> str:
        if self.client is None:
            raise RuntimeError("Connection is not open")
        return self.client.protocol_version

    async def list_tools(self) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("Connection is not open")
        tools, seen, cursor = [], set(), None
        for _ in range(100):
            result = await self.client.list_tools(cursor=cursor)
            tools.extend(tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools)
            cursor = result.next_cursor
            if cursor is None:
                return tools
            if cursor in seen:
                raise RuntimeError("tools/list repeated a pagination cursor")
            seen.add(cursor)
        raise RuntimeError("tools/list exceeded 100 pages")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Connection is not open")
        result = await self.client.call_tool(name, arguments)
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

def create_connection(config: dict[str, Any]) -> MCPConnection:
    return MCPConnection(config)
