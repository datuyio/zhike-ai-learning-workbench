const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
const EXPLICIT_WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL as string | undefined;

/** 依据 API 地址推导 WebSocket 根路径，显式配置优先。 */
function resolveWsBasePath(): string {
  if (EXPLICIT_WS_BASE_URL) {
    return EXPLICIT_WS_BASE_URL.replace(/\/$/, '');
  }

  if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
    const apiUrl = new URL(API_BASE_URL);
    const protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${apiUrl.host}/ws`;
  }

  // Vite base（子路径前缀）：部署在 /zhike/ 下时，相对地址推导必须拼上前缀，否则 WebSocket 连不上
  const BASE_PATH = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${BASE_PATH}/ws`;
}

/** 构造 AI 对话 WebSocket 地址；鉴权 token 通过连接后的 auth 帧发送。 */
export function buildAiWebSocketUrl(conversationId?: string | null): string {
  const normalizedConversationId = conversationId || 'new';
  return `${resolveWsBasePath()}/ai/${encodeURIComponent(normalizedConversationId)}`;
}

/** 构造资源任务进度 WebSocket 地址；鉴权 token 通过连接后的 auth 帧发送。 */
export function buildResourceWebSocketUrl(taskId: string): string {
  return `${resolveWsBasePath()}/resources/${encodeURIComponent(taskId)}`;
}
