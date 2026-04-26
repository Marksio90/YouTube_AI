interface ApiError {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const CSRF_HEADER_NAME = "X-CSRF-Token";

interface RequestOptions extends RequestInit {
  skipAuthRefresh?: boolean;
  hasRetried?: boolean;
}

class ApiClient {
  private baseUrl: string;
  private refreshPromise: Promise<void> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getCsrfTokenFromCookie(): string | null {
    if (typeof document === "undefined") return null;
    const tokenEntry = document.cookie
      .split(";")
      .map((entry) => entry.trim())
      .find((entry) => entry.startsWith("csrf_token="));
    if (!tokenEntry) return null;
    return decodeURIComponent(tokenEntry.slice("csrf_token=".length));
  }

  private isMutatingMethod(method: string | undefined): boolean {
    return ["POST", "PATCH", "DELETE"].includes((method ?? "GET").toUpperCase());
  }

  private async ensureCsrfToken(): Promise<string> {
    const cookieToken = this.getCsrfTokenFromCookie();
    if (cookieToken) return cookieToken;

    const response = await fetch(`${this.baseUrl}/auth/csrf`, {
      method: "GET",
      credentials: "include",
    });
    if (!response.ok) {
      throw await this.buildApiError(response);
    }

    const payload = (await response.json()) as { csrf_token?: string };
    if (!payload.csrf_token) {
      throw new ApiClientError(500, {
        code: "CSRF_TOKEN_MISSING",
        message: "Could not initialize CSRF token",
        details: null,
      });
    }
    return payload.csrf_token;
  }

  private async refreshAuthSession(): Promise<void> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.request<void>("/auth/refresh", {
        method: "POST",
        skipAuthRefresh: true,
      }).finally(() => {
        this.refreshPromise = null;
      });
    }

    return this.refreshPromise;
  }

  private async request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string> | undefined),
    };

    if (this.isMutatingMethod(init.method)) {
      headers[CSRF_HEADER_NAME] = await this.ensureCsrfToken();
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });

    if (response.status === 401 && !init.skipAuthRefresh && !init.hasRetried) {
      try {
        await this.refreshAuthSession();
      } catch {
        throw await this.buildApiError(response);
      }

      return this.request<T>(path, { ...init, hasRetried: true });
    }

    if (!response.ok) {
      throw await this.buildApiError(response);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  private async buildApiError(response: Response) {
    let error: ApiError = { code: "HTTP_ERROR", message: response.statusText, details: null };
    try {
      error = await response.json();
    } catch {
      // noop - keep default API error object
    }
    return new ApiClientError(response.status, error);
  }

  get<T>(path: string, options: Omit<RequestOptions, "method"> = {}) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) {
    const requestInit: RequestOptions = {
      ...options,
      method: "POST",
    };

    if (typeof body !== "undefined") {
      requestInit.body = JSON.stringify(body);
    }

    return this.request<T>(path, requestInit);
  }

  patch<T>(path: string, body: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) {
    return this.request<T>(path, { ...options, method: "PATCH", body: JSON.stringify(body) });
  }

  delete<T>(path: string, options: Omit<RequestOptions, "method"> = {}) {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }
}

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly error: ApiError
  ) {
    super(error.message);
    this.name = "ApiClientError";
  }
}

export const apiClient = new ApiClient(API_BASE);
