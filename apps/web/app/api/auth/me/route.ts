import { NextResponse } from "next/server";
import { getTokenFromCookies } from "@/lib/auth-cookie";

const API_BASE = process.env.PFA_API_URL || "http://127.0.0.1:8000";

export async function GET() {
  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const client = new FloatApiClient({ token });
    const profile: any = await client.auth.getProfile();
    return NextResponse.json({
      ok: true,
      user_id: profile.user_id ?? profile.id,
      consent: profile.consent ?? {
        terms_accepted: Boolean(profile.terms_accepted),
        privacy_accepted: Boolean(profile.privacy_accepted),
        ai_data_processing_consent: Boolean(profile.ai_data_processing_consent),
      },
    });
  } catch (err: any) {
    const status = err.status || 401;
    return NextResponse.json({ ok: false, error: err.message || "Session invalid or expired" }, { status });
  }
}
