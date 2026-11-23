# Float Web Landing Page (`apps/web`)

Modern, high-performance landing page for **Float**, built with Next.js (App Router), TypeScript, and Tailwind CSS. The visual direction reuses the art direction and layout dynamics ("the window" with layered atmospheric horizons and floating conversation/alert cards) of the design reference while completely eliminating all fictional testimonials, customer logos, fake counts, and ratings.

---

## Architecture & Structure

- **All Copy**: Maintained in a single editable file: [`content/landing.ts`](file:///d:/PersonalFinanceAgent/apps/web/content/landing.ts).
- **Design Reference & Tokens**:
  - Documentation: [`docs/web/design-notes.md`](file:///d:/PersonalFinanceAgent/docs/web/design-notes.md)
  - Open-Source Credits & Font Attribution: [`docs/web/credits.md`](file:///d:/PersonalFinanceAgent/docs/web/credits.md)
  - Styling & Animations: [`app/globals.css`](file:///d:/PersonalFinanceAgent/apps/web/app/globals.css) and [`tailwind.config.ts`](file:///d:/PersonalFinanceAgent/apps/web/tailwind.config.ts).
- **Components**:
  - [`components/Logo.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/Logo.tsx): Clearly marked `<Logo />` placeholder for the Float wordmark in a fixed-size container.
  - [`components/Navbar.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/Navbar.tsx): Sticky frosted header with responsive mobile sheet menu.
  - [`components/Hero.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/Hero.tsx): Indian personal finance focus (Plan, Protect, Borrow) with code-drawn abstract UI cards over layered mountain ridges (no stock photos).
  - [`components/ThreePillars.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/ThreePillars.tsx): Interactive tabs for Plan (bank statements/SMS), Protect (fraud defense), and Borrow (indicative readiness).
  - [`components/HowItWorks.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/HowItWorks.tsx): 4-step clear progression.
  - [`components/LiveScamDemo.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/LiveScamDemo.tsx): Live interactive test box calling `POST /api/v1/protect/check` handling loading, error, and 503 states.
  - [`components/SecuritySection.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/SecuritySection.tsx): Honest security safeguards (masked accounts, explicit consent, no money movement).
  - [`components/FaqSection.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/FaqSection.tsx): Accessible accordion addressing credit bureau questions, data handling, and supported languages.
  - [`components/Footer.tsx`](file:///d:/PersonalFinanceAgent/apps/web/components/Footer.tsx): Night CTA, legal links, large watermark, and mandatory legal disclaimer: *"Float provides indicative information only. It is not a credit score, financial advice or a lender's decision."*

---

## Running Locally

### Development Server
```bash
cd apps/web
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the landing page.

### Production Build
```bash
cd apps/web
npm run build
npm run start
```

### Running Smoke Tests
```bash
cd apps/web
npm test
```

### Playwright E2E Tests
```bash
cd apps/web
npx playwright test
```
