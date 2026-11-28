# Float Feature & E2E Coverage Matrix

| Feature / Route | Backend Test | Web Unit Test | Mocked E2E | Fullstack E2E | Status |
|---|---|---|---|---|---|
| Auth Flows (`/login`, `/signup`, `/forgot-password`, `/reset-password`, `/verify-email`, `/consent`) | `tests/test_auth*.py` | `auth-login-flow.test.mjs`, `auth-bff.test.mjs` | `login-e2e.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/auth-and-profile.spec.ts` | Covered |
| Home & Health Score (`/home`) | `tests/test_health_score.py` | `health-score.test.mjs` | `e2e-flow.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/home-protect-borrow-chat.spec.ts` | Covered |
| Statement Upload (`/plan`, `/home`) | `tests/test_statement_parsing_suite.py`, `tests/test_age_gate_and_upload_n1.py` | `security-streaming-upload.test.mjs` | `e2e-flow.spec.ts` | `fullstack/home-protect-borrow-chat.spec.ts` | Covered |
| Protect, UPI Check & 1930 Flow (`/protect`) | `tests/test_protect*.py` | `component-states.test.mjs` | `e2e-flow.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/home-protect-borrow-chat.spec.ts` | Covered |
| Borrow & EMI (`/borrow`) | `tests/test_borrow*.py` | `component-states.test.mjs` | `e2e-flow.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/home-protect-borrow-chat.spec.ts` | Covered |
| Float.ai Chat (`/chat`) | `tests/ai/test_agent_orchestrator.py` | `float-ai-chat.test.mjs` | `float-ai-chat-e2e.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/home-protect-borrow-chat.spec.ts` | Covered |
| Budget Plan (`/plan`) | `tests/test_budget_recurring.py` | `budget-recurring.test.mjs` | `budget-recurring-e2e.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Recurring & Bills (`/plan/recurring`) | `tests/test_budget_recurring.py` | `budget-recurring.test.mjs` | `budget-recurring-e2e.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Goals (`/plan/goals`) | `tests/test_goals_emergency.py` | `goals-emergency.test.mjs` | `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Emergency Fund (`/plan/emergency-fund`) | `tests/test_goals_emergency.py` | `goals-emergency.test.mjs` | `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Subscriptions (`/plan/subscriptions`) | `tests/test_subscriptions_networth.py` | `subscriptions-networth.test.mjs` | `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Net Worth (`/plan/net-worth`) | `tests/test_subscriptions_networth.py` | `subscriptions-networth.test.mjs` | `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Calculators & SIP Step-Up/Reverse (`/plan/calculators`) | `tests/test_calculators.py` | `calculators.test.mjs` | `cross-browser-a11y.spec.ts` | `fullstack/plan-and-calculators.spec.ts` | Covered |
| Notifications (`/profile/settings`, `/plan/recurring`) | `tests/test_budget_recurring.py` | `profile.test.mjs` | `profile-e2e.spec.ts` | `fullstack/auth-and-profile.spec.ts` | Covered |
| Profile & Settings (`/profile`, `/profile/settings`) | `tests/test_profile.py` | `profile.test.mjs` | `profile-e2e.spec.ts` | `fullstack/auth-and-profile.spec.ts` | Covered |
| Public Pages (`/`, `/privacy`, `/terms`, `/security`, `/download`) | — | `smoke-verify.mjs` | `landing-smoke.spec.ts`, `cross-browser-a11y.spec.ts` | `fullstack/auth-and-profile.spec.ts` | Covered |
