import type { CSSProperties } from 'react';
import { readLocalString, writeLocalString, removeLocalItem } from '../utils/browser-storage';
import { tryParseJsonValue } from '../utils/json-parse';
import { DEFAULT_OVERLAY_HERO_IMAGE_URL, resolvePresetValue } from './appearance-presets';

/**
 * 工作台外观主题的个人偏好配置。
 * 仅作用于前端，通过 localStorage 持久化，不落库。
 */

/** 文字明暗模式：light 表示深色文字配亮背景，dark 表示浅色文字配暗背景。 */
export type AppearanceTheme = 'light' | 'dark';

/** 背景来源类型：default 保持现状，preset-* 使用预设，upload 使用用户上传图。 */
export type AppearanceBgMode = 'default' | 'preset-image' | 'preset-color' | 'upload';

/** 外观偏好完整状态。 */
export interface AppearanceState {
  /** 文字明暗模式，用户手动切换。 */
  theme: AppearanceTheme;
  /** 背景来源。 */
  bgMode: AppearanceBgMode;
  /** 预设 ID（bgMode 为 preset-image/preset-color 时有效）。 */
  presetId?: string;
  /** 用户上传图片的 data URL（bgMode 为 upload 时有效）。 */
  customImageUrl?: string;
  /** 上传文件名，仅用于 UI 展示。 */
  customImageName?: string;
  /** 遮罩透明度 0-1，暗背景下提升前景可读性。 */
  overlayOpacity: number;
  /** 最后更新时间（ISO 字符串），用于调试与过期清理。 */
  updatedAt: string;
}

/** localStorage 主键，与 codex-pet 系列保持同一前缀风格。 */
export const appearanceStorageKey = 'zhike-appearance';
/** 外观变更广播事件名，订阅方据此同步刷新。 */
export const appearanceChangedEventName = 'zhike-appearance-changed';

/** 默认状态：不改变现状，保持工作台原有渐变背景与深色文字。 */
export const DEFAULT_APPEARANCE_STATE: AppearanceState = {
  theme: 'light',
  bgMode: 'default',
  overlayOpacity: 0,
  updatedAt: new Date(0).toISOString(),
};

/** 上传图片大小上限（2MB），超出时前端拦截。 */
export const APPEARANCE_UPLOAD_MAX_BYTES = 2 * 1024 * 1024;
/** 允许上传的图片 MIME 白名单。 */
export const APPEARANCE_UPLOAD_ALLOWED_MIME = ['image/png', 'image/jpeg', 'image/webp'] as const;
/** 压缩后图片的最大宽度，避免 data URL 体积过大撑爆 localStorage。 */
export const APPEARANCE_COMPRESS_MAX_WIDTH = 1920;
/** 压缩后 JPEG 质量。 */
export const APPEARANCE_COMPRESS_QUALITY = 0.82;

/** 解析 localStorage 字符串为 AppearanceState，损坏时回退默认值。 */
function parseAppearanceState(raw: string | null): AppearanceState {
  if (!raw) return { ...DEFAULT_APPEARANCE_STATE };
  const parsed = tryParseJsonValue(raw) as Partial<AppearanceState>;
  if (!parsed || typeof parsed !== 'object') {
    // 数据损坏时清理并回退默认值，避免反复抛错。
    removeLocalItem(appearanceStorageKey);
    return { ...DEFAULT_APPEARANCE_STATE };
  }
  return {
    theme: parsed.theme === 'dark' ? 'dark' : 'light',
    bgMode: validateBgMode(parsed.bgMode),
    presetId: typeof parsed.presetId === 'string' ? parsed.presetId : undefined,
    customImageUrl: typeof parsed.customImageUrl === 'string' ? parsed.customImageUrl : undefined,
    customImageName: typeof parsed.customImageName === 'string' ? parsed.customImageName : undefined,
    overlayOpacity: clampOverlay(parsed.overlayOpacity),
    updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : DEFAULT_APPEARANCE_STATE.updatedAt,
  };
}

