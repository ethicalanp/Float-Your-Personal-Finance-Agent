import { FloatApiClient } from "@float/api-client";

/**
 * Robust fetch wrapper that performs safe retries strictly on idempotent GET requests,
 * using exponential backoff with jitter. Mutating requests are NEVER retried.
 */
async function resilientFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const method = (init?.method || "GET").toUpperCase();
  const isSafeGet = method === "GET";
  const maxRetries = isSafeGet ? 2 : 0;
  let attempt = 0;

  while (true) {
    try {
      const response = await fetch(input, init);
      // Retry safe GETs on transient 5xx server/gateway errors
      if (
        isSafeGet &&
        [502, 503, 504].includes(response.status) &&
        attempt < maxRetries
      ) {
        attempt++;
        const backoffMs = Math.min(100 * Math.pow(2, attempt) + Math.random() * 50, 1000);
        await new Promise((res) => setTimeout(res, backoffMs));
        continue;
      }
      return response;
    } catch (error) {
      if (isSafeGet && attempt < maxRetries) {
        attempt++;
        const backoffMs = Math.min(100 * Math.pow(2, attempt) + Math.random() * 50, 1000);
        await new Promise((res) => setTimeout(res, backoffMs));
        continue;
      }
      throw error;
    }
  }
}

/**
 * Returns a FloatApiClient instance configured for browser-side calls via the BFF proxy,
 * or direct backend calls when running server-side with an explicit token.
 */
export function getApiClient(token?: string): FloatApiClient {
  const isBrowser = typeof window !== "undefined";
  const baseUrl = isBrowser ? "/api/backend" : (process.env.PFA_API_URL || "http://127.0.0.1:8000");

  return new FloatApiClient({
    baseUrl,
    token,
    fetch: resilientFetch,
  });
}
