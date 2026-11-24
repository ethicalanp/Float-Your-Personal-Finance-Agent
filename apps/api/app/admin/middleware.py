from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class AdminIPAllowlistMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing IP allowlisting for all routes under /admin."""

    def __init__(self, app, allowed_ips: str | list[str] = "127.0.0.1,::1,testclient") -> None:
        super().__init__(app)
        if isinstance(allowed_ips, str):
            self.allowed_ips = {ip.strip() for ip in allowed_ips.split(",") if ip.strip()}
        else:
            self.allowed_ips = set(allowed_ips)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/admin" or request.url.path.startswith("/admin/"):
            client_ip = request.client.host if request.client else "unknown"

            # Check forwarded header if present from trusted proxy, otherwise direct client
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                candidate_ip = forwarded.split(",")[0].strip()
            else:
                candidate_ip = client_ip

            if candidate_ip not in self.allowed_ips and client_ip not in self.allowed_ips:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "ADMIN_FORBIDDEN_IP",
                            "message": f"Access to /admin from IP '{candidate_ip}' is not permitted.",
                            "request_id": getattr(request.state, "request_id", None),
                        }
                    },
                )

        return await call_next(request)
