/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend API. Defaults to "/api" (proxied by Vite in development). */
  readonly VITE_API_BASE_URL?: string
  /** Backend origin the Vite dev server proxies /api to. */
  readonly VITE_BACKEND_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
