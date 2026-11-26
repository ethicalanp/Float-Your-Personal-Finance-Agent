import asyncio
import logging
import os
from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings, get_settings
from app.services.phone_service import hash_identifier

logger = logging.getLogger(__name__)


class SmsProvider(ABC):
    @abstractmethod
    async def send_otp(self, phone_number: str, otp_code: str) -> bool:
        """Send a 6-digit OTP to the recipient phone number."""
        pass


class FakeSmsProvider(SmsProvider):
    last_phone: str | None = None
    last_otp: str | None = None

    async def send_otp(self, phone_number: str, otp_code: str) -> bool:
        FakeSmsProvider.last_phone = phone_number
        FakeSmsProvider.last_otp = otp_code
        env_str = os.environ.get("ENV", "").lower()
        # Log only when ENV=local, NEVER outside local
        if env_str in ("local", "loc"):
            ident_hash = hash_identifier(phone_number)
            logger.info("Fake SMS: Sent OTP for ident_hash=%s [LOCAL ONLY]", ident_hash)
        return True


class AwsSnsSmsProvider(SmsProvider):
    async def send_otp(self, phone_number: str, otp_code: str) -> bool:
        ident_hash = hash_identifier(phone_number)
        logger.info("AWS SNS stub: Sending SMS for ident_hash=%s", ident_hash)
        return True


class Msg91SmsProvider(SmsProvider):
    """MSG91 transactional OTP SMS provider adhering to TRAI DLT regulations."""

    def __init__(self, settings: Settings | None = None, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings or get_settings()
        self._http_client = http_client

    def is_configured(self) -> bool:
        return bool(
            self.settings.msg91_auth_key
            and self.settings.msg91_auth_key.get_secret_value().strip()
            and self.settings.msg91_template_id
            and self.settings.msg91_sender_id
        )

    async def send_otp(self, phone_number: str, otp_code: str) -> bool:
        ident_hash = hash_identifier(phone_number)

        if not self.is_configured():
            logger.error("MSG91 SMS provider not configured; failing closed (ident_hash=%s)", ident_hash)
            return False

        auth_key = self.settings.msg91_auth_key.get_secret_value() if self.settings.msg91_auth_key else ""
        template_id = self.settings.msg91_template_id or ""
        sender_id = self.settings.msg91_sender_id or ""
        mobile = phone_number.lstrip("+")

        url = "https://control.msg91.com/api/v5/otp"
        headers = {
            "authkey": auth_key,
            "Content-Type": "application/json",
        }
        params: dict[str, str] = {
            "template_id": template_id,
            "mobile": mobile,
        }
        if sender_id:
            params["sender"] = sender_id

        payload = {"otp": otp_code}
        max_attempts = 3
        timeout = httpx.Timeout(5.0)

        for attempt in range(1, max_attempts + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.post(
                        url,
                        headers=headers,
                        params=params,
                        json=payload,
                        timeout=timeout,
                    )
                else:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            url,
                            headers=headers,
                            params=params,
                            json=payload,
                        )

                if response.status_code == 200:
                    data = response.json() if response.content else {}
                    message_id = data.get("request_id") or data.get("message")
                    logger.info(
                        "MSG91 SMS delivered: ident_hash=%s status=200 msg_id=%s",
                        ident_hash,
                        message_id,
                    )
                    return True

                if 400 <= response.status_code < 500:
                    logger.warning(
                        "MSG91 SMS rejected with client error (no retry): ident_hash=%s status=%d",
                        ident_hash,
                        response.status_code,
                    )
                    return False

                logger.warning(
                    "MSG91 SMS server error (attempt %d/%d): ident_hash=%s status=%d",
                    attempt,
                    max_attempts,
                    ident_hash,
                    response.status_code,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "MSG91 SMS network failure (attempt %d/%d): ident_hash=%s error=%s",
                    attempt,
                    max_attempts,
                    ident_hash,
                    type(exc).__name__,
                )

            if attempt < max_attempts:
                await asyncio.sleep(0.05 * attempt)

        logger.error(
            "MSG91 SMS delivery exhausted %d attempts: ident_hash=%s",
            max_attempts,
            ident_hash,
        )
        return False


def get_sms_provider(settings: Settings | None = None) -> SmsProvider:
    cfg = settings or get_settings()
    if cfg.sms_provider == "aws_sns":
        return AwsSnsSmsProvider()
    if cfg.sms_provider == "msg91":
        return Msg91SmsProvider(settings=cfg)
    return FakeSmsProvider()
