import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { setAuthCookie, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }
  try {
    const body = await request.json();
    const client = new FloatApiClient();
    const result = await client.auth.verifyPhoneOtp(body);
    const res = NextResponse.json({
      ok: true,
      user: {
        id: result.user_id,
        email: result.email,
        full_name: result.full_name,
      },
    });
    setAuthCookie(res, result.access_token, request);
    return res;
  } catch (err: any) {
    return NextResponse.json(
      { error: { code: err.code || "OTP_VERIFY_FAILED", message: err.message || "Invalid OTP" } },
      { status: err.status || 400 }
    );
  }
}
