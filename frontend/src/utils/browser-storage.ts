import { parseJsonValue } from './json-parse';

export type JsonValidator<T> = (value: unknown) => value is T;

function getBrowserStorage(kind: 'localStorage' | 'sessionStorage'): Storage | null {
  try {
    if (typeof window !== 'undefined') {
      return kind === 'localStorage' ? window.localStorage : window.sessionStorage;
    }
    // 兼容没有 window 的测试环境或非浏览器运行时，让内存存储桩仍可通过统一入口使用。
    if (typeof globalThis !== 'undefined') {
      const storage = globalThis[kind];
      if (storage) return storage;
    }
  } catch (error) {
    logStorageWarning('访问浏览器存储失败', kind, error);
  }
  return null;
}

function getLocalStorage(): Storage | null {
  return getBrowserStorage('localStorage');
}

function getSessionStorage(): Storage | null {
  return getBrowserStorage('sessionStorage');
}

function logStorageWarning(action: string, key: string, error: unknown): void {
  if (typeof console === 'undefined') return;
  const message = error instanceof Error ? error.message : String(error);
  console.warn(`[browser-storage] ${action}：${key}。${message}`);
}

/** 安全读取 localStorage 中的 JSON，并在不可用、解析失败或结构不匹配时返回兜底值。 */
export function readLocalJson<T>(key: string, fallback: T, validator: JsonValidator<T>): T {
  const storage = getLocalStorage();
  if (!storage) return fallback;

  try {
    const raw = storage.getItem(key);
    if (!raw) return fallback;
    const parsed = parseJsonValue(raw);
    if (validator(parsed)) return parsed;
    logStorageWarning('本地 JSON 结构不匹配，已使用兜底值', key, 'invalid-shape');
    storage.removeItem(key);
    return fallback;
  } catch (error) {
    logStorageWarning('读取本地 JSON 失败，已使用兜底值', key, error);
    storage.removeItem(key);
    return fallback;
  }
}

/** 安全写入 localStorage JSON；写入失败时返回 false，避免影响页面主流程。 */
export function writeLocalJson<T>(key: string, value: T): boolean {
  const storage = getLocalStorage();
  if (!storage) return false;

  try {
    storage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    logStorageWarning('写入本地 JSON 失败', key, error);
    return false;
  }
}

/** 安全读取 localStorage 文本；适合不需要 JSON 结构的简单偏好值。 */
export function readLocalString(key: string, fallback: string | null = null): string | null {
  const storage = getLocalStorage();
  if (!storage) return fallback;

  try {
    return storage.getItem(key) ?? fallback;
  } catch (error) {
    logStorageWarning('读取本地文本失败，已使用兜底值', key, error);
    return fallback;
  }
}

/** 安全写入 localStorage 文本；写入失败时返回 false，避免影响页面主流程。 */
export function writeLocalString(key: string, value: string): boolean {
  const storage = getLocalStorage();
  if (!storage) return false;

  try {
    storage.setItem(key, value);
    return true;
  } catch (error) {
    logStorageWarning('写入本地文本失败', key, error);
    return false;
  }
}

/** 安全移除 localStorage 条目；失败时只记录警告，不影响页面主流程。 */
export function removeLocalItem(key: string): boolean {
  const storage = getLocalStorage();
  if (!storage) return false;

  try {
    storage.removeItem(key);
    return true;
  } catch (error) {
    logStorageWarning('移除本地存储失败', key, error);
    return false;
  }
}

/** 安全读取 sessionStorage 中的 JSON；适合页面草稿、临时标签页状态等短生命周期数据。 */
export function readSessionJson<T>(key: string, fallback: T, validator: JsonValidator<T>): T {
  const storage = getSessionStorage();
  if (!storage) return fallback;

  try {
    const raw = storage.getItem(key);
    if (!raw) return fallback;
    const parsed = parseJsonValue(raw);
    if (validator(parsed)) return parsed;
    logStorageWarning('会话 JSON 结构不匹配，已使用兜底值', key, 'invalid-shape');
    storage.removeItem(key);
    return fallback;
  } catch (error) {
    logStorageWarning('读取会话 JSON 失败，已使用兜底值', key, error);
    storage.removeItem(key);
    return fallback;
  }
}

/** 安全写入 sessionStorage JSON；传入 null 或 undefined 时清理对应 key。 */
export function writeSessionJson<T>(key: string, value: T | null | undefined): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;

  try {
    if (value == null) storage.removeItem(key);
    else storage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    logStorageWarning('写入会话 JSON 失败', key, error);
    return false;
  }
}

/** 安全移除 sessionStorage 条目；失败时只记录警告，不影响页面主流程。 */
export function removeSessionItem(key: string): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;

  try {
    storage.removeItem(key);
    return true;
  } catch (error) {
    logStorageWarning('移除会话存储失败', key, error);
    return false;
  }
}

/** 安全读取 sessionStorage 文本；适合 token、临时 ID 等非 JSON 值。 */
export function readSessionString(key: string, fallback: string | null = null): string | null {
  const storage = getSessionStorage();
  if (!storage) return fallback;

  try {
    return storage.getItem(key) ?? fallback;
  } catch (error) {
    logStorageWarning('读取会话文本失败，已使用兜底值', key, error);
    return fallback;
  }
}

/** 安全写入 sessionStorage 文本；写入失败时返回 false，避免影响页面主流程。 */
export function writeSessionString(key: string, value: string): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;

  try {
    storage.setItem(key, value);
    return true;
  } catch (error) {
    logStorageWarning('写入会话文本失败', key, error);
    return false;
  }
}
