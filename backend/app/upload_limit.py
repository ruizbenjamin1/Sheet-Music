"""Middleware ASGI que corta una subida apenas supera un tamaño máximo.

FastAPI guarda todo el multipart antes de llamar a la ruta, así que el límite
dentro de la ruta llega tarde. Este middleware:
  - responde 413 enseguida si el Content-Length ya pasa el máximo, sin leer el cuerpo;
  - si no hay Content-Length (envío por partes), cuenta los bytes a medida que
    llegan y corta al pasar el máximo.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class UploadLimitMiddleware:
    def __init__(self, app, path: str, max_bytes: int, detail: str):
        self.app = app
        self.path = path
        self.max_bytes = max_bytes
        self.detail = detail

    async def _reject(self, send) -> None:
        body = json.dumps({"detail": self.detail}, ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None:
            try:
                too_big = int(length) > self.max_bytes
            except ValueError:
                too_big = False
            if too_big:
                log.info("Subida rechazada por Content-Length: %s bytes", length)
                await self._reject(send)
                return

        total = 0
        exceeded = False
        started = False

        async def limited_receive():
            nonlocal total, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    exceeded = True
                    log.info("Subida cortada al pasar %s bytes", self.max_bytes)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal started
            if exceeded:
                return  # la respuesta la manda este middleware
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
        if exceeded and not started:
            await self._reject(send)
