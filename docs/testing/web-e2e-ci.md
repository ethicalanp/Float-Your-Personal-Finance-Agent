# Proposed `web-e2e` CI Job (Do Not Auto-Edit `.github/workflows/ci.yml`)

Add the following job to `.github/workflows/ci.yml` when ready to run full-stack Playwright E2E in GitHub Actions:

```yaml
  web-e2e:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: float_e2e
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install Python dependencies
        working-directory: apps/api
        run: pip install -e ".[dev]"
      - name: Install Web dependencies & Playwright Chromium
        working-directory: apps/web
        run: |
          npm ci
          npx playwright install --with-deps chromium
      - name: Build Next.js production bundle
        working-directory: apps/web
        run: npm run build
      - name: Run fullstack Playwright E2E
        working-directory: apps/web
        env:
          FULLSTACK_E2E: "1"
          CI: "true"
          PFA_DATABASE_URL: postgresql+psycopg://postgres:postgres@127.0.0.1:5432/float_e2e
        run: npx playwright test --project=fullstack --retries=1
      - name: Upload Playwright trace artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-traces
          path: apps/web/test-results/
          retention-days: 7
```
