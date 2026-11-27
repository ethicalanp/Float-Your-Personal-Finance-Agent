# Real-Device & Assistive Technology Manual Checklist

Use this checklist before production releases alongside automated Playwright (`chromium`, `firefox`, `webkit`, `mobile`, `mobile-safari`) checks.

## 1. Android Chrome (Viewport ~360px–412px)
- [ ] **Auth & Consent**: `/login`, `/signup`, `/consent` inputs are reachable with soft keyboard open; no obscured submit buttons; Google Sign-In button renders cleanly.
- [ ] **Plan & Calculators**: `PlanTabs` segmented control fits at `360px` with zero horizontal page scroll; sliders + numeric inputs sync smoothly.
- [ ] **Protect & 1930**: `tel:1930` dialer link opens Android phone dialer; "Copy 1930 Summary Draft" copies text to clipboard.
- [ ] **Float.ai Chat**: IME composition (Malayalam/Manglish Gboard) does not submit prematurely on `Enter`.
- [ ] **Themes**: Light and Dark themes preserve readable contrast on cards, badges, and alerts.

## 2. iOS Safari (iPhone SE 375px / iPhone 13+ 390px)
- [ ] **Auth Cookies & Redirects**: Login sets `float_token` cookie; `/recurring` redirects `308` to `/plan/recurring`; `/assistant` redirects `308` to `/chat`.
- [ ] **Input Zoom Prevention**: Form inputs use `>= 16px` or viewport behavior does not break layout on focus.
- [ ] **Safe Area & Sticky Nav**: Bottom/top navigation never overlaps iOS home indicator or notch.
- [ ] **PDF/CSV Upload**: File picker accepts `.csv` and `.pdf` from iOS Files app cleanly.

## 3. Screen Reader (TalkBack on Android / VoiceOver on iOS & macOS)
- [ ] **Skip Link**: First `Tab` / swipe lands on "Skip to main content" and moves focus to `#main-content`.
- [ ] **PlanTabs**: Announced as `tablist` with `tab` items (`selected` / `not selected`), `ArrowLeft`/`ArrowRight` moves focus and switches routes.
- [ ] **Live Regions**: Float.ai responses (`aria-live="polite"`) and `OfflineBanner` (`role="alert"`, `aria-live="assertive"`) announce updates automatically.
- [ ] **Form Labels & Errors**: Every input announces its label; `409` conflict and validation errors are announced with `role="alert"`.