function validateBgMode(value: unknown): AppearanceBgMode {
  switch (value) {
    case 'default':
    case 'preset-image':
    case 'preset-color':
    case 'upload':
      return value;
    default:
      return 'default';
  }
}

function clampOverlay(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.min(1, Math.max(0, numeric));
}

/** 从 localStorage 读取当前外观偏好，读取失败时使用默认值。 */
export function readAppearance(): AppearanceState {
  return parseAppearanceState(readLocalString(appearanceStorageKey));
}

/** 保存外观偏好并广播变更事件，通知同页所有订阅方立即刷新。 */
export function saveAppearance(next: AppearanceState): AppearanceState {
  const normalized: AppearanceState = {
    ...next,
    updatedAt: new Date().toISOString(),
  };
  if (typeof window === 'undefined') return normalized;
  try {
    writeLocalString(appearanceStorageKey, JSON.stringify(normalized));
  } catch {
    // localStorage 写入失败（通常是配额已满）时静默降级，仅广播当前会话内生效。
  }
  window.dispatchEvent(new CustomEvent<AppearanceState>(appearanceChangedEventName, { detail: normalized }));
  return normalized;
}

/** 重置为默认外观并广播。 */
export function resetAppearance(): AppearanceState {
  removeLocalItem(appearanceStorageKey);
  const fallback = { ...DEFAULT_APPEARANCE_STATE };
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<AppearanceState>(appearanceChangedEventName, { detail: fallback }));
  }
  return fallback;
}

/**
 * 订阅外观变更事件，返回取消订阅函数。
 * 供 React 组件在 useEffect 中挂载监听。
 */
export function subscribeAppearance(handler: (state: AppearanceState) => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const listener = (event: Event): void => {
    const customEvent = event as CustomEvent<AppearanceState>;
    handler(customEvent.detail ?? readAppearance());
  };
  window.addEventListener(appearanceChangedEventName, listener);
  return () => window.removeEventListener(appearanceChangedEventName, listener);
}

/** 工作台根节点 inline CSS 变量类型。 */
type WorkspaceAppearanceCssVars = CSSProperties & Record<`--workspace-${string}`, string>;

/**
 * 把外观状态转换为工作台根节点（.ai-workspace-shell）的 inline CSS 变量。
 * 这些变量仅用于驱动文字/卡片颜色覆盖，不再注入背景。
 * 背景由独立的 fixed 背景层承载（见 buildWorkspaceBackgroundLayerStyle），
 * 避免背景样式污染 shell 内部流布局与定位。
 */
export function buildWorkspaceAppearanceStyle(state: AppearanceState): WorkspaceAppearanceCssVars {
  if (state.bgMode === 'default') return {};
  const textPrimary = state.theme === 'dark' ? '#f8fafc' : '#0f172a';
  const textSecondary = state.theme === 'dark' ? '#cbd5e1' : '#475569';
  const surface = state.theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.72)';
  const border = state.theme === 'dark' ? 'rgba(255,255,255,0.14)' : 'rgba(15,23,42,0.10)';
  return {
    '--workspace-text-primary': textPrimary,
    '--workspace-text-secondary': textSecondary,
    '--workspace-surface': surface,
    '--workspace-border': border,
  };
}

/**
 * 构造独立背景层的 inline style。
 * 该层 fixed 定位、z-index: -1，与 shell 内部流布局完全解耦，
 * 仅承载背景图与遮罩，不参与 shell 的 flex/absolute 定位计算。
 * bgMode === 'default' 时返回空对象，由调用方决定是否渲染背景层。
 */
