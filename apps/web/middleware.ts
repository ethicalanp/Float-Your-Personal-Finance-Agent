import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE_NAME } from "./lib/auth-cookie";

const PROTECTED_PREFIXES = [
  "/home",
  "/protect",
  "/borrow",
  "/chat",
  "/settings",
  "/consent",
];

const isProd = process.env.NODE_ENV === "production";

// Production CSP strictly eliminates 'unsafe-eval' while dev permits it for Fast Refresh/Webpack HMR
const SCRIPT_SRC = isProd
  ? "script-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/client"
  : "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com/gsi/client";

const CSP_HEADER = [
  "default-src 'self'",
  SCRIPT_SRC,
  "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style https://fonts.googleapis.com",
  "img-src 'self' data: https:",
  "font-src 'self' data: https://fonts.gstatic.com",
  "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 https://accounts.google.com/gsi/ https:",
  "frame-src 'self' https://accounts.google.com/gsi/",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "base-uri 'self'",
].join("; ");

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;

  // Check if route is protected
  const isProtected = PROTECTED_PREFIXES.some((prefix) =>
    pathname === prefix || pathname.startsWith(`${prefix}/`)
  );

  if (isProtected && !token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("return_to", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // If already logged in and visiting login/signup, redirect to home
  if ((pathname === "/login" || pathname === "/signup") && token) {
    return NextResponse.redirect(new URL("/home", request.url));
  }

  const response = NextResponse.next();

  // Apply Security Headers (CSP, Frame Options, Mime sniffing guard, HSTS)
  response.headers.set("Content-Security-Policy", CSP_HEADER);
  response.headers.set("Cross-Origin-Opener-Policy", "same-origin-allow-popups");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  response.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload");

  // Private routes: Cache-Control no-store prevents sensitive financial caching and back-button leakage
  if (isProtected) {
    response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
    response.headers.set("Pragma", "no-cache");
    response.headers.set("Expires", "0");
  }

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - images, fonts and public assets
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
