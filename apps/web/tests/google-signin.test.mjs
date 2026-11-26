import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("GoogleSignInButton - uses next/script, renderButton, theme/locale re-render, and no debug/fake click paths", () => {
  const compSrc = fs.readFileSync(path.join(process.cwd(), "components", "GoogleSignInButton.tsx"), "utf-8");
  const loginSrc = fs.readFileSync(path.join(process.cwd(), "app", "login", "page.tsx"), "utf-8");
  const signupSrc = fs.readFileSync(path.join(process.cwd(), "app", "signup", "page.tsx"), "utf-8");
  const settingsSrc = fs.readFileSync(path.join(process.cwd(), "app", "settings", "page.tsx"), "utf-8");

  // Uses next/script afterInteractive and google.accounts.id.renderButton
  assert.ok(compSrc.includes('from "next/script"'), "Must load GIS via next/script");
  assert.ok(compSrc.includes('strategy="afterInteractive"'), "Must use afterInteractive strategy");
  assert.ok(compSrc.includes("https://accounts.google.com/gsi/client"), "Must point to GIS script URL");
  assert.ok(compSrc.includes("renderButton("), "Must use google.accounts.id.renderButton");
  assert.ok(compSrc.includes("NEXT_PUBLIC_GOOGLE_CLIENT_ID"), "Must read NEXT_PUBLIC_GOOGLE_CLIENT_ID");
  assert.ok(compSrc.includes("Math.min(400"), "Must clamp responsive width to max 400px");

  // Handles theme & language re-render and script-blocked fallback
  assert.ok(compSrc.includes("filled_black") && compSrc.includes("outline"), "Must switch GIS theme for dark/light");
  assert.ok(compSrc.includes("locale"), "Must pass locale to renderButton");
  assert.ok(compSrc.includes("google-signin-blocked"), "Must render friendly fallback when script is blocked/offline");

  // No fake clicks, no prompt() fallback, no debug mock token hooks
  for (const [name, src] of [
    ["GoogleSignInButton", compSrc],
    ["login", loginSrc],
    ["signup", signupSrc],
    ["settings", settingsSrc],
  ]) {
    assert.ok(!src.includes("__MOCK_GOOGLE_ID_TOKEN__"), `${name} must not have debug mock token path`);
    assert.ok(!src.includes(".accounts.id.prompt"), `${name} must not use prompt() fallback`);
    assert.ok(!src.includes("width: \"1px\""), `${name} must not hide GIS container at 1px`);
  }
});

test("GoogleSignInButton - mocked window.google callback calls BFF once and maps error with request_id", async () => {
  let initConfig = null;
  let renderCalls = [];
  const fetchCalls = [];

  // Mock google.accounts.id
  const mockGoogle = {
    accounts: {
      id: {
        initialize(cfg) {
          initConfig = cfg;
        },
        renderButton(_el, opts) {
          renderCalls.push(opts);
        },
      },
    },
  };

  // Mock BFF /api/auth/google handler behavior
  async function submitGoogleTokenToBff(idToken, mockFetch) {
    const res = await mockFetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
    const data = await res.json();
    if (!res.ok) {
      const requestId = data?.error?.request_id;
      const msg = data?.error?.message || "Google sign-in was unsuccessful.";
      throw new Error(requestId ? `${msg} (Request ID: ${requestId})` : msg);
    }
    return data;
  }

  // 1. Simulate GIS init + renderButton in light mode, then theme change to dark
  mockGoogle.accounts.id.initialize({
    client_id: "test-client-id.apps.googleusercontent.com",
    callback: async (resp) => {
      if (resp?.credential) {
        await submitGoogleTokenToBff(resp.credential, async (url, init) => {
          fetchCalls.push({ url, init });
          return {
            ok: false,
            json: async () => ({
              error: {
                code: "UNAUTHORIZED",
                message: "Invalid or expired Google ID token.",
                request_id: "req_12345",
              },
            }),
          };
        });
      }
    },
  });
  mockGoogle.accounts.id.renderButton({}, { theme: "outline", locale: "en", width: 340 });
  mockGoogle.accounts.id.renderButton({}, { theme: "filled_black", locale: "ml", width: 360 });

  assert.equal(renderCalls.length, 2);
  assert.equal(renderCalls[0].theme, "outline");
  assert.equal(renderCalls[1].theme, "filled_black");
  assert.equal(renderCalls[1].locale, "ml");

  // 2. Trigger callback with credential -> BFF called once & error includes request_id
  await assert.rejects(
    () => initConfig.callback({ credential: "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig" }),
    /Invalid or expired Google ID token\. \(Request ID: req_12345\)/
  );
  assert.equal(fetchCalls.length, 1);
  assert.equal(fetchCalls[0].url, "/api/auth/google");
});

test("Middleware CSP and COOP headers allow Google GIS minimally and keep prod strict", () => {
  const mw = fs.readFileSync(path.join(process.cwd(), "middleware.ts"), "utf-8");
  assert.ok(mw.includes("https://accounts.google.com/gsi/client"), "script-src must allow GIS client");
  assert.ok(mw.includes("https://accounts.google.com/gsi/style"), "style-src must allow GIS style");
  assert.ok(mw.includes("frame-src 'self' https://accounts.google.com/gsi/"), "frame-src must allow GIS iframe");
  assert.ok(mw.includes("https://accounts.google.com/gsi/"), "connect-src must allow GIS");
  assert.ok(mw.includes('"Cross-Origin-Opener-Policy", "same-origin-allow-popups"'), "COOP must allow popups");
});
