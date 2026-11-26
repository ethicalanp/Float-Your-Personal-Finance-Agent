export const AUTH_COOKIE_NAME = "float_token";

export interface CookieResponse {
  cookies: {
    set(name: string, value: string, options?: any): void;
  };
}

export function isSecureConnection(request?: Request): boolean {
  // Always true when NODE_ENV=production
  if (process.env.NODE_ENV === "production") {
    return true;
  }

  // Explicit override if configured in non-production
  if (process.env.COOKIE_SECURE === "true") return true;
  if (process.env.COOKIE_SECURE === "false") return false;

  // In non-production: relaxed only for http://localhost.
  // Don't trust x-forwarded-proto unless explicitly configured.
  const trustForwarded =
    process.env.TRUST_FORWARDED_PROTO === "true" || process.env.TRUST_PROXY === "true";

  let isHttps = false;
  let hostname = "localhost";

  if (request) {
    if (trustForwarded) {
      const proto = request.headers.get("x-forwarded-proto");
      if (proto === "https") isHttps = true;
    }

    try {
      const url = new URL(request.url);
      if (url.protocol === "https:") isHttps = true;
      hostname = url.hostname;
    } catch {
      const host = request.headers.get("host") || "";
      hostname = host.split(":")[0];
    }
  }

  if (isHttps) return true;

  // Relaxed only for http://localhost (and 127.0.0.1) in non-production
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return false;
  }

  return true;
}

export function getCookieOptions(request?: Request) {
  return {
    httpOnly: true,
    secure: isSecureConnection(request),
    sameSite: "lax" as const,
    path: "/",
    maxAge: 60 * 60 * 24 * 7, // 7 days
  };
}

export const COOKIE_OPTIONS = getCookieOptions();

/**
 * Validate that mutating requests originate from the same host to prevent CSRF.
 * Strict CSRF: Returns false if neither Origin nor Referer is provided, or if the host mismatches.
 * In production: The Origin must match the configured site origin exactly (or exact host).
 * Outside production: Allows matching ports on loopback aliases (localhost and 127.0.0.1).
 */
export function verifyOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("x-forwarded-host") || request.headers.get("host");

  if (!host) {
    return false;
  }

  const isProd = process.env.NODE_ENV === "production";
  const configuredOrigin = process.env.SITE_ORIGIN || process.env.NEXT_PUBLIC_APP_URL;

  const isLoopback = (h: string) => {
    const hostname = h.split(":")[0];
    return hostname === "localhost" || hostname === "127.0.0.1";
  };

  const getPort = (h: string, defaultPort: string = "80") => {
    return h.includes(":") ? h.split(":")[1] : defaultPort;
  };

  const checkCandidate = (candidateUrlStr: string) => {
    try {
      const candidateUrl = new URL(candidateUrlStr);
      const candidateHost = candidateUrl.host;

      // In production: Origin must match configured site origin exactly if set, or exact host
      if (isProd) {
        if (configuredOrigin) {
          const expectedUrl = new URL(configuredOrigin);
          return candidateUrl.origin === expectedUrl.origin;
        }
        return candidateHost === host;
      }

      // Outside production:
      if (candidateHost === host) {
        return true;
      }
      // Loopback alias applies only outside production
      if (isLoopback(candidateHost) && isLoopback(host)) {
        const candidatePort = candidateUrl.port || (candidateUrl.protocol === "https:" ? "443" : "80");
        const hostPort = getPort(host, candidateUrl.protocol === "https:" ? "443" : "80");
        return candidatePort === hostPort;
      }
      return false;
    } catch {
      return false;
    }
  };

  if (origin) {
    return checkCandidate(origin);
  }

  const referer = request.headers.get("referer");
  if (referer) {
    return checkCandidate(referer);
  }

  return false;
}

export function getTokenFromCookies(): string | undefined {
  try {
    const req = typeof require !== "undefined" ? require : null;
    if (!req) return undefined;
    const cookieStore = req("next/headers").cookies();
    return cookieStore.get(AUTH_COOKIE_NAME)?.value;
  } catch {
    return undefined;
  }
}

export function setAuthCookie(response: CookieResponse, token: string, request?: Request): void {
  response.cookies.set(AUTH_COOKIE_NAME, token, getCookieOptions(request));
}

export function clearAuthCookie(response: CookieResponse, request?: Request): void {
  response.cookies.set(AUTH_COOKIE_NAME, "", {
    ...getCookieOptions(request),
    maxAge: 0,
  });
}
