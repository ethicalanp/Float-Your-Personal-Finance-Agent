# Auth Skill & Security Rules

## Principles & Guardrails
- **Zero Plaintext Credentials**: Never store plaintext passwords, OTPs, or verification tokens. Store passwords with Argon2id/bcrypt and tokens/OTPs with salted HMAC-SHA256.
- **Constant-Time Comparisons**: Always use `secrets.compare_digest` for hash and token verification to prevent timing attacks.
- **No User Enumeration**: All authentication requests (login, password reset, OTP request, email verify) return generic messages regardless of whether the identifier exists in the database.
- **Zero Raw PII in Logs & Audits**: Log events with one-way SHA-256 hashes (`email_hash`, `phone_hash`), masked IPs (e.g. `192.168.1.xxx` or CIDR), and sanitized metadata. Never log passwords, OTPs, or auth tokens.

## Google Sign-In Rules
- Accept Google ID tokens (web/mobile).
- Verify JWT signature using Google JWKS (`https://www.googleapis.com/oauth2/v3/certs`), audience against `GOOGLE_CLIENT_ID`, issuer (`accounts.google.com` or `https://accounts.google.com`), and expiration.
- Verify `email_verified is True`.
- Create new user or link to existing user **ONLY** when `email_verified` is true and matches. Never link unverified Google emails.
- Store provider (`google`) and subject (`sub`), not just email.

## Phone OTP Rules
- Normalize all phone numbers to E.164 format (default country code: `+91` India, configurable).
- OTP specs: 6 numeric digits, 5-minute expiry, single-use, max 5 incorrect attempts before permanent invalidation.
- Rate limits & Cooldowns:
  - Resend cooldown: 30–60 seconds per phone number.
  - Per-phone limit: max 5 requests per hour.
  - Per-IP limit: max 20 requests per hour.
  - Global daily cap against SMS pumping.
- SMS Provider Interface:
  - Abstract base interface `SmsProvider` with `send_otp(phone_number, otp_code)`.
  - Fake provider: logs the OTP **only** when `ENV=local` or `PFA_APP_ENV=development`; silent in test/production.
  - Adapter stubs for production providers (e.g. AWS SNS, MSG91).

## Email Verification & Password Reset
- Single-use, cryptographically secure 256-bit random tokens hashed with SHA-256.
- Expiration: Password reset tokens expire in 15 minutes; email verification tokens in 24 hours.
- When password is changed or reset: revoke **all** active user sessions immediately.

## Sessions & Token Rotation
- Access tokens: short-lived (15–60 minutes) JWTs.
- Refresh tokens: opaque, stored as HMAC hashes in `user_sessions`.
- Rotation: Every refresh returns a new access token and rotates the refresh token.
- Reuse Detection: If an already-used or revoked refresh token is presented, revoke the entire session family immediately as potential theft.
- Account Linking:
  - Users can view linked methods (`password`, `google`, `phone`).
  - Adding or removing an identity requires fresh re-authentication.
  - Never allow unlinking the user's sole remaining authentication method.

## Consent Separation (DPDP Act 2023)
- Explicitly record `terms` and `privacy` consent separately from `ai_data_processing` consent.
- Version tracking: Each consent record stores `consent_type`, `consent_version`, `granted_at`, and `ip_address_mask`.
- Profile & Data Rights (`/api/v1/me`): `GET`/`PATCH /me` manages display name (incl. Malayalam), `preferred_language`, `locale`, and `notification_preferences` (direct email/phone changes blocked). `POST /me/export` returns non-secret user data; `DELETE /me` requires step-up re-auth (`<=10 min`), revokes sessions, purges conversations, anonymizes audit logs, and schedules deletion with a configurable grace period (`POST /me/delete/cancel`).

## Telecom DLT Checklist (TRAI India) - MSG91
Status: **NOT YET COMPLETED**
- [ ] **Principal Entity (PE) Registration**: Register organization with an Indian telecom operator (Jio, Airtel, Vodafone Idea, BSNL) DLT portal.
- [ ] **Sender ID (Header) Registration**: Register 6-character alphabetic header (e.g. `FLTPFA`) under Service Implicit / Transactional category.
- [ ] **OTP Content Template Registration**: Submit explicit transactional OTP template with variable parameter `{#var#}` for the 6-digit OTP code.
- [ ] **Template ID Mapping**: Map registered Telecom DLT Template ID to `PFA_MSG91_TEMPLATE_ID` in production environment.
