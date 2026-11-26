export interface ApiErrorDetail {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
  [key: string]: unknown;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetail[];
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: ApiErrorDetail[];
  readonly requestId: string;

  constructor(status: number, payload: Partial<ApiErrorPayload> | string) {
    if (typeof payload === "string") {
      super(payload);
      this.code = "UNKNOWN_ERROR";
      this.status = status;
      this.details = [];
      this.requestId = "";
      return;
    }

    const errorObj = payload.error;
    const msg = errorObj?.message || `API request failed with status ${status}`;
    super(msg);
    this.name = "ApiError";
    this.status = status;
    this.code = errorObj?.code || "HTTP_ERROR";
    this.details = errorObj?.details || [];
    this.requestId = errorObj?.request_id || "";
  }
}
