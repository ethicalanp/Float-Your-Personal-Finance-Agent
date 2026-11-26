import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("Profile page - exists in AppNav, middleware protected routes, and supports all required states", () => {
  const navSrc = fs.readFileSync(path.join(process.cwd(), "components", "AppNav.tsx"), "utf-8");
  const mwSrc = fs.readFileSync(path.join(process.cwd(), "middleware.ts"), "utf-8");
  const profileSrc = fs.readFileSync(path.join(process.cwd(), "app", "profile", "page.tsx"), "utf-8");

  assert.ok(navSrc.includes('href: "/profile"'), "AppNav must link to /profile");
  assert.ok(mwSrc.includes('"/profile"'), "middleware.ts must protect /profile");

  // Required UI states & features
  assert.ok(profileSrc.includes("profile-skeleton"), "Must render loading skeleton state");
  assert.ok(profileSrc.includes('role="alert"'), "Must render accessible error alert");
  assert.ok(profileSrc.includes('role="status"'), "Must render status/success/grace notice");
  assert.ok(profileSrc.includes("isSubmitting.current"), "Must guard against double submit");
  assert.ok(profileSrc.includes("deletion-grace-notice"), "Must render deletion grace notice");
  assert.ok(profileSrc.includes("/api/me/export"), "Must wire DPDP export");
  assert.ok(profileSrc.includes("/api/me/delete/cancel"), "Must wire deletion cancel");
});

test("GetAppPrompt - StrictMode safe initial mount guard and APK env var fallback", () => {
  const promptSrc = fs.readFileSync(path.join(process.cwd(), "components", "GetAppPrompt.tsx"), "utf-8");
  assert.ok(
    promptSrc.includes("pathname === initialMountPath.current"),
    "Must ignore StrictMode double-invoke on initial mount path"
  );
  assert.ok(
    promptSrc.includes("NEXT_PUBLIC_APK_URL"),
    "Must read NEXT_PUBLIC_APK_URL for Android APK link"
  );
});

test("Profile BFF routes - verify CSRF origin checks and cookie clearing on DELETE", () => {
  const meRoute = fs.readFileSync(path.join(process.cwd(), "app", "api", "me", "route.ts"), "utf-8");
  const expRoute = fs.readFileSync(path.join(process.cwd(), "app", "api", "me", "export", "route.ts"), "utf-8");
  const cancelRoute = fs.readFileSync(
    path.join(process.cwd(), "app", "api", "me", "delete", "cancel", "route.ts"),
    "utf-8"
  );

  assert.ok(meRoute.includes("verifyOrigin(request)"), "PATCH/DELETE /api/me must verify CSRF origin");
  assert.ok(meRoute.includes("clearAuthCookie"), "DELETE /api/me must clear auth cookie");
  assert.ok(expRoute.includes("verifyOrigin(request)"), "POST /api/me/export must verify CSRF origin");
  assert.ok(cancelRoute.includes("verifyOrigin(request)"), "POST /api/me/delete/cancel must verify CSRF origin");
});
