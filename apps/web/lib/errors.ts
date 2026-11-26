export interface AppErrorDetails {
  field?: string;
  message: string;
  code?: string;
}

export interface MappedError {
  code: string;
  title: string;
  message: string;
  status: number;
  requestId?: string;
  fieldErrors?: Record<string, string>;
  retryAfterSeconds?: number;
  returnTo?: string;
  canRetry: boolean;
}

/**
 * Standard mapper converting HTTP status codes, API error payloads,
 * and network/timeout failures into user-friendly UI error models.
 */
export function mapHttpError(
  status: number,
  payload?: any,
  options?: { currentPath?: string; requestId?: string }
): MappedError {
  const reqId =
    payload?.error?.request_id ||
    payload?.request_id ||
    options?.requestId ||
    "";

  // 1. 401 Unauthorized -> Re-login and retain return path
  if (status === 401) {
    const returnPath = options?.currentPath || "/home";
    return {
      code: payload?.error?.code || "UNAUTHORIZED",
      status: 401,
      title: "Session Expired",
      message: "Your session has expired. Please log in again to continue.",
      requestId: reqId,
      returnTo: `/login?return_to=${encodeURIComponent(returnPath)}`,
      canRetry: false,
    };
  }

  // 2. 403 Forbidden
  if (status === 403) {
    return {
      code: payload?.error?.code || "FORBIDDEN",
      status: 403,
      title: "Access Denied",
      message: "You do not have permission to access or modify this resource.",
      requestId: reqId,
      canRetry: false,
    };
  }

  // 3. 404 Not Found
  if (status === 404) {
    return {
      code: payload?.error?.code || "NOT_FOUND",
      status: 404,
      title: "Resource Not Found",
      message: "The requested resource could not be found or has been moved.",
      requestId: reqId,
      canRetry: false,
    };
  }

  // 4. 413 Payload Too Large
  if (status === 413) {
    return {
      code: payload?.error?.code || "PAYLOAD_TOO_LARGE",
      status: 413,
      title: "File Too Large",
      message:
        payload?.error?.message ||
        "The uploaded file exceeds the maximum allowed limit of 10 MB.",
      requestId: reqId,
      canRetry: false,
    };
  }

  // 5. 415 Unsupported Media Type
  if (status === 415) {
    return {
      code: payload?.error?.code || "UNSUPPORTED_MEDIA_TYPE",
      status: 415,
      title: "Unsupported File Format",
      message:
        payload?.error?.message ||
        "Only CSV, PDF, or XLSX statement files are supported.",
      requestId: reqId,
      canRetry: false,
    };
  }

  // 6. 422 Unprocessable Entity / Validation Error
  if (status === 422) {
    const fieldErrors: Record<string, string> = {};
    const rawDetails = payload?.error?.details || payload?.detail;

    if (Array.isArray(rawDetails)) {
      for (const item of rawDetails) {
        const fieldName = Array.isArray(item.loc)
          ? item.loc[item.loc.length - 1]
          : item.field || "general";
        fieldErrors[String(fieldName)] = item.msg || item.message || "Invalid value";
      }
    }

    return {
      code: payload?.error?.code || "VALIDATION_ERROR",
      status: 422,
      title: "Input Validation Error",
      message:
        payload?.error?.message ||
        "Please check the highlighted fields and correct the errors.",
      requestId: reqId,
      fieldErrors,
      canRetry: false,
    };
  }

  // 7. 429 Rate Limit Exceeded
  if (status === 429) {
    const retryAfter =
      Number(payload?.retry_after || payload?.error?.details?.[0]?.retry_after) ||
      60;

    return {
      code: payload?.error?.code || "RATE_LIMITED",
      status: 429,
      title: "Too Many Requests",
      message: `You have made too many requests. Please wait ${retryAfter} seconds before trying again.`,
      requestId: reqId,
      retryAfterSeconds: retryAfter,
      canRetry: true,
    };
  }

  // 8. 503 Service Unavailable / Phone Login Disabled
  if (status === 503) {
    const isPhoneDisabled = payload?.error?.code === "phone_login_disabled";
    return {
      code: payload?.error?.code || "SERVICE_UNAVAILABLE",
      status: 503,
      title: isPhoneDisabled ? "Phone Login Unavailable" : "Service Unavailable",
      message:
        payload?.error?.message ||
        "The service is temporarily unavailable. Please try again shortly.",
      requestId: reqId,
      canRetry: true,
    };
  }

  // 9. 5xx Server Errors
  if (status >= 500) {
    return {
      code: payload?.error?.code || "SERVER_ERROR",
      status,
      title: "Internal Server Error",
      message:
        "Something went wrong on our end. Our engineering team has been alerted.",
      requestId: reqId,
      canRetry: true,
    };
  }

  // Default fallback
  return {
    code: payload?.error?.code || "UNKNOWN_ERROR",
    status,
    title: "Request Failed",
    message: payload?.error?.message || "An unexpected error occurred.",
    requestId: reqId,
    canRetry: true,
  };
}

/**
 * Maps client-side network or fetch exceptions (offline, DNS, timeout).
 */
export function mapNetworkError(error: any): MappedError {
  const isTimeout =
    error.name === "AbortError" ||
    error.name === "TimeoutError" ||
    /timeout/i.test(error.message || "");

  if (isTimeout) {
    return {
      code: "TIMEOUT",
      status: 408,
      title: "Request Timed Out",
      message: "The server took too long to respond. Please check your connection and try again.",
      canRetry: true,
    };
  }

  return {
    code: "NETWORK_ERROR",
    status: 0,
    title: "Connection Failed",
    message: "Could not connect to Float server. Please check your internet connection.",
    canRetry: true,
  };
}
