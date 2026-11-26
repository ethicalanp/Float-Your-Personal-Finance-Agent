import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { setAuthCookie, getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

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
    const result = await client.auth.reauth(body);

    const res = NextResponse.json({
      ok: true,
      message: "Authentication confirmed",
      user: {
        id: result.user_id,
        email: result.email,
        full_name: result.full_name,
      },
    });

    setAuthCookie(res, result.access_token, request);
    return res;
  } catch (err: any) {
    const status = err.status || 401;
    return NextResponse.json(
      { error: { code: err.code || "REAUTH_FAILED", message: err.message || "Re-authentication failed" } },
      { status }
    );
  }
}
