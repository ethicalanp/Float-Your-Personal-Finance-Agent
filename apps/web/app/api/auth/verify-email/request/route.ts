import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const token = getTokenFromCookies();
  try {
    const body = await request.json().catch(() => ({}));
    const client = new FloatApiClient({ token });
    const result = await client.auth.requestEmailVerification({ email: body.email });
    return NextResponse.json({ ok: true, message: result.message });
  } catch (err: any) {
    const status = err.status || 500;
    return NextResponse.json(
      { error: { code: err.code || "REQUEST_FAILED", message: err.message || "Failed to send verification email" } },
      { status }
    );
  }
}
