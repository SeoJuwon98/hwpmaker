from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logger import get_logger

_STREAMING_CONTENT_TYPES = ("text/event-stream", "x-ndjson", "application/octet-stream")


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = get_logger("api.middleware")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.time()
        response = await call_next(request)
        if response is None:
            return Response(status_code=500)

        process_time = round((time.time() - start_time) * 1000, 2)
        client_addr = request.client.host if request.client else "unknown"
        content_type = response.headers.get("content-type", "")

        # 스트리밍/파일 응답은 body를 소비하지 않고 바로 반환
        if any(t in content_type for t in _STREAMING_CONTENT_TYPES):
            self.logger.info(
                f"{client_addr} STREAM {request.url.path} - {response.status_code}",
                client_addr=client_addr,
                request_method=request.method,
                status_code=response.status_code,
                process_time_ms=process_time,
                is_streaming=True,
            )
            return response

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        log_props: dict = dict(
            client_addr=client_addr,
            request_method=request.method,
            status_code=response.status_code,
            process_time_ms=process_time,
        )
        if request.query_params:
            log_props["query_params"] = str(request.query_params)

        if response.status_code < 400:
            self.logger.info(
                f"{client_addr} - {request.method} {request.url.path} {response.status_code}",
                **log_props,
            )

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
