import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }
  try {
    const body = await request.json();
    const client = new FloatApiClient();
    const res = await client.auth.requestPhoneOtp(body);
    return NextResponse.json(res);
  } catch (err: any) {
    return NextResponse.json(
      { error: { code: err.code || "OTP_REQUEST_FAILED", message: err.message || "Failed to request OTP" } },
      { status: err.status || 500 }
    );
  }
}
