import test from "node:test";
import assert from "node:assert/strict";

// Helper simulating capabilities resolution logic
function resolveAuthCapabilities(fetchResult) {
  if (!fetchResult.ok) {
    // Failure fallback hides phone and google
    return { google: false, phone: false, email: true };
  }
  return {
    google: Boolean(fetchResult.data?.google),
    phone: Boolean(fetchResult.data?.phone),
    email: Boolean(fetchResult.data?.email ?? true),
  };
}

// Helper simulating whether UI components render the phone option
function shouldRenderPhoneOption(capabilities) {
  return Boolean(capabilities?.phone);
}

test("Web Capabilities - flag on renders phone option", () => {
  const caps = resolveAuthCapabilities({
    ok: true,
    data: { google: true, phone: true, email: true },
  });
  assert.equal(caps.phone, true);
  assert.equal(shouldRenderPhoneOption(caps), true);
});

test("Web Capabilities - flag off hides phone option", () => {
  const caps = resolveAuthCapabilities({
    ok: true,
    data: { google: true, phone: false, email: true },
  });
  assert.equal(caps.phone, false);
  assert.equal(shouldRenderPhoneOption(caps), false);
});

test("Web Capabilities - fetch failure safely hides phone option", () => {
  const caps = resolveAuthCapabilities({
    ok: false,
    status: 500,
    error: "Internal Server Error",
  });
  assert.equal(caps.phone, false);
  assert.equal(caps.google, false);
  assert.equal(caps.email, true);
  assert.equal(shouldRenderPhoneOption(caps), false);
});
