import { execSync, spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

async function waitForUrl(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

export default async function globalSetup() {
  const webDir = path.resolve(__dirname, "../..");
  const repoRoot = path.resolve(webDir, "../..");
  const apiDir = path.join(repoRoot, "apps", "api");
  const venvPython =
    process.platform === "win32"
      ? path.join(repoRoot, "venv", "Scripts", "python.exe")
      : path.join(repoRoot, "venv", "bin", "python");
  const pythonBin = fs.existsSync(venvPython) ? venvPython : "python";

  let dbUrl = process.env.PFA_DATABASE_URL;
  if (!dbUrl) {
    const apiEnvPath = path.join(apiDir, ".env");
    if (fs.existsSync(apiEnvPath)) {
      const envLine = fs
        .readFileSync(apiEnvPath, "utf8")
        .split(/\r?\n/)
        .find((l) => l.startsWith("PFA_DATABASE_URL="));
      if (envLine) {
        dbUrl = envLine.slice("PFA_DATABASE_URL=".length).trim().replace(/^['"]|['"]$/g, "");
      }
    }
  }
  dbUrl = dbUrl || "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/float";

  const apiPort = process.env.FULLSTACK_API_PORT || "8010";
  const webPort = process.env.FULLSTACK_WEB_PORT || "3010";
  const apiUrl = `http://127.0.0.1:${apiPort}`;
  const webUrl = `http://127.0.0.1:${webPort}`;

  const sharedEnv: NodeJS.ProcessEnv = {
    ...process.env,
    PFA_DATABASE_URL: dbUrl,
    PFA_APP_ENV: "development",
    PFA_LLM_PROVIDER: "fake",
    PFA_SMS_PROVIDER: "fake",
    PFA_JWT_SECRET_KEY: "fullstack-e2e-secret-key-min-32-chars-long-001",
    PFA_ALLOWED_HOSTS: "127.0.0.1,localhost,testserver",
    PFA_CORS_ALLOWED_ORIGINS: `${webUrl},http://localhost:${webPort}`,
    PFA_API_URL: apiUrl,
    API_BASE_URL: apiUrl,
    NEXT_PUBLIC_API_URL: apiUrl,
    NEXT_PUBLIC_ENABLE_CALCULATORS: "true",
    NEXT_PUBLIC_ENABLE_GOALS: "true",
    NEXT_PUBLIC_ENABLE_SUBSCRIPTIONS: "true",
    NEXT_PUBLIC_ENABLE_NOTIFICATIONS: "true",
  };

  execSync(`"${pythonBin}" -m alembic upgrade head`, {
    cwd: apiDir,
    env: sharedEnv,
    stdio: "inherit",
  });

  const apiProc: ChildProcess = spawn(
    pythonBin,
    [
      "-c",
      `import asyncio, sys, uvicorn; cfg = uvicorn.Config('app.main:app', host='127.0.0.1', port=${apiPort}); srv = uvicorn.Server(cfg); asyncio.run(srv.serve(), loop_factory=asyncio.SelectorEventLoop) if sys.platform == 'win32' else asyncio.run(srv.serve())`,
    ],
    { cwd: apiDir, env: sharedEnv, stdio: "inherit" },
  );

  await waitForUrl(`${apiUrl}/ready`, 60_000);

  const nextBin = path.join(webDir, "node_modules", "next", "dist", "bin", "next");
  const webProc: ChildProcess = spawn(process.execPath, [nextBin, "start", "-p", webPort], {
    cwd: webDir,
    env: sharedEnv,
    stdio: "inherit",
  });

  await waitForUrl(`${webUrl}/login`, 60_000);

  return async () => {
    for (const proc of [webProc, apiProc]) {
      if (proc.pid) {
        try {
          if (process.platform === "win32") {
            execSync(`taskkill /PID ${proc.pid} /T /F`, { stdio: "ignore" });
          } else {
            proc.kill("SIGTERM");
          }
        } catch {
          // already exited
        }
      }
    }
  };
}
