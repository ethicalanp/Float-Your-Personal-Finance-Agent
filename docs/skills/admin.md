# Admin panel skill (SQLAdmin)

Float provides an internal operational administration panel mounted at `/admin` using SQLAdmin.

## Core Rules & Guardrails
- **Operational data only**: Knowledge documents, verified contacts, audit/trace metadata, and feature flags.
- **Sensitive data prohibited**: NEVER register users, accounts, transactions, balances, conversations, or messages in the admin panel. Tests strictly enforce this absence.
- **Dedicated admin authentication**: Separate admin authentication (not normal user tokens), short session expiry, disabled unless `PFA_ADMIN_ENABLED=true`, internal IP allowlist by default.
- **Explicit column lists**: Never show embedding vectors or `content_tsv`. Truncate long text in list and detail views.
- **Lifecycle guardrails**: Knowledge document lifecycle changes (review, publish, archive, supersede) must go through the same domain service as the ingestion CLI (`KnowledgeIngestService`), never raw status updates. Reviewer is set to the acting admin.
- **Audit trail**: Every admin write (create, edit, delete, custom action) is audited: admin ID, action name, object ID, and timestamp; never raw content.

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
4. **Prohibited Consumer Models**: Never register `User`, `Account`, `Transaction`, `Balance`, `Conversation`, `Message`, or `UserProfile`. Enforced by `test_sensitive_models_absent_from_admin_registry`.
