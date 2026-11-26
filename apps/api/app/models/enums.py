from enum import Enum

from sqlalchemy import Enum as SqlEnum


class ConsentType(str, Enum):
    TERMS = "terms"
    PRIVACY = "privacy"
    AI_DATA_PROCESSING = "ai_data_processing"


class AuthProvider(str, Enum):
    PASSWORD = "password"
    GOOGLE = "google"
    PHONE = "phone"


class AuthTokenType(str, Enum):
    OTP = "otp"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class AuthAuditEventType(str, Enum):
    REGISTER = "register"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    OTP_REQUEST = "otp_request"
    OTP_VERIFY_SUCCESS = "otp_verify_success"
    OTP_VERIFY_FAILURE = "otp_verify_failure"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_SUCCESS = "password_reset_success"
    EMAIL_VERIFY_REQUEST = "email_verify_request"
    EMAIL_VERIFY_SUCCESS = "email_verify_success"
    REFRESH_SUCCESS = "refresh_success"
    REFRESH_REUSE_DETECTED = "refresh_reuse_detected"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    IDENTITY_LINKED = "identity_linked"
    IDENTITY_UNLINKED = "identity_unlinked"


class AccountType(str, Enum):
    SAVINGS = "savings"
    CHECKING = "checking"
    CREDIT_CARD = "credit_card"
    WALLET = "wallet"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    SUSPENDED = "suspended"


class TransactionType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionSource(str, Enum):
    CSV_UPLOAD = "csv_upload"
    SMS = "sms"
    EMAIL = "email"
    MANUAL = "manual"
    ACCOUNT_AGGREGATOR = "account_aggregator"


class ImportStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LanguageCode(str, Enum):
    EN = "en"
    ML = "ml"
    MANGLISH = "manglish"


class RiskTier(str, Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CaseStatus(str, Enum):
    REPORTED = "reported"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class AuditActor(str, Enum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class ReadinessBand(str, Enum):
    LOW = "low"
    FAIR = "fair"
    GOOD = "good"
    STRONG = "strong"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def enum_type(enum_class: type[Enum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
