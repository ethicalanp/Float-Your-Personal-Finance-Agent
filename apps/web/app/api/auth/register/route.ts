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
    const result = await client.auth.register(body);

    const res = NextResponse.json({
      ok: true,
      user: {
        id: result.user_id,
        email: result.email,
        full_name: result.full_name,
      },
    }, { status: 201 });

    setAuthCookie(res, result.access_token, request);
    return res;
  } catch (err: any) {
    const status = err.status || 500;
    return NextResponse.json(
      { error: { code: err.code || "REGISTRATION_FAILED", message: err.message || "Registration failed", details: err.details } },
      { status }
    );
  }
}
