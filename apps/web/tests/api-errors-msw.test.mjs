import test from "node:test";
import assert from "node:assert/strict";
import { mapHttpError, mapNetworkError } from "../lib/errors.ts";

test("Error Mapper - 401 Unauthorized maps to re-login with return_to path", () => {
  const err = mapHttpError(401, { error: { code: "UNAUTHORIZED", request_id: "req_auth_001" } }, { currentPath: "/settings" });
  assert.equal(err.status, 401);
  assert.equal(err.code, "UNAUTHORIZED");
  assert.equal(err.requestId, "req_auth_001");
  assert.equal(err.returnTo, "/login?return_to=%2Fsettings");
  assert.equal(err.canRetry, false);
});

test("Error Mapper - 403 Forbidden maps to access denied with request_id", () => {
  const err = mapHttpError(403, { error: { code: "FORBIDDEN", request_id: "req_csrf_002" } });
  assert.equal(err.status, 403);
  assert.equal(err.code, "FORBIDDEN");
  assert.equal(err.title, "Access Denied");
  assert.equal(err.requestId, "req_csrf_002");
  assert.equal(err.canRetry, false);
});

test("Error Mapper - 404 Not Found maps to resource not found", () => {
  const err = mapHttpError(404, { error: { code: "NOT_FOUND", request_id: "req_nf_003" } });
  assert.equal(err.status, 404);
  assert.equal(err.code, "NOT_FOUND");
  assert.equal(err.title, "Resource Not Found");
  assert.equal(err.requestId, "req_nf_003");
});

test("Error Mapper - 413 Payload Too Large maps to 10MB limit message", () => {
  const err = mapHttpError(413, { error: { code: "PAYLOAD_TOO_LARGE", message: "File exceeds 10 MB limit", request_id: "req_413" } });
  assert.equal(err.status, 413);
  assert.equal(err.code, "PAYLOAD_TOO_LARGE");
  assert.equal(err.title, "File Too Large");
  assert.equal(err.requestId, "req_413");
});

test("Error Mapper - 415 Unsupported Media Type maps to format explanation", () => {
  const err = mapHttpError(415, { error: { code: "UNSUPPORTED_MEDIA_TYPE", message: "Invalid binary executable", request_id: "req_415" } });
  assert.equal(err.status, 415);
  assert.equal(err.code, "UNSUPPORTED_MEDIA_TYPE");
  assert.equal(err.title, "Unsupported File Format");
});

test("Error Mapper - 422 Unprocessable Entity maps field errors", () => {
  const err = mapHttpError(422, {
    error: {
      code: "VALIDATION_ERROR",
      details: [
        { loc: ["body", "phone_number"], msg: "Invalid E.164 phone format" },
        { loc: ["body", "amount"], msg: "Amount must be positive" },
      ],
      request_id: "req_val_004",
    },
  });
  assert.equal(err.status, 422);
  assert.equal(err.code, "VALIDATION_ERROR");
  assert.equal(err.fieldErrors?.["phone_number"], "Invalid E.164 phone format");
  assert.equal(err.fieldErrors?.["amount"], "Amount must be positive");
  assert.equal(err.requestId, "req_val_004");
});

test("Error Mapper - 429 Rate Limited extracts Retry-After countdown", () => {
  const err = mapHttpError(429, {
    error: {
      code: "RATE_LIMITED",
      request_id: "req_rate_005",
      details: [{ retry_after: 45 }],
    },
  });
  assert.equal(err.status, 429);
  assert.equal(err.code, "RATE_LIMITED");
  assert.equal(err.retryAfterSeconds, 45);
  assert.match(err.message, /45 seconds/);
  assert.equal(err.canRetry, true);
});

test("Error Mapper - 503 Phone Login Disabled produces specific friendly message", () => {
  const err = mapHttpError(503, {
    error: {
      code: "phone_login_disabled",
      message: "Phone authentication is currently unavailable.",
      request_id: "req_phone_503",
    },
  });
  assert.equal(err.status, 503);
  assert.equal(err.code, "phone_login_disabled");
  assert.equal(err.title, "Phone Login Unavailable");
  assert.equal(err.requestId, "req_phone_503");
  assert.equal(err.canRetry, true);
});

test("Error Mapper - 500 Server Error shows friendly message and request_id", () => {
  const err = mapHttpError(500, { error: { code: "INTERNAL_ERROR", request_id: "req_500_xyz" } });
  assert.equal(err.status, 500);
  assert.equal(err.title, "Internal Server Error");
  assert.equal(err.requestId, "req_500_xyz");
  assert.equal(err.canRetry, true);
});

test("Error Mapper - Network Down and Timeout errors", () => {
  const timeoutErr = mapNetworkError(new Error("Request timeout after 5000ms"));
  assert.equal(timeoutErr.code, "TIMEOUT");
  assert.equal(timeoutErr.status, 408);
  assert.equal(timeoutErr.canRetry, true);

  const netErr = mapNetworkError(new TypeError("Failed to fetch"));
  assert.equal(netErr.code, "NETWORK_ERROR");
  assert.equal(netErr.status, 0);
  assert.equal(netErr.canRetry, true);
});
