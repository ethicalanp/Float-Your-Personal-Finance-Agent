import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { clearAuthCookie, getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const token = getTokenFromCookies();
  if (token) {
    try {
      const client = new FloatApiClient({ token });
      await client.auth.logoutAll();
    } catch {
      // Ignore backend logout errors to ensure client cookie is always cleared
    }
  }

  const res = NextResponse.json({ ok: true, message: "Logged out from all sessions" });
  clearAuthCookie(res);
  return res;
}
