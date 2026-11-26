import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { verifyOrigin, isSecureConnection, getCookieOptions } from "../lib/auth-cookie.ts";

test("1. Cookie Secure Flag - Always true in production, relaxed only for http://localhost in non-prod, x-forwarded-proto rules", () => {
  const origNodeEnv = process.env.NODE_ENV;
  const origTrust = process.env.TRUST_FORWARDED_PROTO;
  const origTrustProxy = process.env.TRUST_PROXY;

  try {
    // 1a. Always true when NODE_ENV=production, even on plain http://localhost
    process.env.NODE_ENV = "production";
    delete process.env.TRUST_FORWARDED_PROTO;
    delete process.env.TRUST_PROXY;

    const prodLocalReq = new Request("http://localhost:3000/api/auth/login", {
      headers: { host: "localhost:3000" },
    });
    assert.equal(isSecureConnection(prodLocalReq), true, "In production, secure must be true even on http://localhost");
    assert.equal(getCookieOptions(prodLocalReq).secure, true);

    const prodRemoteReq = new Request("https://app.float.in/api/auth/login", {
      headers: { host: "app.float.in" },
    });
    assert.equal(isSecureConnection(prodRemoteReq), true, "In production, secure must be true on remote HTTPS");

    // 1b. In non-production, relaxed ONLY for http://localhost (and 127.0.0.1)
    process.env.NODE_ENV = "development";

    const devLocalReq = new Request("http://localhost:3000/api/auth/login", {
      headers: { host: "localhost:3000" },
    });
    assert.equal(isSecureConnection(devLocalReq), false, "In non-production, relaxed for http://localhost");

    const devLoopbackReq = new Request("http://127.0.0.1:3000/api/auth/login", {
      headers: { host: "127.0.0.1:3000" },
    });
    assert.equal(isSecureConnection(devLoopbackReq), false, "In non-production, relaxed for http://127.0.0.1");

    const devRemoteReq = new Request("http://remote-preview.float.internal/api/auth/login", {
      headers: { host: "remote-preview.float.internal" },
    });
    assert.equal(isSecureConnection(devRemoteReq), true, "In non-production, non-localhost http must NOT be relaxed");

    // 1c. Don't trust x-forwarded-proto unless explicitly configured
    delete process.env.TRUST_FORWARDED_PROTO;
    delete process.env.TRUST_PROXY;
    const untrustedFwdReq = new Request("http://localhost:3000/api/auth/login", {
      headers: { host: "localhost:3000", "x-forwarded-proto": "https" },
    });
    assert.equal(
      isSecureConnection(untrustedFwdReq),
      false,
      "Must not trust x-forwarded-proto without explicit TRUST_FORWARDED_PROTO / TRUST_PROXY"
    );

    // 1d. Trust x-forwarded-proto when explicitly configured
    process.env.TRUST_FORWARDED_PROTO = "true";
    const trustedFwdReq = new Request("http://localhost:3000/api/auth/login", {
      headers: { host: "localhost:3000", "x-forwarded-proto": "https" },
    });
    assert.equal(
      isSecureConnection(trustedFwdReq),
      true,
      "Must trust x-forwarded-proto when TRUST_FORWARDED_PROTO=true"
    );
  } finally {
    process.env.NODE_ENV = origNodeEnv;
    if (origTrust !== undefined) process.env.TRUST_FORWARDED_PROTO = origTrust;
    else delete process.env.TRUST_FORWARDED_PROTO;
    if (origTrustProxy !== undefined) process.env.TRUST_PROXY = origTrustProxy;
    else delete process.env.TRUST_PROXY;
  }
});

test("2. CSRF Loopback Alias - Applies only outside production; in production Origin must match configured site origin exactly", () => {
  const origNodeEnv = process.env.NODE_ENV;
  const origSiteOrigin = process.env.SITE_ORIGIN;
  const origAppUrl = process.env.NEXT_PUBLIC_APP_URL;

  try {
    // 2a. Outside production: Loopback alias IS allowed
    process.env.NODE_ENV = "development";
    delete process.env.SITE_ORIGIN;
    delete process.env.NEXT_PUBLIC_APP_URL;

    const devReq = new Request("http://127.0.0.1:3000/api/auth/login", {
      method: "POST",
      headers: { host: "127.0.0.1:3000", origin: "http://localhost:3000" },
    });
    assert.equal(verifyOrigin(devReq), true, "Outside production, loopback alias (localhost vs 127.0.0.1) is accepted");

    // 2b. In production: Loopback alias is FORBIDDEN
    process.env.NODE_ENV = "production";
    process.env.SITE_ORIGIN = "https://app.float.in";

    const prodLoopbackReq = new Request("http://127.0.0.1:3000/api/auth/login", {
      method: "POST",
      headers: { host: "127.0.0.1:3000", origin: "http://localhost:3000" },
    });
    assert.equal(verifyOrigin(prodLoopbackReq), false, "In production, loopback alias must be strictly rejected");

    // 2c. In production: Origin must match configured site origin exactly
    const prodValidReq = new Request("https://app.float.in/api/auth/login", {
      method: "POST",
      headers: { host: "app.float.in", origin: "https://app.float.in" },
    });
    assert.equal(verifyOrigin(prodValidReq), true, "In production, matching configured origin is accepted");

    const prodWrongOriginReq = new Request("https://app.float.in/api/auth/login", {
      method: "POST",
      headers: { host: "app.float.in", origin: "https://evil-spoof.app.float.in" },
    });
    assert.equal(verifyOrigin(prodWrongOriginReq), false, "In production, mismatched origin is rejected");
  } finally {
    process.env.NODE_ENV = origNodeEnv;
    if (origSiteOrigin !== undefined) process.env.SITE_ORIGIN = origSiteOrigin;
    else delete process.env.SITE_ORIGIN;
    if (origAppUrl !== undefined) process.env.NEXT_PUBLIC_APP_URL = origAppUrl;
    else delete process.env.NEXT_PUBLIC_APP_URL;
  }
});

