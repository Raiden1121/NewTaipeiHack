/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  /** 政策分析助理的 AI endpoint；省略時用同網域的 /api/ai（CloudFront 轉到 AI Lambda）。 */
  readonly VITE_AI_ENDPOINT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
