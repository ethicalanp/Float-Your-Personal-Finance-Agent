import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import verify_password
from app.db.session import get_async_session_factory
from app.models.admin import AdminUser

# IP -> list of timestamps of failed login attempts
_LOGIN_FAILED_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_MAX_FAILED_ATTEMPTS = 5


class AdminAuth(AuthenticationBackend):
    """SQLAdmin AuthenticationBackend using dedicated AdminUser accounts."""

    def __init__(
        self,
        secret_key: str,
        session_expire_seconds: int = 1800,
        session_factory: Any = None,
    ) -> None:
        super().__init__(secret_key=secret_key)
        self.session_expire_seconds = session_expire_seconds
        self.session_factory = session_factory

    def _is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        attempts = [t for t in _LOGIN_FAILED_ATTEMPTS[ip] if now - t < _RATE_LIMIT_WINDOW_SECONDS]
        _LOGIN_FAILED_ATTEMPTS[ip] = attempts
        return len(attempts) >= _MAX_FAILED_ATTEMPTS

    def _record_failed_attempt(self, ip: str) -> None:
        _LOGIN_FAILED_ATTEMPTS[ip].append(time.time())

    def _clear_attempts(self, ip: str) -> None:
        _LOGIN_FAILED_ATTEMPTS.pop(ip, None)

    async def login(self, request: Request) -> bool:
        client_ip = request.client.host if request.client else "unknown"

        if self._is_rate_limited(client_ip):
            return False

        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", "")).strip()

        if not username or not password:
            self._record_failed_attempt(client_ip)
            return False

        session_factory = (
            self.session_factory
            or getattr(request.state, "session_factory", None)
            or get_async_session_factory()
        )
        async with session_factory() as session:
            stmt = select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True))
            res = await session.execute(stmt)
            admin = res.scalars().first()

            if not admin or not verify_password(password, admin.hashed_password):
                self._record_failed_attempt(client_ip)
                return False

            admin.last_login_at = datetime.now(UTC)
            await session.commit()

        self._clear_attempts(client_ip)
        request.session.update({
            "admin_id": str(admin.id),
            "admin_username": admin.username,
            "is_superuser": admin.is_superuser,
            "login_time": time.time(),
        })
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool | Response:
        admin_id = request.session.get("admin_id")
        login_time = request.session.get("login_time")

        if not admin_id or not login_time:
            return False

        # Session expiry validation
        if time.time() - float(login_time) > self.session_expire_seconds:
            request.session.clear()
            return False

        return True
