import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE_NAME, clearAuthCookie, verifyOrigin } from "@/lib/auth-cookie";

const API_BASE = process.env.PFA_API_URL || "http://127.0.0.1:8000";

async function proxyMe(method: string, request?: Request) {
  const token = cookies().get(AUTH_COOKIE_NAME)?.value;
  if (!token) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Not authenticated" } }, { status: 401 });
  }

  let body: string | undefined;
  if (request && method === "PATCH") {
    body = await request.text();
  }

  const res = await fetch(`${API_BASE}/api/v1/me`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body } : {}),
    cache: "no-store",
  });

  const data = await res.json().catch(() => null);
  const response = NextResponse.json(data, { status: res.status });
  if (method === "DELETE" && res.ok) {
    clearAuthCookie(response, request);
  }
  return response;
}

export async function GET() {
  return proxyMe("GET");
}

export async function PATCH(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }
  return proxyMe("PATCH", request);
}

export async function DELETE(request: Request) {
  if (!verifyOrigin(request)) {
    return NextResponse.json({ error: { code: "FORBIDDEN", message: "Origin check failed" } }, { status: 403 });
  }
  return proxyMe("DELETE", request);
}
