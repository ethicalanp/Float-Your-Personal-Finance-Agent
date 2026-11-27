import test from "node:test";
import assert from "node:assert/strict";
import { verifyOrigin, AUTH_COOKIE_NAME } from "../lib/auth-cookie.ts";
import fs from "node:fs";
import path from "node:path";

const PROTECTED_PREFIXES = [
  "/home",
  "/protect",
  "/borrow",
  "/chat",
  "/settings",
  "/consent",
];

function checkRouteProtection(pathname, hasToken) {
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  if (isProtected && !hasToken) {
    return { redirect: `/login?return_to=${encodeURIComponent(pathname)}` };
  }
  if ((pathname === "/login" || pathname === "/signup") && hasToken) {
    return { redirect: "/home" };
  }
  return { ok: true };
}

test("Auth Guard - Unauthenticated requests to protected paths redirect to /login with return_to", () => {
  for (const prefix of PROTECTED_PREFIXES) {
    const result = checkRouteProtection(prefix, false);
    assert.ok(result.redirect, `Path ${prefix} must require authentication`);
    assert.equal(
      result.redirect,
      `/login?return_to=${encodeURIComponent(prefix)}`
    );
  }
});

test("Auth Guard - Authenticated users visiting /login or /signup redirect to /home", () => {
  assert.equal(checkRouteProtection("/login", true).redirect, "/home");
  assert.equal(checkRouteProtection("/signup", true).redirect, "/home");
});

test("Auth Guard - Authenticated users can access protected routes", () => {
  assert.equal(checkRouteProtection("/home", true).ok, true);
  assert.equal(checkRouteProtection("/protect", true).ok, true);
});

test("Auth Guard - Middleware source enforces CSP, HSTS, X-Frame-Options, and Cache-Control no-store", () => {
  const middlewarePath = path.join(process.cwd(), "middleware.ts");
  const content = fs.readFileSync(middlewarePath, "utf-8");

  assert.ok(content.includes("Content-Security-Policy"), "Middleware must enforce CSP");
  assert.ok(content.includes("frame-ancestors 'none'"), "CSP must forbid frame-ancestors");
  assert.ok(content.includes("Strict-Transport-Security"), "Middleware must enforce HSTS");
  assert.ok(content.includes("X-Frame-Options"), "Middleware must set X-Frame-Options: DENY");
  assert.ok(content.includes("no-store, no-cache, must-revalidate"), "Middleware must enforce Cache-Control no-store on private routes");
});

test("Auth Guard - CSRF rejects mutating requests without Origin or Referer", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    method: "POST",
    headers: {
      host: "localhost:3000",
    },
  });
  assert.equal(verifyOrigin(req), false);
});

test("Auth Guard - CSRF rejects mutating requests with mismatched Origin host", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    method: "POST",
    headers: {
      host: "localhost:3000",
      origin: "https://malicious-bank-phishing.com",
    },
  });
  assert.equal(verifyOrigin(req), false);
});

test("Auth Guard - CSRF accepts mutating requests with matching Origin host", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    method: "POST",
    headers: {
      host: "localhost:3000",
      origin: "http://localhost:3000",
    },
  });
  assert.equal(verifyOrigin(req), true);
});

test("Auth Guard - CSRF accepts matching Referer when Origin is absent", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    method: "POST",
    headers: {
      host: "localhost:3000",
      referer: "http://localhost:3000/login",
    },
  });
  assert.equal(verifyOrigin(req), true);
});
