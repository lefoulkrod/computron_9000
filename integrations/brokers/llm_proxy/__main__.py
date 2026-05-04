"""LLM proxy broker: inject auth header, forward HTTP traffic over a UDS.

The supervisor spawns this with credentials and provider info in the
environment. It starts an aiohttp HTTP server on a Unix Domain Socket,
validates the API key at startup, then serves as a transparent HTTP proxy
that injects the real auth header on every forwarded request.

Streaming responses (SSE / chunked transfer encoding) pass through
unmodified — the proxy writes chunks to the SDK client as they arrive
from the upstream API.

Exit codes (same contract as email_broker):
- 0: clean shutdown
- 77: API key rejected by upstream (401 / 403 on startup validation)
- 1: network unreachable or internal error
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import aiohttp
from aiohttp import web

from integrations._env import env_required
from integrations._perms import PROCESS_UMASK, SOCKET_MODE, disable_core_dumps
from integrations.brokers._common._exit_codes import AUTH_FAIL, CLEAN_SHUTDOWN, GENERIC_ERROR
from integrations.brokers._common._ready import print_ready

os.umask(PROCESS_UMASK)
disable_core_dumps()

logger = logging.getLogger("llm_proxy")

# Headers that must not be forwarded; they're hop-by-hop and meaningful
# only for the immediate transport layer, not the end-to-end exchange.
_HOP_BY_HOP = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
})

# Auth headers each provider expects; we strip these from the SDK client
# request (which carries a placeholder) and inject the real key.
_AUTH_HEADERS_TO_STRIP = frozenset({"authorization", "x-api-key"})


def _make_auth_headers(provider: str, api_key: str) -> dict[str, str]:
    """Return the auth header(s) to inject for this provider."""
    if provider == "anthropic":
        # The Anthropic SDK sends anthropic-version itself; we only inject the
        # credential header. Injecting our own copy would produce a duplicate.
        return {"x-api-key": api_key}
    # OpenAI and all OpenAI-compatible providers
    return {"Authorization": f"Bearer {api_key}"}


async def _validate_key(
    provider: str,
    api_key: str,
    upstream_base: str,
    log: logging.Logger,
) -> int:
    """Hit the upstream /v1/models endpoint to validate the API key before accepting traffic.

    Returns AUTH_FAIL on 401/403, GENERIC_ERROR on connection failure, 0 on success.
    Non-auth failures (network, 5xx) are returned as GENERIC_ERROR so the supervisor
    can apply backoff restart rather than marking the integration permanently failed.
    """
    url = f"{upstream_base}/v1/models"
    headers = _make_auth_headers(provider, api_key)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    log.error("API key rejected by upstream (status=%d)", resp.status)
                    return AUTH_FAIL
                # 5xx or unexpected 4xx: upstream is up but unhappy for a non-auth reason.
                # Don't treat as auth failure — let the supervisor retry with backoff.
                if resp.status >= 500:
                    log.error("upstream returned %d on startup validation", resp.status)
                    return GENERIC_ERROR
    except aiohttp.ClientConnectionError as exc:
        log.error("could not reach upstream during startup validation: %s", exc)
        return GENERIC_ERROR
    except Exception as exc:
        # Timeout, SSL errors, etc. Not an auth failure; let the supervisor retry.
        log.error("startup validation failed unexpectedly: %s", exc)
        return GENERIC_ERROR
    return 0


async def _run() -> int:
    integration_id = env_required("INTEGRATION_ID")
    socket_path = Path(env_required("BROKER_SOCKET"))
    api_key = env_required("LLM_API_KEY")
    provider = env_required("LLM_PROVIDER")
    upstream_base = env_required("LLM_BASE_URL").rstrip("/")

    # Wipe the key from the process environment (best-effort hygiene).
    # Narrows in-process exposure: debuggers, traceback locals, crash-reporter
    # captures. Does NOT clear /proc/<pid>/environ — that's set at exec time
    # and is mode 0400 (unreadable by other UIDs).
    os.environ.pop("LLM_API_KEY", None)

    log = logging.getLogger(f"llm_proxy[{integration_id}]")

    rc = await _validate_key(provider, api_key, upstream_base, log)
    if rc != 0:
        return rc

    # One persistent upstream session for all proxied requests. Reusing a session
    # keeps the TCP connection pool warm and avoids per-request TLS handshake overhead.
    upstream_session = aiohttp.ClientSession()

    async def proxy_handler(request: web.Request) -> web.StreamResponse:
        # Reconstruct the full upstream URL from the base plus the request's
        # relative URL (path + query string).
        url = upstream_base + str(request.rel_url)

        # Forward all request headers except hop-by-hop and auth placeholders;
        # then inject the real credentials.
        headers: dict[str, str] = {}
        for k, v in request.headers.items():
            kl = k.lower()
            if kl in _HOP_BY_HOP or kl in _AUTH_HEADERS_TO_STRIP or kl == "host":
                continue
            headers[k] = v
        headers.update(_make_auth_headers(provider, api_key))

        body = await request.read()

        try:
            async with upstream_session.request(
                request.method,
                url,
                headers=headers,
                data=body or None,
                # Long timeout to accommodate streaming completions that may
                # run for many seconds (or minutes for long generation tasks).
                timeout=aiohttp.ClientTimeout(total=600),
                allow_redirects=False,
            ) as upstream_resp:
                response = web.StreamResponse(
                    status=upstream_resp.status,
                    reason=upstream_resp.reason,
                )
                for k, v in upstream_resp.headers.items():
                    kl = k.lower()
                    # Drop content-length so the response can stream as chunked
                    # encoding without a mismatch if the upstream sends a length.
                    if kl in _HOP_BY_HOP or kl == "content-length":
                        continue
                    response.headers[k] = v

                await response.prepare(request)
                async for chunk in upstream_resp.content.iter_any():
                    await response.write(chunk)
                await response.write_eof()
                return response
        except aiohttp.ClientError as exc:
            log.error("upstream request failed: %s", exc)
            return web.Response(status=502, text=f"Bad Gateway: {exc}")

    # Remove stale socket from a crashed or previous run. The supervisor
    # un-links sockets on clean shutdown; a SIGKILL leaves them behind.
    if socket_path.exists() or socket_path.is_symlink():
        socket_path.unlink()

    app = web.Application()
    app.router.add_route("*", "/{path_info:.*}", proxy_handler)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.UnixSite(runner, str(socket_path))
    await site.start()
    # chmod AFTER bind — aiohttp creates the socket with the process umask
    # (0o077) which blocks all group/other access. We need 0o660 so the
    # computron UID (in the broker group) can connect.
    socket_path.chmod(SOCKET_MODE)

    log.info("listening on %s (provider=%s, upstream=%s)", socket_path, provider, upstream_base)
    print_ready()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        log.info("shutting down")
        await upstream_session.close()
        await runner.cleanup()

    return CLEAN_SHUTDOWN


def main() -> None:
    """Console entry point — configure logging, run the async body, exit with its return code."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="[%(name)s] %(asctime)s %(levelname)s %(message)s",
    )
    try:
        code = asyncio.run(_run())
    except KeyboardInterrupt:
        code = CLEAN_SHUTDOWN
    sys.exit(code)


if __name__ == "__main__":
    main()
