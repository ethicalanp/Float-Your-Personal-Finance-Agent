import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { setAuthCookie, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  const reqId = request.headers.get("x-request-id") || crypto.randomUUID();

  if (!verifyOrigin(request)) {
    return NextResponse.json(
      { error: { code: "FORBIDDEN", message: "Origin check failed", request_id: reqId } },
      { status: 403 }
    );
  }

  try {
    const body = await request.json();
    const client = new FloatApiClient();
    const result = await client.auth.login(body);

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
    const status = err.status || 401;
    const resolvedReqId = err.details?.request_id || err.request_id || reqId;
    return NextResponse.json(
      {
        error: {
          code: err.code || "LOGIN_FAILED",
          message: err.message || "Invalid credentials",
          details: err.details,
          request_id: resolvedReqId,
        },
      },
      { status }
    );
  }
}
