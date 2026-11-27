import { NextRequest, NextResponse } from "next/server";
import { getTokenFromCookies, verifyOrigin } from "@/lib/auth-cookie";
import { validateStatementAllowlist, MAX_UPLOAD_BYTES } from "@/lib/upload-validator";

const BACKEND_BASE_URL = (
  process.env.PFA_API_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const PUBLIC_BACKEND_ROUTES = new Set([
  "auth/capabilities",
  "auth/login",
  "auth/register",
  "auth/phone/request-otp",
  "auth/phone/verify-otp",
  "auth/password-reset/request",
  "auth/password-reset/confirm",
  "health",
  "health/ready",
  "health/live",
]);

async function handleProxy(request: NextRequest, { params }: { params: { path: string[] } }) {
  const method = request.method;
  const isMutating = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const rawSubPath = (params?.path || []).join("/");
  const subPath = rawSubPath.replace(/^api\/v1\//, "");

  // 1. Strict CSRF check on all mutating routes
  if (isMutating && !verifyOrigin(request)) {
    return NextResponse.json(
      { error: { code: "FORBIDDEN", message: "Origin validation failed" } },
      { status: 403 }
    );
  }

  // 2. Defense-in-depth: Verify session for all non-public routes
  const token = getTokenFromCookies();
  const isPublic = PUBLIC_BACKEND_ROUTES.has(subPath);

  if (!isPublic && !token) {
    return NextResponse.json(
      { error: { code: "UNAUTHORIZED", message: "Authentication required" } },
      { status: 401 }
    );
  }

  // 3. Upload protection: 10MB streaming limit and magic-byte checks
  const isUploadRoute = subPath === "plan/upload-statement";
  const contentLengthHeader = request.headers.get("content-length");

  if (isUploadRoute && contentLengthHeader) {
    const contentLength = parseInt(contentLengthHeader, 10);
    if (!isNaN(contentLength) && contentLength > MAX_UPLOAD_BYTES) {
      return NextResponse.json(
        {
          error: {
            code: "PAYLOAD_TOO_LARGE",
            message: "File exceeds maximum size limit of 10 MB",
            request_id: request.headers.get("x-request-id") || "",
          },
        },
        { status: 413 }
      );
    }
  }

  let bodyBuffer: Uint8Array | undefined = undefined;

  if (isMutating && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;
    let isFirstChunk = true;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        if (value) {
          totalBytes += value.length;
          if (totalBytes > MAX_UPLOAD_BYTES && isUploadRoute) {
            reader.cancel();
            return NextResponse.json(
              {
                error: {
                  code: "PAYLOAD_TOO_LARGE",
                  message: "File exceeds maximum size limit of 10 MB",
                  request_id: request.headers.get("x-request-id") || "",
                },
              },
              { status: 413 }
            );
          }

          if (isFirstChunk && isUploadRoute) {
            isFirstChunk = false;
            const validation = validateStatementAllowlist(value);
            if (!validation.valid) {
              reader.cancel();
              return NextResponse.json(
                {
                  error: {
                    code: "UNSUPPORTED_MEDIA_TYPE",
                    message: validation.error || "Unsupported media type. Only CSV, PDF, and XLSX statements are supported.",
                    request_id: request.headers.get("x-request-id") || "",
                  },
                },
                { status: 415 }
              );
            }
          }

          chunks.push(value);
        }
      }

      // Concatenate received chunks
      const merged = new Uint8Array(totalBytes);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }
      bodyBuffer = merged;
    } catch (streamErr: any) {
      return NextResponse.json(
        {
          error: {
            code: "STREAM_READ_ERROR",
            message: "Failed to read request body stream",
            details: [{ error: streamErr.message }],
          },
        },
        { status: 400 }
      );
    }
  }

  // 4. Forward to backend
  const search = request.nextUrl.search;
  const targetUrl = `${BACKEND_BASE_URL}/api/v1/${subPath}${search}`;

  const headers = new Headers();
  const incomingContentType = request.headers.get("content-type");
  if (incomingContentType) {
    headers.set("Content-Type", incomingContentType);
  }

  const incomingReqId = request.headers.get("x-request-id");
  if (incomingReqId) {
    headers.set("X-Request-ID", incomingReqId);
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  try {
    const backendRes = await fetch(targetUrl, {
      method,
      headers,
      body: bodyBuffer as any,
      signal: request.signal,
    });

    const resContentType = backendRes.headers.get("content-type") || "";
    if (resContentType.includes("text/event-stream") && backendRes.body) {
      return new Response(backendRes.body, {
        status: backendRes.status,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
        },
      });
    }

    if (resContentType.includes("application/json")) {
      const data = await backendRes.json();
      return NextResponse.json(data, { status: backendRes.status });
    }

    const text = await backendRes.text();
    return new NextResponse(text, {
      status: backendRes.status,
      headers: { "Content-Type": resContentType || "text/plain" },
    });
  } catch (err: any) {
    return NextResponse.json(
      {
        error: {
          code: "BACKEND_UNAVAILABLE",
          message: "Could not connect to backend service.",
          details: [{ error: err.message }],
        },
      },
      { status: 503 }
    );
  }
}

export const GET = handleProxy;
export const POST = handleProxy;
export const PUT = handleProxy;
export const PATCH = handleProxy;
export const DELETE = handleProxy;
