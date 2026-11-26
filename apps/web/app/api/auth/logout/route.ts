import { NextResponse } from "next/server";
import { clearAuthCookie, verifyOrigin } from "@/lib/auth-cookie";

export async function POST(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const res = NextResponse.json({ ok: true, message: "Logged out successfully" });
  clearAuthCookie(res);
  return res;
}
