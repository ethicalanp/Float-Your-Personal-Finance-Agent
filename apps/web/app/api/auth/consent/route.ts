import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Authentication required" } }, { status: 401 });
  }

  try {
    const body = await request.json();
    const client = new FloatApiClient({ token });
    const result = await client.auth.updateConsent(body);
    return NextResponse.json({ ok: true, consent: result.consent });
  } catch (err: any) {
    const status = err.status || 500;
    return NextResponse.json(
      { error: { code: err.code || "CONSENT_UPDATE_FAILED", message: err.message || "Failed to update consent" } },
      { status }
    );
  }
}
