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
    const result = await client.auth.requestPasswordReset({ email: body.email });
    return NextResponse.json({ ok: true, message: result.message });
  } catch (err: any) {
    const status = err.status || 500;
    return NextResponse.json(
      { error: { code: err.code || "REQUEST_FAILED", message: err.message || "Failed to request password reset" } },
      { status }
    );
  }
}
