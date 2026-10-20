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

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  if (!response.ok) {
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

export const api = {
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

  getReportDownloadUrl(analysisId: string): string {
    return `/api/analyses/${encodeURIComponent(analysisId)}/report`;
  },

  async getTestSamples(): Promise<TestSamplesResponse> {
    return request<TestSamplesResponse>("/api/test-samples");
  },

  async getTestSampleBlob(sampleId: string): Promise<Blob> {
    const response = await fetch(`/api/test-samples/${encodeURIComponent(sampleId)}/file`);
    if (!response.ok) {
      throw new TrustlensApiError("Failed to fetch test sample file", "file_not_found", response.status);
    }
    return response.blob();
  },
};
