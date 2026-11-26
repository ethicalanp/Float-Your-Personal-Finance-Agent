import { NextResponse } from "next/server";
import { FloatApiClient } from "@float/api-client";

export async function GET() {
  try {
    const client = new FloatApiClient();
    const caps = await client.auth.getCapabilities();
    return NextResponse.json(caps);
  } catch {
    // Handle capabilities fetch failure by hiding phone and google
    return NextResponse.json({ google: false, phone: false, email: true, google_client_id: null });
  }
}
