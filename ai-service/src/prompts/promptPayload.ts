/**
 * 送進模型的 prompt。刻意拆成 system / user 兩段，對應 Bedrock Converse API 的
 * `system` 與 `messages`：規則與範例放 system，這次請求的實際資料放 user。
 *
 * 這麼分不只是形式：system 內容在同一個 session 內是固定的，之後要接 prompt caching
 * 時可以直接快取這一段。
 */
export interface PromptPayload {
  system: string;
  user: string;
}
