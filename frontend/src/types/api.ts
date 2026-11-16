/** Error envelope returned by every backend error response. */
export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  data_schema_version: number
  market_data_provider: string
  server_time: string
}
