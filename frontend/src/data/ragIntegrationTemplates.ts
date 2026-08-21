import { api } from '../api/endpoints';
import type { RagIntegrationTemplate } from '../types';
import bundledRagTemplates from './rag-integration-templates.json';
import { parseBundledRagIntegrationTemplates } from './templateValidation';

const BUNDLED_ITEMS = parseBundledRagIntegrationTemplates(bundledRagTemplates);

const TEMPLATES_PLACEHOLDER = { items: BUNDLED_ITEMS, source: 'bundled' as const };

const TEMPLATES_FETCH_TIMEOUT_MS = 12_000;

export function getBundledRagIntegrationTemplates(): RagIntegrationTemplate[] {
  return BUNDLED_ITEMS;
}

export function bundledRagIntegrationTemplatesQueryData(): {
  items: RagIntegrationTemplate[];
  source: 'bundled';
} {
  return TEMPLATES_PLACEHOLDER;
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export async function loadRagIntegrationTemplates(): Promise<{
  items: RagIntegrationTemplate[];
  source: 'api' | 'bundled';
}> {
  try {
    const result = await withTimeout(
      api.ragIntegrationTemplates(),
      TEMPLATES_FETCH_TIMEOUT_MS,
      '加载知识库接入模板超时，请确认后端已启动（默认 http://localhost:8001）',
    );
    if (result.items?.length) {
      return { items: result.items, source: 'api' };
    }
  } catch {
    // 后端不可用时回退到内置模板。
  }
  return TEMPLATES_PLACEHOLDER;
}

export function findRagTemplate(
  templates: RagIntegrationTemplate[],
  key: string | null | undefined,
): RagIntegrationTemplate | undefined {
  if (!key) return undefined;
  const normalized = key === 'iflytek_chatdoc' ? 'iflytek-chatdoc' : key;
  return templates.find((item) => item.key === normalized);
}

/** 网关编辑器下拉：始终展示全部预置模板（选择用哪套预置配置），并保证当前选中项在列表中 */
export function buildKnowledgePickerTemplates(
  templates: RagIntegrationTemplate[],
  currentKey: string | null,
): RagIntegrationTemplate[] {
  const presets = templates
    .filter((item) => item.key !== GENERIC_RAG_TEMPLATE_KEY)
    .sort((a, b) => a.label.localeCompare(b.label, 'zh'));
  if (!currentKey || presets.some((item) => item.key === currentKey)) {
    return presets;
  }
  const current = findRagTemplate(templates, currentKey);
  return current ? [current, ...presets] : presets;
}

export const GENERIC_RAG_TEMPLATE_KEY = 'generic-cloud-rag';

/** 新增时下拉占位，与空字符串（通用云端 RAG）区分，避免无法触发 onChange */
export const RAG_TEMPLATE_PICK_PLACEHOLDER = '__pick_template__';

const BUNDLED_GENERIC_TEMPLATE = BUNDLED_ITEMS.find((item) => item.key === GENERIC_RAG_TEMPLATE_KEY);

/** 与后端 client / 模板 JSON 对齐；API 未返回 default_base_url 时仍展示 */
const PRESET_RAG_API_BASE_URLS: Record<string, string> = {
  'iflytek-chatdoc': 'https://chatdoc.xfyun.cn',
  iflytek_chatdoc: 'https://chatdoc.xfyun.cn',
  'dashscope-bailian': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  dashscope_kb: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  'zhipu-knowledge': 'https://open.bigmodel.cn/api/paas/v4',
  zhipu_kb: 'https://open.bigmodel.cn/api/paas/v4',
};

export function isGenericRagTemplate(template?: RagIntegrationTemplate | null): boolean {
  if (!template) return false;
  return template.key === GENERIC_RAG_TEMPLATE_KEY || template.meta_json?.custom_form === true;
}

export function resolveGenericRagTemplate(templates: RagIntegrationTemplate[]): RagIntegrationTemplate | undefined {
  return findRagTemplate(templates, GENERIC_RAG_TEMPLATE_KEY) ?? BUNDLED_GENERIC_TEMPLATE;
}

export function defaultCredentialValues(template: RagIntegrationTemplate): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of template.credential_fields) {
    if (field.default != null) {
      values[field.key] = String(field.default);
    }
  }
  const meta = template.meta_json ?? {};
  if (typeof meta.default_base_url === 'string' && meta.default_base_url.trim()) {
    values.base_url = meta.default_base_url.trim();
  }
  if (typeof meta.default_app_id === 'string' && meta.default_app_id.trim()) {
    values.app_id = meta.default_app_id.trim();
  }
  return values;
}

