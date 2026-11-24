# Admin panel skill (SQLAdmin)

Float provides an internal operational administration panel mounted at `/admin` using SQLAdmin.

## Core Rules & Guardrails
- **Operational data only**: Knowledge documents, verified contacts, audit/trace metadata, feature flags, and a read-only Users view with strict allowlisted columns (email masked by default; reveal is permanently audited). NEVER register accounts, transactions, balances, conversations, or messages.
- **Sensitive data prohibited**: Financial accounts, transactions, balances, conversations, messages, and raw sensitive user credentials (hashed passwords, tokens, full name, phone, PAN/Aadhaar) are strictly forbidden from appearing in the admin panel. Unit tests strictly enforce this guardrail.
- **Dedicated admin authentication**: Separate admin authentication (not normal user tokens), short session expiry (30m), disabled unless `PFA_ADMIN_ENABLED=true`, internal IP allowlist by default.
- **Explicit column lists**: Never show embedding vectors, `content_tsv`, or raw credentials. Truncate long text in list and detail views.
- **Audit trail & actor identity**: Every admin write (create, edit, delete, lifecycle action) and email reveal permanently records the acting admin's ID, action, resource ID, and timestamp; never raw content or unmasked email addresses.

## Architecture & Configuration
- **Package**: `sqladmin==0.32.0` (with `wtforms>=3.1.0`, `itsdangerous>=2.2.0`, `python-multipart>=0.0.18`).
- **Feature flag**: `PFA_ADMIN_ENABLED=false` (default off).
- **Security controls**:
  - `AdminIPAllowlistMiddleware`: Restricts `/admin` paths to configured IPs (default `["127.0.0.1", "::1"]`).
  - `AdminAuth`: SQLAdmin `AuthenticationBackend` validating credentials against `admin_users` table with bcrypt password hashing.
  - Rate limiting on `/admin/login` to prevent credential brute-forcing (5 attempts / 60 seconds).
  - Short session expiry (default 1800s / 30m).

## CLI & Local Usage
- Create an admin user:
  ```bash
  python -m app.admin.create_admin --username admin --password "StrongAdminPass123!" --superuser
  ```
- Run server with admin enabled:
  ```bash
  set PFA_ADMIN_ENABLED=true
  python -m uvicorn app.main:create_app --factory --port 8000
  ```
- Open panel: Navigate to `http://127.0.0.1:8000/admin`.

## SQLAdmin Gotchas & Implementation Notes
1. **Column Exclusions vs Inclusions**: Do not specify both `column_list` and `column_exclude_list` on the same `ModelView` in sqladmin 0.32.0; it raises `AssertionError: Cannot use column_list and column_exclude_list together`. Explicitly enumerate allowed columns in `column_list` and `column_details_list`.
2. **`@action` Authentication Wrapping**: The `@action` decorator wraps functions with `login_required`. In tests or direct view calls, `request.session` must contain `admin_id`, `admin_username`, and `login_time`, and `request.scope` must contain `session`.
3. **Hook Signatures**: `after_model_delete(self, model: Any, request: Request) -> None` returns `None`. Return types other than `None` fail mypy subtype compatibility checks.
4. **Prohibited Consumer Models & User Guardrails**: `Account`, `Transaction`, `TransactionImport`, `Balance`, `Conversation`, `Message`, `BorrowAssessment`, `RecurringCommitment`, etc. are strictly forbidden from the registry. The `User` model is permitted solely via read-only `UserAdmin` (`can_create=can_edit=can_delete=can_export=False`) with allowlisted columns only.
5. **Exact Search Override**: Default SQLAdmin search uses substring `LIKE %term%`. Override `search_query` on `UserAdmin` to enforce exact matching on `User.normalized_email` and UUID `User.id` only.
