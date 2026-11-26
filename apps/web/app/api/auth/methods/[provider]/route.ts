import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";
import { getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";

export async function DELETE(
  request: Request,
  { params }: { params: { provider: string } }
) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }

  const token = getTokenFromCookies();
  if (!token) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Not authenticated" } }, { status: 401 });
  }

  try {
    const client = new FloatApiClient({ token });
    const result = await client.auth.unlinkMethod(params.provider);
    return NextResponse.json({ ok: true, message: result.message });
  } catch (err: any) {
    const status = err.status || 400;
    return NextResponse.json(
      { error: { code: err.code || "UNLINK_FAILED", message: err.message || "Failed to unlink method" } },
      { status }
    );
  }
}
