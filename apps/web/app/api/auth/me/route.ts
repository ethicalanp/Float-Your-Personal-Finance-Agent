import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies } from "@/lib/auth-cookie";

export async function GET() {
  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const client = new FloatApiClient({ token });
    const consent = await client.auth.getConsent();
    return NextResponse.json({
      ok: true,
      user_id: consent.user_id,
      consent: consent.consent,
    });
  } catch (err: any) {
    const status = err.status || 401;
    return NextResponse.json({ ok: false, error: err.message || "Session invalid or expired" }, { status });
  }
}