export function buildWorkspaceBackgroundLayerStyle(state: AppearanceState): CSSProperties {
  if (state.bgMode === 'default') return {};
  const backgroundImage = resolveBackgroundImage(state);
  const overlay = state.overlayOpacity > 0 ? buildOverlayColor(state.theme, state.overlayOpacity) : 'transparent';
  const hasOverlay = overlay !== 'transparent';
  // 图片预设：url(...) 放底层，遮罩用 linear-gradient 叠在上层。
  if (backgroundImage.startsWith('url(')) {
    return {
      backgroundImage: hasOverlay
        ? `linear-gradient(${overlay}, ${overlay}), ${backgroundImage}`
        : backgroundImage,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    };
  }
  // 颜色/渐变预设：纯色包装成 linear-gradient 以统一走 background-image 通道。
  const isGradient = backgroundImage.startsWith('linear-gradient') || backgroundImage.startsWith('radial-gradient');
  const colorLayer = isGradient ? backgroundImage : `linear-gradient(${backgroundImage}, ${backgroundImage})`;
  return {
    backgroundImage: hasOverlay ? `linear-gradient(${overlay}, ${overlay}), ${colorLayer}` : colorLayer,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundRepeat: 'no-repeat',
  };
}

/**
 * 解析学生端 overlay 页头通栏背景的 CSS background-image 值。
 * 默认使用薄荷森林预设；用户启用外观主题时与工作台背景保持一致。
 */
export function resolveOverlayPageHeroBackground(state: AppearanceState): string {
  if (state.bgMode === 'default') {
    return `linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.28)), url("${DEFAULT_OVERLAY_HERO_IMAGE_URL}")`;
  }
  const layerStyle = buildWorkspaceBackgroundLayerStyle(state);
  const backgroundImage = layerStyle.backgroundImage;
  if (typeof backgroundImage === 'string' && backgroundImage.length > 0) {
    return backgroundImage;
  }
  return `url("${DEFAULT_OVERLAY_HERO_IMAGE_URL}")`;
}

/** 解析外观状态为 CSS background-image 值。 */
function resolveBackgroundImage(state: AppearanceState): string {
  if (state.bgMode === 'upload' && state.customImageUrl) {
    return `url("${state.customImageUrl}")`;
  }
  if (state.bgMode === 'preset-image' || state.bgMode === 'preset-color') {
    // 预设值（图片 URL 或颜色/渐变）由 appearance-presets.ts 查表解析。
    return resolvePresetValue(state.presetId);
  }
  return 'none';
}

/** 根据明暗模式与遮罩透明度构造遮罩颜色。 */
function buildOverlayColor(theme: AppearanceTheme, opacity: number): string {
  if (theme === 'dark') {
    return `rgba(0,0,0,${opacity.toFixed(3)})`;
  }
  return `rgba(255,255,255,${opacity.toFixed(3)})`;
}

/**
 * 把用户上传的 File 压缩为 data URL。
 * 使用 canvas 等比缩放到 APPEARANCE_COMPRESS_MAX_WIDTH 内，输出 JPEG。
 * 失败时抛出错误，由调用方提示用户。
 */
export async function compressImageToDataUrl(file: File): Promise<string> {
  if (!APPEARANCE_UPLOAD_ALLOWED_MIME.includes(file.type as (typeof APPEARANCE_UPLOAD_ALLOWED_MIME)[number])) {
    throw new Error('仅支持 PNG / JPEG / WebP 格式的图片');
  }
  if (file.size > APPEARANCE_UPLOAD_MAX_BYTES) {
    throw new Error(`图片大小不能超过 ${Math.round(APPEARANCE_UPLOAD_MAX_BYTES / 1024 / 1024)}MB`);
  }
  const dataUrl = await readFileAsDataUrl(file);
  const img = await loadImage(dataUrl);
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, APPEARANCE_COMPRESS_MAX_WIDTH / img.width);
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('无法创建压缩画布，请更换浏览器重试');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', APPEARANCE_COMPRESS_QUALITY);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(new Error('图片读取失败，请重试'));
    reader.readAsDataURL(file);
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('图片加载失败，请确认文件未损坏'));
    img.src = src;
  });
}
