# Web skill (Next.js)

## Architecture & Principles
- **Next.js App Router + TypeScript**: Reuses the landing-page design system and CSS tokens (`var(--cnl-*)`) across all screens.
- **Thin Client over OpenAPI**: Shared typed client in `packages/api-client` (`FloatApiClient`), eliminating frontend business logic.
- **BFF Auth in httpOnly Cookies**: Tokens are stored strictly in `httpOnly`, `SameSite=lax` cookies named `float_token`. Never stored in `localStorage`.
- **CSRF & Origin Verification**: Mutating BFF route handlers (`POST`, `PUT`, `PATCH`, `DELETE`) verify `Origin` or `Referer` header against `Host`.
- **Content Security Policy (CSP)**: Set via `middleware.ts` alongside `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.
- **Feature Flag Registry**: `lib/features.ts` gates planned features until backend endpoints are implemented.
- **Safe Rendering (Float.ai `/chat`)**: Float.ai responses are sanitized with `SafeMarkdown` (zero `dangerouslySetInnerHTML`, raw HTML stripped). Citations strictly enforce `https://` and `rel="noopener noreferrer"`. `/assistant` permanently redirects (`308`) to `/chat`.
- **Navigation & Profile Settings**: Top-level nav (`AppNav`) exposes Home, Plan, Recurring, Protect, Borrow, Float.ai, and Profile (with a Profile menu + section on `/profile` opening `/profile/settings`). `/settings` returns a `308` permanent redirect to `/profile/settings` via `next.config.mjs`.
- **Disclaimers**: Mandatory indicative disclaimers on Borrow and Assistant per AGENTS.md rules.

## Core Commands
- **Development Server**: `npm run dev` (starts on port 3000)
- **Production Build**: `npm run build`
- **Linting**: `npm run lint`
- **Type Checking**: `npx tsc --noEmit`
- **Unit & Smoke Tests**: `npm test`
- **End-to-End Suite**: `npm run test:e2e` (requires Playwright browser binaries)

## Windows & CI Gotchas
- **Transient Node.js EPERM on `.next/static`**: On Windows, file locking during webpack cache directory creation can trigger transient `EPERM: operation not permitted, mkdir`. Rerun the command once; it resolves immediately.
- **Playwright Browser Binaries**: In sandboxed environments with no external network access, `npx playwright install` cannot fetch browser binaries (Chromium/Firefox/WebKit). Unit and integration tests run via `node --test` with zero external dependencies.
- **BFF Proxy Path**: In browser contexts, `getApiClient()` routes via `/api/backend/*` to proxy requests with the `float_token` cookie attached, avoiding CORS and token leakage.
