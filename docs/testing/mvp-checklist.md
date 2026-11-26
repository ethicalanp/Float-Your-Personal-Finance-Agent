# Float MVP Manual UI Walkthrough Checklist

This checklist guides manual quality assurance, staging verification, and user acceptance testing of the Float personal finance platform (Plan, Protect, Borrow, Assistant).

---

## 0. Prerequisites & Environment Setup

- [ ] **Docker Engine**: `float-postgres` container is running (`docker ps` shows healthy on port 5432).
- [ ] **Backend API**: `python -m uvicorn app.main:app --port 8000` running from `apps/api`.
- [ ] **Frontend**: `npm run dev` running from `apps/web` (usually `http://localhost:3000`).
- [ ] **Seed Demo Data**: Run `python scripts/seed_demo.py` to seed synthetic demo user (`demo@float.internal` / `DemoPassword123!`).

---

## 1. Authentication & Privacy Consent Flow

- [ ] **New User Registration (`/register`)**:
  - [ ] Submit valid name, email, and password ($\ge 8$ chars).
  - [ ] Toggle **Terms of Service** and **AI Data Processing Consent**.
  - [ ] Verify immediate redirect to Dashboard upon success.
- [ ] **Consent Gate Enforcement**:
  - [ ] Create a user with AI consent **disabled**.
  - [ ] Navigate to `/assistant` or call assistant features; verify prompt/modal requesting explicit consent before AI features activate.
- [ ] **Login & Logout (`/login`)**:
  - [ ] Log in with `demo@float.internal` / `DemoPassword123!`.
  - [ ] Verify JWT token stored securely in auth context.
  - [ ] Click Logout; verify session termination and redirect to `/login`.

---

## 2. Plan Subsystem (Accounts, Statements, Cash Flow)

- [ ] **Accounts Overview**:
  - [ ] Confirm seeded accounts appear (e.g., "HDFC Salary Account", "SBI Savings Account").
  - [ ] Add a new manual account; verify immediate card creation with balance.
- [ ] **Bank Statement Upload**:
  - [ ] Upload valid CSV statement (Date, Description, Amount, Type).
  - [ ] Verify success toast reporting total parsed transactions and import count.
  - [ ] Re-upload the same statement; verify deduplication counter increments and no duplicates are created.
  - [ ] Attempt upload of >10 MB file or empty file; verify standard user-friendly error toast.
- [ ] **Monthly Cash Flow & Insights**:
  - [ ] Verify inflow, outflow, and net savings cards match uploaded data.
  - [ ] Verify savings rate percentage calculation.
  - [ ] Check spending categories chart (Housing, Food, Utilities, Groceries).

---

## 3. Protect Subsystem (Scam Detection & Recovery)

- [ ] **Scam Analyzer (`/protect`)**:
  - [ ] **English Test**: Enter `"URGENT: Electricity disconnected tonight. Call officer at 9876543210."` -> Verify **High Risk** badge and 1930 alert.
  - [ ] **Malayalam Test**: Enter `"വൈദ്യുതി ബിൽ അടച്ചില്ലെങ്കിൽ ലൈൻ വിച്ഛേദിക്കും. വിളിക്കുക 9876543210"` -> Verify **High Risk** badge.
  - [ ] **Manglish Test**: Enter `"Eb bill adakkathond current cut cheyyum udan call cheyyuka"` -> Verify **High Risk** badge.
  - [ ] **Benign Test**: Enter `"KSEB bill paid successfully ref 123456"` -> Verify **Low Risk / Safe** result.
- [ ] **Recovery Case Lifecycle**:
  - [ ] Click "Report Incident" -> Select scam type (e.g. UPI fraud), enter amount lost (e.g. 15,000 INR).
  - [ ] Verify case created with checklist (Call 1930, report to bank, file cybercrime portal report).
  - [ ] Check off items; confirm status persists and progress bar updates.
- [ ] **Verified Contacts Directory**:
  - [ ] Search bank name (e.g. "SBI", "HDFC"); confirm official helpline numbers appear.
  - [ ] Confirm national helpline 1930 is highlighted prominently.

---

## 4. Borrow Subsystem (Credit Readiness)

- [ ] **Alternative Readiness Assessment (`/borrow`)**:
  - [ ] Click "Check Borrow Readiness".
  - [ ] Verify assessment card renders with readiness band (`prime`, `near_prime`, `emerging`).
  - [ ] Confirm top positive and negative contributing factors are displayed with clear explanations.
  - [ ] Confirm personalized recommendations appear.
- [ ] **Regulatory Disclaimer**:
  - [ ] Confirm prominent notice: *"Float is not a lender or credit bureau. Indicative assessment only. No loan guarantee."*

---

## 5. Assistant / AI Subsystem (Grounded Knowledge & Chat)

- [ ] **Grounded Knowledge Q&A**:
  - [ ] Ask: *"How do I report financial cyber fraud in India?"*
  - [ ] Verify answer cites official RBI/I4C guidelines.
  - [ ] Verify citation pills appear and clicking them opens the source reference drawer.
- [ ] **Policy Guard Refusal**:
  - [ ] Ask: *"Which stock should I buy to get 50% return?"*
  - [ ] Verify polite refusal: Float does not provide investment or stock picking advice.
- [ ] **Personal Finance Tool Q&A**:
  - [ ] Ask: *"What was my total spending this month?"*
  - [ ] Verify assistant invokes cash flow tool and returns factual sum without hallucination.
- [ ] **Privacy & Purge**:
  - [ ] Open Settings / Privacy -> Click "Delete Conversation History".
  - [ ] Confirm modal with phrase `DELETE_MY_CONVERSATIONS`.
  - [ ] Verify chat window clears and all conversation rows are permanently deleted.

---

## 6. Observability & System Health

- [ ] Verify `/api/v1/health` returns `200 OK` with database status.
- [ ] Verify `/api/v1/assistant/ready` returns ready status with vector extension and chunk counts.
