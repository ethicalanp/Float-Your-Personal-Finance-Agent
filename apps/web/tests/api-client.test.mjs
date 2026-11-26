import test from "node:test";
import assert from "node:assert/strict";
import { FloatApiClient } from "../../../packages/api-client/src/client.ts";
import { ApiError } from "../../../packages/api-client/src/errors.ts";

test("FloatApiClient - initialization and defaults", () => {
  const client = new FloatApiClient({ baseUrl: "http://localhost:8000" });
  assert.ok(client);
  assert.ok(client.auth);
  assert.ok(client.plan);
  assert.ok(client.protect);
  assert.ok(client.borrow);
  assert.ok(client.assistant);
});

test("FloatApiClient - token management", async () => {
  let capturedHeaders = null;
  const mockFetch = async (url, init) => {
    capturedHeaders = init.headers;
    return new Response(JSON.stringify({ status: "ok", consent: { terms_accepted: true, ai_data_processing_consent: true } }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const client = new FloatApiClient({ baseUrl: "http://localhost:8000", fetch: mockFetch });
  client.setToken("test-jwt-token-xyz");

  await client.auth.getConsent();
  assert.ok(capturedHeaders);
  assert.equal(capturedHeaders.get("Authorization"), "Bearer test-jwt-token-xyz");
});

test("FloatApiClient - ApiError parsing", async () => {
  const mockFetch = async () => {
    return new Response(
      JSON.stringify({
        error: {
          code: "VALIDATION_ERROR",
          message: "Request payload invalid",
          details: [{ loc: ["body", "email"], msg: "invalid email format" }],
          request_id: "req-12345",
        },
      }),
      { status: 422, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new FloatApiClient({ baseUrl: "http://localhost:8000", fetch: mockFetch });

  await assert.rejects(
    async () => {
      await client.auth.login({ email: "invalid", password: "123" });
    },
    (err) => {
      assert.ok(err instanceof ApiError);
      assert.equal(err.status, 422);
      assert.equal(err.code, "VALIDATION_ERROR");
      assert.equal(err.message, "Request payload invalid");
      assert.equal(err.requestId, "req-12345");
      assert.equal(err.details.length, 1);
      return true;
    }
  );
});

test("FloatApiClient - protect scam check method", async () => {
  const mockFetch = async (url, init) => {
    const body = JSON.parse(init.body);
    assert.equal(body.message, "Electricity bill unpaid");
    return new Response(
      JSON.stringify({
        status: "success",
        analysis: {
          is_scam: true,
          risk_tier: "HIGH",
          risk_score: 85,
          reasons: ["Urgent utility disconnection threat"],
          recommendations: ["Call 1930 immediately"],
          detected_patterns: ["electricity_bill"],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const client = new FloatApiClient({ baseUrl: "http://localhost:8000", fetch: mockFetch });
  const result = await client.protect.checkScam("Electricity bill unpaid");
  assert.equal(result.status, "success");
  assert.equal(result.analysis.is_scam, true);
  assert.equal(result.analysis.risk_tier, "HIGH");
  assert.ok(result.analysis.recommendations[0].includes("1930"));
});