/** 预置模板中带默认值的非密钥字段由模板锁定，用户只需填写控制台凭证 */
export function isCredentialFieldLocked(
  template: RagIntegrationTemplate,
  field: RagIntegrationTemplate['credential_fields'][number],
): boolean {
  if (field.type === 'password') return false;
  if (field.key === 'base_url') return false;
  const lockedKeys = template.meta_json?.locked_credential_keys;
  if (Array.isArray(lockedKeys) && lockedKeys.some((item) => String(item) === field.key)) {
    return true;
  }
  if (isGenericRagTemplate(template)) {
    return field.default != null;
  }
  return field.default != null;
}

export function resolveTemplateApiBaseUrl(
  template: RagIntegrationTemplate,
  formValues?: Record<string, string>,
  config?: { base_url?: string | null },
): string {
  const fromForm = (formValues?.base_url ?? '').trim();
  if (fromForm) return fromForm;
  const fromConfig = (config?.base_url ?? '').trim();
  if (fromConfig) return fromConfig;
  const fromMeta = typeof template.meta_json?.default_base_url === 'string'
    ? template.meta_json.default_base_url.trim()
    : '';
  if (fromMeta) return fromMeta;
  const baseField = template.credential_fields.find((field) => field.key === 'base_url');
  if (baseField?.default != null) return String(baseField.default);
  return PRESET_RAG_API_BASE_URLS[template.key] ?? PRESET_RAG_API_BASE_URLS[template.rag_backend] ?? '';
}

export function templateShowsLockedApiBaseUrl(template: RagIntegrationTemplate): boolean {
  if (isGenericRagTemplate(template)) return false;
  return !template.credential_fields.some((field) => field.key === 'base_url');
}

export function shouldShowPresetTemplateApiBaseUrl(template: RagIntegrationTemplate): boolean {
  return templateShowsLockedApiBaseUrl(template);
}

export function buildTemplateEditorConfig(
  templateKey: string,
  template: RagIntegrationTemplate,
  activeKey?: string,
  saved?: import('../types').ChatdocConfigView,
): import('../types').ChatdocConfigView {
  if (saved) return saved;
  const defaults = defaultCredentialValues(template);
  const wikiRaw = defaults.wiki_filter_score;
  return {
    integration_key: templateKey,
    template_key: templateKey,
    template_label: template.label,
    template_available: template.available,
    rag_backend: template.rag_backend,
    base_url: defaults.base_url || null,
    configured: false,
    credential_source: 'none',
    has_stored_secret: false,
    wiki_filter_score: wikiRaw ? Number(wikiRaw) : 0.2,
    is_active: true,
    active_integration_key: activeKey,
    env_fallback_hint: template.env_fallback_hint,
  };
}

export function createEmptyGenericRagFormValues(template: RagIntegrationTemplate): Record<string, string> {
  return { ...defaultCredentialValues(template), display_name: '', remarks: '', website_url: '' };
}

/** 新建网关实例时生成唯一 integration_key（同一预置可多次添加） */
export function generateKnowledgeInstanceKey(presetKey: string, displayName?: string): string {
  const slug = (displayName ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 24);
  const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  if (presetKey === GENERIC_RAG_TEMPLATE_KEY && slug) {
    return `${presetKey}-${slug}`;
  }
  return `${presetKey}-${suffix}`;
}