test("3. CSP 'unsafe-eval' - Permitted only in development CSP; production CSP never contains it", () => {
  // Static code inspection of middleware.ts
  const middlewareSrc = fs.readFileSync(path.join(process.cwd(), "middleware.ts"), "utf-8");

  // Verify branching on process.env.NODE_ENV === "production"
  assert.ok(middlewareSrc.includes('const isProd = process.env.NODE_ENV === "production"'), "Must determine isProd from NODE_ENV");
  assert.ok(middlewareSrc.includes("SCRIPT_SRC"), "Must define SCRIPT_SRC directive");

  // Extract SCRIPT_SRC definition
  const scriptSrcMatch = middlewareSrc.match(/const SCRIPT_SRC = isProd\s*\?\s*("[\s\S]*?")\s*:\s*("[\s\S]*?");/);
  assert.ok(scriptSrcMatch, "Must define SCRIPT_SRC with ternary on isProd");

  const prodBranch = scriptSrcMatch[1].trim();
  const devBranch = scriptSrcMatch[2].trim();

  // Production branch must strictly exclude 'unsafe-eval' and permit Google Identity Services
  assert.ok(!prodBranch.includes("'unsafe-eval'"), `Production CSP branch must NEVER contain 'unsafe-eval': got ${prodBranch}`);
  assert.ok(prodBranch.includes("script-src 'self' 'unsafe-inline'"));
  assert.ok(prodBranch.includes("https://accounts.google.com/gsi/client"), "Must allow Google Identity Services script");

  // Development branch permits 'unsafe-eval' for HMR
  assert.ok(devBranch.includes("'unsafe-eval'"), `Development CSP branch must contain 'unsafe-eval': got ${devBranch}`);

  // CSP_HEADER in production must never contain 'unsafe-eval'
  const cspHeaderMatch = middlewareSrc.match(/const CSP_HEADER = \[([\s\S]*?)\]\.join/);
  assert.ok(cspHeaderMatch, "Must define CSP_HEADER array");
  const directives = cspHeaderMatch[1];
  assert.ok(!directives.includes("'unsafe-eval'"), "Static CSP directives must not contain 'unsafe-eval'");
});

test("4. Native Form Fallback - No credential or OTP can appear in a URL (GET) on login, signup, reset and OTP forms", () => {
  const formFiles = [
    { name: "login", path: path.join(process.cwd(), "app", "login", "page.tsx") },
    { name: "signup", path: path.join(process.cwd(), "app", "signup", "page.tsx") },
    { name: "reset-password", path: path.join(process.cwd(), "app", "reset-password", "page.tsx") },
    { name: "forgot-password", path: path.join(process.cwd(), "app", "forgot-password", "page.tsx") },
  ];

  for (const formFile of formFiles) {
    const src = fs.readFileSync(formFile.path, "utf-8");

    // Must never contain method="get"
    assert.ok(!src.toLowerCase().includes('method="get"'), `${formFile.name} must never contain method='get'`);

    // Every form must explicitly declare method="post"
    const formMatches = src.match(/<form[\s\S]*?>/g) || [];
    assert.ok(formMatches.length > 0, `${formFile.name} must contain at least one <form>`);

    for (const formTag of formMatches) {
      assert.ok(
        formTag.includes('method="post"'),
        `${formFile.name} form tag [${formTag}] must explicitly declare method="post"`
      );
      assert.ok(
        formTag.includes('action="#"') || formTag.includes("action="),
        `${formFile.name} form tag [${formTag}] must declare action="#" to prevent native navigation`
      );
    }

    // Must include noscript fallback warning user that JS is required for secure authentication
    assert.ok(src.includes("<noscript>"), `${formFile.name} must contain a <noscript> banner`);
  }
});
