"""Progressive lockout and rate-limiting tracker for password login and password reset."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _LockoutState:
    attempts: int = 0
    locked_until: float = 0.0


class AuthLockoutTracker:
    """In-memory progressive delay & lockout tracker keyed by (scope, identifier)."""

    def __init__(
        self,
        login_account_threshold: int = 5,
        login_ip_threshold: int = 20,
        reset_account_threshold: int = 3,
        reset_ip_threshold: int = 10,
        base_delay_seconds: float = 15.0,
        max_delay_seconds: float = 900.0,
    ) -> None:
        self.login_account_threshold = login_account_threshold
        self.login_ip_threshold = login_ip_threshold
        self.reset_account_threshold = reset_account_threshold
        self.reset_ip_threshold = reset_ip_threshold
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], _LockoutState] = {}

    def _compute_delay(self, attempts: int, threshold: int) -> float:
        if attempts < threshold:
            return 0.0
        exponent = attempts - threshold
        return float(min(self.max_delay_seconds, self.base_delay_seconds * (2**exponent)))

    def _is_locked(self, scope: str, key: str | None, now: float) -> bool:
        if not key:
            return False
        state = self._states.get((scope, key))
        return state is not None and state.locked_until > now

    def _record_attempt(self, scope: str, key: str | None, threshold: int, now: float) -> float:
        if not key:
            return 0.0
        state = self._states.setdefault((scope, key), _LockoutState())
        state.attempts += 1
        delay = self._compute_delay(state.attempts, threshold)
        if delay > 0:
            state.locked_until = max(state.locked_until, now + delay)
        return delay

    def is_login_locked(self, email: str, ip: str | None) -> tuple[bool, str | None]:
        now = time.monotonic()
        with self._lock:
            if self._is_locked("login_account", email, now):
                return True, "account"
            if self._is_locked("login_ip", ip, now):
                return True, "ip"
            return False, None

    def record_login_failure(self, email: str, ip: str | None) -> float:
        now = time.monotonic()
        with self._lock:
            d_acct = self._record_attempt("login_account", email, self.login_account_threshold, now)
            d_ip = self._record_attempt("login_ip", ip, self.login_ip_threshold, now)
            return max(d_acct, d_ip)

    def clear_login_account(self, email: str) -> None:
        with self._lock:
            self._states.pop(("login_account", email), None)

    def is_reset_locked(self, email: str, ip: str | None) -> tuple[bool, str | None]:
        now = time.monotonic()
        with self._lock:
            if self._is_locked("reset_account", email, now):
                return True, "account"
            if self._is_locked("reset_ip", ip, now):
                return True, "ip"
            return False, None

    def record_reset_request(self, email: str, ip: str | None) -> float:
        now = time.monotonic()
        with self._lock:
            d_acct = self._record_attempt("reset_account", email, self.reset_account_threshold, now)
            d_ip = self._record_attempt("reset_ip", ip, self.reset_ip_threshold, now)
            return max(d_acct, d_ip)

    def unlock_via_reset(self, email: str | None) -> None:
        if not email:
            return
        with self._lock:
            self._states.pop(("login_account", email), None)
            self._states.pop(("reset_account", email), None)

    def reset(self) -> None:
        with self._lock:
            self._states.clear()


lockout_tracker = AuthLockoutTracker()
