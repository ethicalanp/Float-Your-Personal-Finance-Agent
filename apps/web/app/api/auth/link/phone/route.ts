import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Not authenticated" } }, { status: 401 });
  }

  try {
    const body = await request.json();
    const client = new FloatApiClient({ token });
    const result = await client.auth.linkPhone({ phone_number: body.phone_number });
    return NextResponse.json({ ok: true, message: result.message });
  } catch (err: any) {
    const status = err.status || 400;
    return NextResponse.json(
      { error: { code: err.code || "LINK_PHONE_FAILED", message: err.message || "Failed to send link OTP" } },
      { status }
    );
  }
}
