# Float Web Application (`apps/web`)

Responsive web application for Float personal finance agent (Plan, Protect, Borrow, Assistant). Built with Next.js 14 App Router, TypeScript, and Tailwind CSS.

## 1. Quick Start

### Prerequisites
- Node.js >= 18.18.0
- Backend running at `http://127.0.0.1:8000` (or configured via `PFA_API_URL`)

### Commands
```cmd
cd apps\web

:: Install dependencies
npm install

:: Start development server (port 3000)
npm run dev

:: Type checking & linting
npx tsc --noEmit
npm run lint

:: Run unit and security tests (50 tests)
npm test

:: Run Playwright mocked end-to-end suite (8 tests, Chromium + Mobile)
npx playwright test

:: Production build
npm run build
npm start
```

## 2. Environment Variables

| Variable | Scope | Default | Purpose |
|---|---|---|---|
| `PFA_API_URL` | Server (BFF) | `http://127.0.0.1:8000` | Target URL for backend FastAPI service |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Client/Public | *(optional)* | Google OAuth 2.0 Web Client ID (must match backend `PFA_GOOGLE_CLIENT_ID`) |
| `NEXT_PUBLIC_APP_VERSION` | Client/Public | *(optional)* | Version number displayed on Download page |
| `NEXT_PUBLIC_APK_URL` | Client/Public | *(optional)* | Direct link to Android APK binary |
| `NEXT_PUBLIC_APK_SHA256` | Client/Public | *(optional)* | SHA-256 integrity hash for manual verification |

*Note: If `NEXT_PUBLIC_APK_URL` is omitted, the Download screen renders a graceful "Coming Soon" state.*

## 3. Architecture & Security Model

- **Backend-for-Frontend (BFF)**: Browser clients never interact directly with backend bearer tokens. Mutating and protected requests proxy through `/api/backend/[...path]`.
- **HttpOnly Cookies**: Session tokens (`float_token`) reside in secure, `httpOnly`, `SameSite=Lax` cookies, shielding authentication state from client-side XSS.
- **CSRF Defense**: All mutating routes (`POST`, `PUT`, `PATCH`, `DELETE`) enforce strict Origin and Referer validation matching the host header.
- **Auth UI & Layered Depth Visual**:
  - **Back layer**: Giant decorative "FLOAT" serif text rendered via inline SVG per-letter transforms in concave/pincushion projection (outer F and T flared tall; middle L-O-A pinched inward). Zero CDN fonts, CSP-safe (zero inline scripts), `aria-hidden="true"`, pointer-events-none.
  - **Mid layer**: Soft gradient shapes with pointer parallax on desktop fine-pointer devices; disabled on touch and `prefers-reduced-motion`.
  - **Front layer**: High-contrast WCAG AA login/signup cards on high-opacity surfaces (`bg-card/95 backdrop-blur-md`).
  - **Social Button & Google Sign-In**: "Continue with Google" (`SocialButton`) rendered on both login and signup, strictly gated by `GET /api/auth/capabilities` (`capabilities.google`).
  - **"Get the Float App" Prompt**: Mobile-first dismissible non-blocking bottom sheet. Displayed upon page navigation at most once per session; hides for 14 days upon dismissal (`localStorage`). Excluded from `/download`, `/login`, `/signup`, legal pages, and the first screen of a visit. Escape key dismisses; focus is not trapped.
  - **Settings Sign-in Methods & Sessions (`/profile/settings`)**: Manage linked methods (Password, Google, Phone OTP with +91 validation). Enforces step-up re-authentication (≤10 min) and forbids removing the sole remaining authentication method. Manage active sessions with individual revoke and global "Log Out All Devices". `/settings` permanently redirects (`308`) to `/profile/settings`.
  - **Profile (`/profile`) & DPDP Data Rights (`/profile/settings#data-rights`)**: Display name (supports Malayalam), language (`en`/`ml`/`manglish`), theme (`light`/`dark`/`system`), notification preferences, DPDP JSON export (`POST /api/me/export`), and grace-period account deletion (`DELETE /api/me` + `POST /api/me/delete/cancel`).
- **Upload Hardening**: Enforces a 10MB streaming byte counter and strict allowlist validation (`lib/upload-validator.ts`). Only valid PDF (`%PDF-`), XLSX (`PK\x03\x04`), and printable CSV/text are accepted; executables (`MZ`, `ELF`), empty files, and unsupported binary types return `415 Unsupported Media Type`.
- **Defense in Depth**: Middleware validates tokens across protected prefixes (`/home`, `/plan`, `/recurring`, `/protect`, `/borrow`, `/assistant`, `/settings`, `/consent`); BFF route handler redundantly validates cookies on non-public endpoints.
- **Security Headers & CSP**: Middleware injects production CSP with strictly NO `'unsafe-eval'`, script hash for inline theme init, `X-Frame-Options: DENY`, `Strict-Transport-Security`, `Permissions-Policy`, and Cache-Control `no-store` on authenticated views.
- **Theme System**: Zero-flash inline theme init script in `<head>`, supporting `light`, `dark`, and `system` modes with WCAG AA compliance and `prefers-reduced-motion` fallbacks.
- **i18n**: Multi-lingual dictionary supporting `en`, `ml` (Malayalam), and `manglish`. Non-English content is tagged with `needsReview: true` until verified by native reviewers.

