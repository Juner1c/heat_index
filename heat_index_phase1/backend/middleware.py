"""Bound the small forecast request body, including requests without Content-Length."""
from starlette.responses import JSONResponse


class ForecastBodyLimit:
    def __init__(self, app, max_bytes=4096):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/forecast/predict" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                response = JSONResponse({"detail": {"code": "request_too_large", "message": "Forecast request bodies must not exceed 4096 bytes."}}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        return await self.app(scope, bounded_receive, send)
