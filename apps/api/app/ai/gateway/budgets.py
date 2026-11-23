import asyncio
import datetime
from typing import Protocol

from app.ai.gateway.errors import BudgetExceeded


class BudgetStore(Protocol):
    async def check_and_increment(self, user_id: str, tokens: int, daily_limit: int) -> int:
        """Check if adding tokens exceeds daily_limit, and increment if allowed.

        Raises BudgetExceeded if budget is breached. Returns new daily total.
        """
        ...


class InMemoryBudgetStore:
    """In-memory thread-safe daily token budget tracker per user."""

    def __init__(self) -> None:
        self._usage: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()

    def _today_str(self) -> str:
        return datetime.date.today().isoformat()

    async def check_and_increment(self, user_id: str, tokens: int, daily_limit: int) -> int:
        async with self._lock:
            today = self._today_str()
            if today not in self._usage:
                self._usage[today] = {}

            current = self._usage[today].get(user_id, 0)
            if current + tokens > daily_limit:
                raise BudgetExceeded(
                    f"User daily token budget exceeded: current {current} + {tokens} > {daily_limit}",
                    budget_type="daily_user",
                )

            self._usage[today][user_id] = current + tokens
            return current + tokens

    async def get_usage(self, user_id: str) -> int:
        async with self._lock:
            today = self._today_str()
            return self._usage.get(today, {}).get(user_id, 0)

    async def reset(self) -> None:
        async with self._lock:
            self._usage.clear()
