import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies } from "@/lib/auth-cookie";

export async function GET() {
  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Not authenticated" } }, { status: 401 });
  }

  try {
    const client = new FloatApiClient({ token });
    const data = await client.auth.getMethods();
    return NextResponse.json(data);
  } catch (err: any) {
    const status = err.status || 500;
    return NextResponse.json(
      { error: { code: err.code || "METHODS_FETCH_FAILED", message: err.message || "Failed to load methods" } },
      { status }
    );
  }
}