## 4. Runbook & Troubleshooting

- **Port 3000 Address In Use (`EADDRINUSE`)**:
  ```cmd
  netstat -ano | findstr :3000
  taskkill /PID <PID> /F
  ```
- **Windows PowerShell Execution Policy (`npm.ps1 cannot be loaded`)**:
  Run command line binaries explicitly using `.cmd` wrappers: `npm.cmd test`, `npx.cmd playwright test`.
- **Playwright Browser Binaries Missing**:
  Run `npx playwright install chromium` from `apps/web`.

### Google Sign-In Setup (Google Cloud Console)
1. **OAuth Consent Screen**: In Google Cloud Console -> *APIs & Services -> OAuth consent screen*, configure User Type (External for testing), app name (`Float`), support email, and add your test Google accounts under *Test users*.
2. **Create Web Client ID**: Go to *Credentials -> Create Credentials -> OAuth client ID -> Web application*.
3. **Authorized JavaScript Origins**: Add **both** `http://localhost:3000` and `http://127.0.0.1:3000` (and your production origin when deploying). Leave *Authorized redirect URIs* blank for GIS popup/ID-token flow.
4. **Environment Variables**: Set the exact same Web Client ID in:
   - `apps/api/.env`: `PFA_GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com`
   - `apps/web/.env.local`: `NEXT_PUBLIC_GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com`

### Manual Google Sign-In Test Checklist
- [ ] `GET /api/auth/capabilities` returns `{ "google": true, "google_client_id": "..." }`.
- [ ] Official Google Sign-In button renders visibly on `/login` and `/signup` (and switches theme in light/dark).
- [ ] Clicking the button opens Google's account chooser popup (no CSP or COOP errors in DevTools).
- [ ] Completing login sends `POST /api/auth/google` -> FastAPI `/api/v1/auth/google`, sets `float_token`, and redirects to `/home`.
- [ ] Blocking `accounts.google.com/gsi/client` (e.g., DevTools request blocking) shows the friendly fallback and leaves email login usable.

## 5. Security Advisories & Audit Exceptions (npm audit)

Running `npm audit` currently flags 6 advisories in the upstream Next.js ecosystem. Upgrading requires a breaking major change to Next.js 16/React 19. All 6 are audited as non-exploitable exceptions in Float:

| Advisory ID | Severity | Affected Package / Feature | Float Usage & Exposure Analysis | Exception Status |
|---|---|---|---|---|
| GHSA-2464-fhr4-w9xw | Critical | `next` Image Optimizer (SVG RCE) | Float does not use `next/image` with remote patterns or user SVGs | Documented Exception |
| GHSA-p3m5-59mp-jv5r | High | `next` App Router Server Actions DoS | Float uses REST route handlers (`/api/*`), no Server Actions | Documented Exception |
| GHSA-9g9p-9gw9-jx7f | Moderate | `next` Image Optimizer remotePatterns | Remote patterns not configured | Documented Exception |
| GHSA-pc58-hwjq-p385 | Moderate | `next` Response forwarding disclosure | Self-hosted response header injection; mitigated by BFF proxy | Documented Exception |
| GHSA-5j98-mcp5-4vw2 | High | `glob` CLI command injection | Dev-only transitive dependency via `eslint-config-next` | Documented Exception |
| GHSA-6g55-p6wh-862q | High | `postcss` sourceMappingURL read | Build-time CSS processing only; no user CSS compiled | Documented Exception |

### Upgrade Path & Test Plan
1. **Target**: Upgrade to Next.js 15+ / 16 in a separate milestone branch (`feature/next-major-upgrade`).
2. **Breaking Changes**: Review React 19 async request params (`params` / `searchParams` as Promises), Server Actions syntax, and eslint config v9 migration.
3. **Verification Plan**: Run `npm test` (unit/security), `npm run build` (25 static/dynamic pages), and `npx playwright test` (all 8 flows across themes and mobile viewports).

### Codebase Verification Evidence
- **"use server" Grep Audit**: 0 occurrences across `apps/web/` (`app/`, `components/`, `lib/`). No Server Actions are declared or exposed; Float uses strictly REST BFF route handlers in `app/api/*`.
- **Remote Image & SVG Configuration**: `apps/web/next.config.mjs` has no `images.remotePatterns` (unconfigured) and `dangerouslyAllowSVG` is unconfigured/false. All UI icons are static JSX Lucide vectors, completely mitigating SVG RCE advisories.
