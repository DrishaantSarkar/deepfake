import {
  AnalysisStats,
  AnalysisListResponse,
  AnalysisDetailResponse,
  EvidenceDetailResponse,
  CapabilitiesResponse,
  HealthResponse,
  ApiError,
  TestSample,
  TestSamplesResponse,
} from "../types/api";

export class TrustlensApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code: string = "api_error", status: number = 500) {
    super(message);
    this.name = "TrustlensApiError";
    this.code = code;
    this.status = status;
  }
}

const SESSION_STORAGE_KEY = "trustlens_session_token";
const SESSION_REQUIRED_EVENT = "trustlens:session-required";

function sessionToken(): string | null {
  return typeof window === "undefined" ? null : window.sessionStorage.getItem(SESSION_STORAGE_KEY);
}

function handleUnauthorized(endpoint: string): void {
  if (endpoint === "/api/admin/verify" || typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  window.dispatchEvent(new Event(SESSION_REQUIRED_EVENT));
}

function requestHeaders(initial?: HeadersInit): Headers {
  const headers = new Headers(initial || {});
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const token = sessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = requestHeaders(options.headers);

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) handleUnauthorized(endpoint);
    let errorMessage = `Request failed with status ${response.status}`;
    let errorCode = "http_error";

    try {
      const errorBody = (await response.json()) as { error?: ApiError };
      if (errorBody?.error?.message) {
        errorMessage = errorBody.error.message;
      }
      if (errorBody?.error?.code) {
        errorCode = errorBody.error.code;
      }
    } catch {
      // fallback to generic message
    }

    throw new TrustlensApiError(errorMessage, errorCode, response.status);
  }

  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}

async function requestBlob(endpoint: string): Promise<Blob> {
  const response = await fetch(endpoint, { headers: requestHeaders() });
  if (!response.ok) {
    if (response.status === 401) handleUnauthorized(endpoint);
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { error?: ApiError };
      if (body.error?.message) message = body.error.message;
    } catch {
      // Keep the status-based message when the response isn't JSON.
    }
    throw new TrustlensApiError(message, "http_error", response.status);
  }
  return response.blob();
}

export const api = {
  async login(key: string): Promise<string> {
    const response = await fetch("/api/admin/verify", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    if (!response.ok) {
      let message = "The access key was rejected.";
      try {
        const body = (await response.json()) as { error?: ApiError };
        if (body.error?.message) message = body.error.message;
      } catch {
        // Keep the default message when the response isn't JSON.
      }
      throw new TrustlensApiError(message, "login_failed", response.status);
    }
    const body = (await response.json()) as { token?: string };
    if (!body.token) throw new TrustlensApiError("The server did not return a session.", "login_failed");
    if (typeof window !== "undefined") window.sessionStorage.setItem(SESSION_STORAGE_KEY, body.token);
    return body.token;
  },

  logout(): void {
    if (typeof window !== "undefined") window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  },

  hasSession(): boolean {
    return Boolean(sessionToken());
  },

  onSessionRequired(listener: () => void): () => void {
    if (typeof window === "undefined") return () => undefined;
    window.addEventListener(SESSION_REQUIRED_EVENT, listener);
    return () => window.removeEventListener(SESSION_REQUIRED_EVENT, listener);
  },

  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/api/health");
  },

  async getCapabilities(): Promise<CapabilitiesResponse> {
    return request<CapabilitiesResponse>("/api/capabilities");
  },

  async getStats(): Promise<AnalysisStats> {
    return request<AnalysisStats>("/api/stats");
  },

  async getAnalyses(
    params: {
      limit?: number;
      offset?: number;
      status?: string;
      media_type?: string;
      q?: string;
    } = {}
  ): Promise<AnalysisListResponse> {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
    if (params.status) searchParams.set("status", params.status);
    if (params.media_type) searchParams.set("media_type", params.media_type);
    if (params.q) searchParams.set("q", params.q);

    const query = searchParams.toString();
    const endpoint = query ? `/api/analyses?${query}` : "/api/analyses";
    return request<AnalysisListResponse>(endpoint);
  },

  async getAnalysis(analysisId: string): Promise<AnalysisDetailResponse> {
    return request<AnalysisDetailResponse>(`/api/analyses/${encodeURIComponent(analysisId)}`);
  },

  async getEvidence(analysisId: string): Promise<EvidenceDetailResponse> {
    return request<EvidenceDetailResponse>(
      `/api/analyses/${encodeURIComponent(analysisId)}/evidence`
    );
  },

  async submitAnalysis(file: File, idempotencyKey?: string): Promise<AnalysisDetailResponse> {
    const formData = new FormData();
    formData.append("file", file, file.name);

    const headers: Record<string, string> = {};
    if (idempotencyKey) {
      headers["Idempotency-Key"] = idempotencyKey;
    } else if (typeof crypto !== "undefined" && crypto.randomUUID) {
      headers["Idempotency-Key"] = crypto.randomUUID();
    }

    return request<AnalysisDetailResponse>("/api/analyses", {
      method: "POST",
      headers,
      body: formData,
    });
  },

  async deleteAnalysis(analysisId: string): Promise<void> {
    await request<void>(`/api/analyses/${encodeURIComponent(analysisId)}`, {
      method: "DELETE",
    });
  },

  async getTestSamples(): Promise<TestSamplesResponse> {
    return request<TestSamplesResponse>("/api/test-samples");
  },

  async getTestSampleBlob(sampleId: string): Promise<Blob> {
    return requestBlob(`/api/test-samples/${encodeURIComponent(sampleId)}/file`);
  },

  async getReportBlob(analysisId: string): Promise<Blob> {
    return requestBlob(`/api/analyses/${encodeURIComponent(analysisId)}/report`);
  },
};

