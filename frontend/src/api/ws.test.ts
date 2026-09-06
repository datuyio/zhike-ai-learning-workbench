import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildAiWebSocketUrl, buildResourceWebSocketUrl } from './ws';
import {
  AUTH_TOKEN_STORAGE_KEY,
  clearAuthStorage,
  readAuthToken,
  writeAuthToken,
} from '../utils/auth-storage';

class MemoryStorage implements Storage {
  private readonly items = new Map<string, string>();

  get length(): number {
    return this.items.size;
  }

  clear(): void {
    this.items.clear();
  }

  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.items.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.items.delete(key);
  }

  setItem(key: string, value: string): void {
    this.items.set(key, value);
  }
}

function stubBrowserWindow(localStorage = new MemoryStorage(), sessionStorage = new MemoryStorage()): void {
  vi.stubGlobal('window', {
    location: {
      protocol: 'https:',
      host: 'example.test',
    },
    localStorage,
    sessionStorage,
  } as unknown as Window);
}

function expectUrlDoesNotExposeAuthToken(url: string, token: string): void {
  const parsedUrl = new URL(url);
  expect(parsedUrl.search).toBe('');
  expect(parsedUrl.hash).toBe('');
  expect(parsedUrl.pathname).not.toContain(token);
  expect(url).not.toContain(token);
}

describe('WebSocket 地址构造', () => {
  afterEach(() => {
    clearAuthStorage();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('构造地址时不在查询、hash 或路径中暴露认证 token', () => {
    stubBrowserWindow();
    const token = 'secret-token';
    writeAuthToken(token);

    const aiUrl = buildAiWebSocketUrl('conv-1');
    const resourceUrl = buildResourceWebSocketUrl('task-1');

    expect(aiUrl).toBe('wss://example.test/ws/ai/conv-1');
    expect(resourceUrl).toBe('wss://example.test/ws/resources/task-1');
    expectUrlDoesNotExposeAuthToken(aiUrl, token);
    expectUrlDoesNotExposeAuthToken(resourceUrl, token);
    expect(aiUrl).not.toContain('token=');
    expect(resourceUrl).not.toContain('token=');
  });

  it('会编码路径参数，避免 ID 注入 WebSocket 查询串或 hash', () => {
    stubBrowserWindow();

    const url = buildAiWebSocketUrl('conv-1?token=leaked#frag/extra');
    const resourceUrl = buildResourceWebSocketUrl('task-1?token=leaked#frag/extra');

    expect(url).toBe('wss://example.test/ws/ai/conv-1%3Ftoken%3Dleaked%23frag%2Fextra');
    expect(resourceUrl).toBe('wss://example.test/ws/resources/task-1%3Ftoken%3Dleaked%23frag%2Fextra');
    expect(new URL(url).search).toBe('');
    expect(new URL(url).hash).toBe('');
    expect(new URL(resourceUrl).search).toBe('');
    expect(new URL(resourceUrl).hash).toBe('');
  });

  it('子路径部署（base=/zhike/）下，相对 API 地址推导的 WebSocket 地址带上子路径前缀', async () => {
    vi.resetModules();
    vi.stubEnv('BASE_URL', '/zhike/');
    const wsModule = await import('./ws');
    stubBrowserWindow();

    expect(wsModule.buildAiWebSocketUrl('conv-1')).toBe('wss://example.test/zhike/ws/ai/conv-1');
    expect(wsModule.buildResourceWebSocketUrl('task-1')).toBe('wss://example.test/zhike/ws/resources/task-1');
  });
});

describe('认证 token 存储策略', () => {
  afterEach(() => {
    clearAuthStorage();
    vi.unstubAllGlobals();
  });

  it('迁移旧版 localStorage token 到 sessionStorage 并清理长期副本', () => {
    const legacyLocalStorage = new MemoryStorage();
    const sessionStorage = new MemoryStorage();
    legacyLocalStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'legacy-token');
    stubBrowserWindow(legacyLocalStorage, sessionStorage);

    expect(readAuthToken()).toBe('legacy-token');
    expect(sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('legacy-token');
    expect(legacyLocalStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it('新 token 只写入 sessionStorage，不写入 localStorage', () => {
    const localStorage = new MemoryStorage();
    const sessionStorage = new MemoryStorage();
    stubBrowserWindow(localStorage, sessionStorage);

    writeAuthToken('fresh-token');

    expect(readAuthToken()).toBe('fresh-token');
    expect(sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('fresh-token');
    expect(localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });
});
