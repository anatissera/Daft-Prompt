"""Cancellation primitive for long-running compose requests.

The chat/compose SSE endpoints run under a scoped ``CancelToken`` (via
contextvar). When the HTTP client disconnects, the endpoint fires the token:

  1. ``event.set()`` — any LLM call that hasn't started yet raises
     ``CancelledCompose`` from ``_FallbackStructuredInvoker.invoke`` before
     hitting the network.
  2. Any registered ``httpx.Client`` gets ``.close()`` called — that tears
     down in-flight sockets, which causes the OpenAI SDK's blocking
     ``chat.completions.create`` to raise, and (crucially) llama-server sees
     the peer disconnect and stops decoding tokens. This is the mid-token
     kill we want when the user hits Stop.

Thread-safety: httpx.Client.close() is safe to call from another thread while
a request is in flight — it closes the underlying transport pool, and any
blocked socket read/write in the worker thread wakes up with a
``ConnectionError`` / ``httpx.CloseError`` / ``RemoteProtocolError`` which we
classify and surface as ``CancelledCompose``.
"""

from __future__ import annotations

import socket
import threading
from contextvars import ContextVar
from typing import Optional


class CancelledCompose(RuntimeError):
    """Raised when the SSE client disconnected mid-compose."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._closables: list[object] = []
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledCompose("compose was cancelled by the client")

    def register_closable(self, closable: object) -> None:
        """Register an httpx.Client (or anything with .close()) to be torn
        down when the token fires. Idempotent — safe to call from multiple
        threads."""
        with self._lock:
            self._closables.append(closable)

    def cancel(self) -> None:
        """Fire the token: set the event, then reach into every registered
        httpx.Client and forcibly shut down the underlying TCP socket. That
        wakes up any blocked read/write in the worker thread with a
        ``RemoteProtocolError`` — and llama-server sees the peer disconnect
        and stops decoding tokens.

        We can't rely on ``httpx.Client.close()`` alone: from another thread
        it doesn't preempt an in-flight blocking request (verified). Only a
        direct ``socket.shutdown(SHUT_RDWR)`` unblocks the syscall.
        """
        self._event.set()
        with self._lock:
            closables = list(self._closables)
            self._closables.clear()
        for c in closables:
            _shutdown_httpx_sockets(c)
            try:
                close = getattr(c, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass


def _shutdown_httpx_sockets(client) -> None:
    """Traverse an httpx.Client (or wrapped openai client) down to the
    httpcore socket layer and force-close each active socket. Layout is
    fragile private API; we swallow attribute errors so a shape change never
    breaks the cancel path — worst case it degrades to close()-only."""
    try:
        transport = getattr(client, "_transport", None)
        pool = getattr(transport, "_pool", None) if transport is not None else None
        if pool is None:
            return
        for conn in list(getattr(pool, "_connections", []) or []):
            inner = getattr(conn, "_connection", None)
            stream = getattr(inner, "_network_stream", None) if inner is not None else None
            sock = getattr(stream, "_sock", None) if stream is not None else None
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    except Exception:
        pass


_CANCEL_TOKEN: ContextVar[Optional[CancelToken]] = ContextVar("cancel_token", default=None)


def current_cancel_token() -> Optional[CancelToken]:
    return _CANCEL_TOKEN.get()


def set_cancel_token(token: Optional[CancelToken]):
    """Return the reset object for the caller to use in `finally`."""
    return _CANCEL_TOKEN.set(token)
