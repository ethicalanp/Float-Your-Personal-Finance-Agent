import test from "node:test";
import assert from "node:assert/strict";
import { verifyOrigin, AUTH_COOKIE_NAME, COOKIE_OPTIONS } from "../lib/auth-cookie.ts";

test("BFF Auth - verifyOrigin accepts same host", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    headers: {
      host: "localhost:3000",
      origin: "http://localhost:3000",
    },
  });
  assert.equal(verifyOrigin(req), true);
});

test("BFF Auth - verifyOrigin rejects cross-origin host mismatch", () => {
  const req = new Request("http://localhost:3000/api/auth/login", {
    headers: {
      host: "localhost:3000",
      origin: "http://attacker-evil-site.com",
    },
  });
  assert.equal(verifyOrigin(req), false);
});

test("BFF Auth - cookie options are strictly httpOnly and SameSite=lax", () => {
  assert.equal(AUTH_COOKIE_NAME, "float_token");
  assert.equal(COOKIE_OPTIONS.httpOnly, true);
  assert.equal(COOKIE_OPTIONS.sameSite, "lax");
  assert.equal(COOKIE_OPTIONS.path, "/");
  assert.ok(COOKIE_OPTIONS.maxAge > 0);
});
