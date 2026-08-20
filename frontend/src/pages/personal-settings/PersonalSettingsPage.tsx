import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  Database,
  Download,
  Eraser,
  Eye,
  EyeOff,
  Fingerprint,
  ImageUp,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  Moon,
  Palette,
  PawPrint,
  PencilLine,
  PlugZap,
  RotateCcw,
  Save,
  ShieldCheck,
  Sun,
  UserRound,
  X,
  type LucideIcon,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import { getApiErrorMessage } from '../../api/client';
import { WorkspaceToast, type ToastTone, type WorkspaceToastItem } from '../../components/shared/WorkspaceToast';
import { PageHeader } from '../../components/shared/PageHeader';
import { useConfirm } from '../../context/ConfirmContext';
import { useCourseContextStore } from '../../stores/course-context.store';
import { useConversationStore } from '../../stores/conversation.store';
import { useSessionStore } from '../../stores/session.store';
import {
  buildUserScopedStorageKey,
  CONVERSATION_ACTIVE_SESSION_KEY_PREFIX,
  CONVERSATION_HISTORY_KEY_PREFIX,
  CONVERSATION_MESSAGES_KEY_PREFIX,
  LEGACY_CONVERSATION_CACHE_KEYS,
} from '../../constants/storage-keys';
import {
  codexPetCatalog,
  codexPetVisibilityChangedEventName,
  codexPetVisibleStorageKey,
  readCodexPetVisible,
  readSelectedCodexPet,
  saveCodexPetVisibility,
  saveSelectedCodexPet,
  type CodexPetDefinition,
  type CodexPetVisibilityPayload,
} from '../../config/codex-pets';
import { formatProviderTestNotice } from '../../utils/providerTestNotice';
import { readLocalString, removeLocalItem } from '../../utils/browser-storage';
import {
  APPEARANCE_UPLOAD_ALLOWED_MIME,
  compressImageToDataUrl,
  readAppearance,
  resetAppearance,
  saveAppearance,
  type AppearanceBgMode,
  type AppearanceState,
  type AppearanceTheme,
} from '../../config/appearance';
import {
  PRESET_COLORS,
  PRESET_IMAGES,
  type PresetItem,
} from '../../config/appearance-presets';
import type { ModelProviderHealth } from '../../types';

const roleLabel: Record<string, string> = {
  admin: '管理员',
  student: '用户',
};

type StatusTone = 'neutral' | 'success' | 'warning' | 'danger';

type SettingsNavItem = {
  id: string;
  label: string;
  helper: string;
  Icon: LucideIcon;
};

type StatusChipProps = {
  label: string;
  tone?: StatusTone;
  Icon?: LucideIcon;
};

type ProfileStatProps = {
  label: string;
  value: string;
};

type SettingsRowProps = {
  label: string;
  value: string;
  helper: string;
  Icon: LucideIcon;
  action?: JSX.Element;
};

type SettingsActionProps = {
  label: string;
  Icon: LucideIcon;
  onClick: () => void;
  disabled?: boolean;
  pending?: boolean;
  tone?: 'default' | 'primary' | 'danger';
};

type IdentityFormState = {
  name: string;
};

type ModelOverrideFormState = {
  provider: string;
  base_url: string;
  api_key: string;
  chat_model: string;
  embedding_model: string;
  enabled: boolean;
  clear_api_key: boolean;
};

type PetOptionCardProps = {
  pet: CodexPetDefinition;
  selected: boolean;
  onSelect: (pet: CodexPetDefinition) => void;
};

const localLearningCacheKeys = [
  ...LEGACY_CONVERSATION_CACHE_KEYS,
  'zhike_workspace_chat_scroll',
  'zhike_ai_room_sessions',
  'zhike_ai_room_messages',
] as const;

const conversationCachePrefixes = [
  CONVERSATION_HISTORY_KEY_PREFIX,
  CONVERSATION_MESSAGES_KEY_PREFIX,
  CONVERSATION_ACTIVE_SESSION_KEY_PREFIX,
] as const;

const settingsNavItems: SettingsNavItem[] = [
  { id: 'settings-identity', label: '身份资料', helper: '账号与权限', Icon: UserRound },
  { id: 'settings-model', label: '模型连接', helper: '供应商与测试', Icon: KeyRound },
  { id: 'settings-pet', label: '学习伙伴', helper: '悬浮助手偏好', Icon: PawPrint },
  { id: 'settings-appearance', label: '外观主题', helper: '背景与壁纸', Icon: Palette },
  { id: 'settings-privacy', label: '隐私数据', helper: '导出与清理', Icon: ShieldCheck },
];

function resolveSettingsSectionId(hash: string): string {
  const sectionId = hash.replace(/^#/, '');
  return settingsNavItems.some((item) => item.id === sectionId) ? sectionId : settingsNavItems[0].id;
}

function valueOrEmpty(value?: string | null): string {
  return value && value.trim() ? value : '未提供';
}

function userInitial(name?: string | null): string {
  return valueOrEmpty(name).slice(0, 1);
}

function providerStatusText(status?: string | null): string {
  const normalized = status?.toLowerCase() ?? '';
  if (['healthy', 'ok', 'passed', 'success'].includes(normalized)) return '健康';
  if (['down', 'failed', 'error'].includes(normalized)) return '异常';
  if (['standby', 'pending', 'unknown'].includes(normalized)) return '待验证';
  return status || '未知';
}

function providerStatusTone(status?: string | null): StatusTone {
  const normalized = status?.toLowerCase() ?? '';
  if (['healthy', 'ok', 'passed', 'success'].includes(normalized)) return 'success';
  if (['down', 'failed', 'error'].includes(normalized)) return 'danger';
  if (['standby', 'pending', 'unknown'].includes(normalized)) return 'warning';
  return 'neutral';
}

function resolveDefaultChatProvider(providers: ModelProviderHealth[]): ModelProviderHealth | null {
  const chatProviders = providers.filter((item) =>
    item.provider_type !== 'embedding' && (item.provider_type === 'chat' || item.provider_type === 'both' || Boolean(item.chat_model)),
  );
  return chatProviders.find((item) => item.is_default) ?? chatProviders[0] ?? null;
}

function clearLocalLearningCache(userId: string | null): number {
  let removed = 0;
  if (userId) {
    for (const prefix of conversationCachePrefixes) {
      const key = buildUserScopedStorageKey(prefix, userId);
      if (readLocalString(key) !== null) {
        removeLocalItem(key);
        removed += 1;
      }
    }
  }
  for (const key of localLearningCacheKeys) {
    if (readLocalString(key) !== null) {
      removeLocalItem(key);
      removed += 1;
    }
  }
  return removed;
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function StatusChip({ label, tone = 'neutral', Icon }: StatusChipProps): JSX.Element {
  return (
    <span className={`personal-settings-chip personal-settings-chip--${tone}`}>
      {Icon ? <Icon size={14} /> : null}
      {label}
    </span>
  );
}

function ProfileStat({ label, value }: ProfileStatProps): JSX.Element {
  return (
    <div className="personal-settings-profile__stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SettingsAction({
  label,
  Icon,
  onClick,
  disabled = false,
  pending = false,
  tone = 'default',
}: SettingsActionProps): JSX.Element {
  return (
    <button
      type="button"
      className={`personal-settings-action personal-settings-action--${tone}`}
      disabled={disabled || pending}
      onClick={onClick}
    >
      {pending ? <Loader2 className="animate-spin" size={16} /> : <Icon size={16} />}
      <span>{pending ? '处理中' : label}</span>
    </button>
  );
}

function SettingsRow({ label, value, helper, Icon, action }: SettingsRowProps): JSX.Element {
  return (
    <div className="personal-settings-row">
      <div className="personal-settings-row__label">
        <Icon size={18} />
        <span>{label}</span>
      </div>
      <div className="personal-settings-row__body">
        <strong>{value}</strong>
        <p>{helper}</p>
      </div>
      {action ? <div className="personal-settings-row__action">{action}</div> : null}
    </div>
  );
}

function SettingsNavLink({
  item,
  active,
  onSelect,
}: {
  item: SettingsNavItem;
  active: boolean;
  onSelect: (id: string) => void;
}): JSX.Element {
  const Icon = item.Icon;

  return (
    <a
      className={`personal-settings-nav__item ${active ? 'is-active' : ''}`}
      href={`#${item.id}`}
      aria-current={active ? 'page' : undefined}
      onClick={() => onSelect(item.id)}
    >
      <span className="personal-settings-nav__icon" aria-hidden="true">
        <Icon size={17} />
      </span>
      <span className="personal-settings-nav__copy">
        <strong>{item.label}</strong>
        <small>{item.helper}</small>
      </span>
    </a>
  );
}

function PetOptionCard({ pet, selected, onSelect }: PetOptionCardProps): JSX.Element {
  const previewStyle = {
    '--settings-pet-sprite': `url("${pet.spritesheetUrl}")`,
  } as CSSProperties;

  return (
    <button
      type="button"
      className={`personal-settings-pet-card ${selected ? 'is-active' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(pet)}
    >
      <span className="personal-settings-pet-card__preview" style={previewStyle} aria-hidden="true" />
      <span className="personal-settings-pet-card__copy">
        <strong>{pet.displayName}</strong>
        <span>{pet.description}</span>
      </span>
      <span className="personal-settings-pet-card__state">{selected ? '使用中' : '切换'}</span>
    </button>
  );
}

type AppearancePresetCardProps = {
  preset: PresetItem;
  selected: boolean;
  onSelect: (preset: PresetItem) => void;
};

/** 外观预设卡片：图片预设显示缩略图，颜色预设显示色块。 */
function AppearancePresetCard({ preset, selected, onSelect }: AppearancePresetCardProps): JSX.Element {
  const isImage = preset.type === 'image';
  return (
    <button
      type="button"
      className={`personal-settings-appearance-card ${selected ? 'is-active' : ''}`}
      aria-pressed={selected}
      title={preset.description}
      onClick={() => onSelect(preset)}
    >
      <span
        className="personal-settings-appearance-card__thumb"
        style={{ background: isImage ? `url("${preset.thumb}") center/cover no-repeat` : preset.thumb }}
        aria-hidden="true"
      />
      <span className="personal-settings-appearance-card__copy">
        <strong>{preset.label}</strong>
        <span>{preset.defaultTheme === 'dark' ? '推荐深色文字' : '推荐亮色文字'}</span>
      </span>
      <span className="personal-settings-appearance-card__state">{selected ? '使用中' : '应用'}</span>
    </button>
  );
}

type AppearanceSectionProps = {
  state: AppearanceState;
  active: boolean;
  onThemeChange: (theme: AppearanceTheme) => void;
  onOverlayChange: (opacity: number) => void;
  onPresetSelect: (preset: PresetItem) => void;
  onUpload: (file: File) => void;
  onUseDefault: () => void;
  onClearUpload: () => void;
  uploading: boolean;
  uploadError: string | null;
};

/** 外观主题分区：明暗切换、遮罩滑块、预设网格、上传入口、恢复默认。 */
function AppearanceSection({
  state,
  active,
  onThemeChange,
  onOverlayChange,
  onPresetSelect,
  onUpload,
  onUseDefault,
  onClearUpload,
  uploading,
  uploadError,
}: AppearanceSectionProps): JSX.Element {
  const acceptAttr = APPEARANCE_UPLOAD_ALLOWED_MIME.join(',');
  const isDefault = state.bgMode === 'default';
  const isUpload = state.bgMode === 'upload';
  // 当前选中的预设 ID（仅 preset-* 模式下有意义）
  const activePresetId = state.bgMode === 'preset-image' || state.bgMode === 'preset-color' ? state.presetId : undefined;

  return (
    <section id="settings-appearance" className={`personal-settings-section ${active ? 'is-active' : ''}`}>
      <div className="personal-settings-section__head">
        <div>
          <h2>外观主题</h2>
          <p>选择工作台与登录页的背景，并切换文字明暗以保持可读。设置仅保存在当前设备。</p>
        </div>
        <StatusChip
          label={isDefault ? '默认外观' : state.theme === 'dark' ? '深色文字' : '亮色文字'}
          tone={isDefault ? 'neutral' : 'success'}
          Icon={Palette}
        />
      </div>

      <div className="personal-settings-appearance-control">
        <div className="personal-settings-appearance-control__body">
          <span className="personal-settings-appearance-control__icon" aria-hidden="true">
            {state.theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
          </span>
          <div>
            <strong>文字明暗模式</strong>
            <p>偏黑或深色背景请切换为深色文字，偏亮背景请使用亮色文字。</p>
          </div>
        </div>
        <div className="personal-settings-appearance-control__segmented" role="group" aria-label="文字明暗切换">
          <button
            type="button"
            className={`personal-settings-appearance-segment ${state.theme === 'light' ? 'is-active' : ''}`}
            onClick={() => onThemeChange('light')}
          >
            <Sun size={14} />
            亮色文字
          </button>
          <button
            type="button"
            className={`personal-settings-appearance-segment ${state.theme === 'dark' ? 'is-active' : ''}`}
            onClick={() => onThemeChange('dark')}
          >
            <Moon size={14} />
            深色文字
          </button>
        </div>
      </div>

      <div className="personal-settings-appearance-overlay">
        <div className="personal-settings-appearance-overlay__label">
          <span>背景遮罩</span>
          <strong>{Math.round(state.overlayOpacity * 100)}%</strong>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={Math.round(state.overlayOpacity * 100)}
          className="personal-settings-appearance-overlay__slider"
          aria-label="背景遮罩透明度"
          onChange={(event) => onOverlayChange(Number(event.target.value) / 100)}
        />
        <p>提高遮罩可让前景文字在繁杂背景下更清晰，深色文字配亮遮罩、深色文字配暗遮罩。</p>
      </div>

      <div className="personal-settings-appearance-group">
        <div className="personal-settings-appearance-group__head">
          <strong>预设壁纸</strong>
          <span>点击即应用，并自动套用推荐明暗</span>
        </div>
        <div className="personal-settings-appearance-grid">
          <button
            type="button"
            className={`personal-settings-appearance-card personal-settings-appearance-card--default ${isDefault ? 'is-active' : ''}`}
            aria-pressed={isDefault}
            onClick={onUseDefault}
          >
            <span className="personal-settings-appearance-card__thumb personal-settings-appearance-card__thumb--default" aria-hidden="true">
              <RotateCcw size={18} />
            </span>
            <span className="personal-settings-appearance-card__copy">
              <strong>默认外观</strong>
              <span>恢复系统渐变背景</span>
            </span>
            <span className="personal-settings-appearance-card__state">{isDefault ? '使用中' : '恢复'}</span>
          </button>
          {PRESET_IMAGES.map((preset) => (
            <AppearancePresetCard
              key={preset.id}
              preset={preset}
              selected={activePresetId === preset.id && state.bgMode === 'preset-image'}
              onSelect={onPresetSelect}
            />
          ))}
        </div>
      </div>

      <div className="personal-settings-appearance-group">
        <div className="personal-settings-appearance-group__head">
          <strong>预设颜色</strong>
          <span>纯色或渐变背景</span>
        </div>
        <div className="personal-settings-appearance-grid personal-settings-appearance-grid--color">
          {PRESET_COLORS.map((preset) => (
            <AppearancePresetCard
              key={preset.id}
              preset={preset}
              selected={activePresetId === preset.id && state.bgMode === 'preset-color'}
              onSelect={onPresetSelect}
            />
          ))}
        </div>
      </div>

      <div className="personal-settings-appearance-group">
        <div className="personal-settings-appearance-group__head">
          <strong>自定义上传</strong>
          <span>仅保存在当前浏览器，不超过 2MB（自动压缩）</span>
        </div>
        <div className="personal-settings-appearance-upload">
          <label className="personal-settings-appearance-upload__trigger">
            <input
              type="file"
              accept={acceptAttr}
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onUpload(file);
                // 重置 value 以便重复选择同一文件
                event.target.value = '';
              }}
            />
            <ImageUp size={16} />
            <span>{uploading ? '正在处理…' : '选择图片'}</span>
          </label>
          {isUpload && state.customImageName ? (
            <div className="personal-settings-appearance-upload__current">
              <span className="personal-settings-appearance-upload__thumb" style={state.customImageUrl ? { backgroundImage: `url("${state.customImageUrl}")` } : undefined} aria-hidden="true" />
              <div className="personal-settings-appearance-upload__meta">
                <strong>{state.customImageName}</strong>
                <span>已设为当前背景</span>
              </div>
              <button type="button" className="personal-settings-action" onClick={onClearUpload}>
                <X size={14} />
                <span>移除</span>
              </button>
            </div>
          ) : (
            <p className="personal-settings-appearance-upload__hint">
              支持 PNG / JPEG / WebP，上传后会自动压缩到 1920px 宽以内。
            </p>
          )}
          {uploadError && <p className="personal-settings-appearance-upload__error">{uploadError}</p>}
        </div>
      </div>
    </section>
  );
}

/** 渲染当前账号、课程上下文、模型连接、安全策略和退出登录联动设置页。 */
export function PersonalSettingsPage(): JSX.Element {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [toast, setToast] = useState<WorkspaceToastItem | null>(null);
  const [selectedPet, setSelectedPet] = useState<CodexPetDefinition>(() => readSelectedCodexPet());
  const [petVisible, setPetVisible] = useState<boolean>(() => readCodexPetVisible());
  // 外观主题状态：从 localStorage 初始化，变更后通过 saveAppearance 广播。
  const [appearance, setAppearance] = useState<AppearanceState>(() => readAppearance());
  const [appearanceUploading, setAppearanceUploading] = useState(false);
  const [appearanceUploadError, setAppearanceUploadError] = useState<string | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string>(() => {
    if (typeof window === 'undefined') return settingsNavItems[0].id;
    return resolveSettingsSectionId(window.location.hash);
  });
  const user = useSessionStore((state) => state.user);
  const updateSessionUser = useSessionStore((state) => state.updateUser);
  const clearSession = useSessionStore((state) => state.clearSession);
  const [isIdentityEditing, setIsIdentityEditing] = useState(false);
  const [identityForm, setIdentityForm] = useState<IdentityFormState>(() => ({ name: user?.name ?? '' }));
  const setGeneralMode = useCourseContextStore((state) => state.setGeneralMode);
  const { currentCourseId, currentCourseTitle } = useCourseContextStore();
  const hydrateConversationStore = useConversationStore((state) => state.hydrate);
  const localConversationCount = useConversationStore((state) => state.history.length);
  const localMessageCount = useConversationStore((state) =>
    Object.values(state.messagesBySession).reduce((sum, messages) => sum + messages.length, 0),
  );
  const settingsQuery = useQuery({ queryKey: ['personal-settings-summary'], queryFn: () => api.personalSettingsSummary() });
  const coursesQuery = useQuery({ queryKey: ['settings-my-courses'], queryFn: api.myCourses });
  const runtime = api.runtimeInfo();
  const isAdmin = user?.role === 'admin';
  const canUseAdminEndpoints = isAdmin || runtime.mode === 'mock';
  const providersQuery = useQuery({
    queryKey: ['settings-model-providers', 'all'],
    queryFn: () => api.modelProviders('all'),
    enabled: canUseAdminEndpoints,
    staleTime: 60_000,
  });
  const modelOverrideQuery = useQuery({
    queryKey: ['user-model-override'],
    queryFn: api.userModelOverride,
    staleTime: 60_000,
  });
  const settings = settingsQuery.data;
  const courses = coursesQuery.data?.items ?? [];
  const defaultProvider = useMemo(() => resolveDefaultChatProvider(providersQuery.data?.items ?? []), [providersQuery.data?.items]);
  const [modelOverrideForm, setModelOverrideForm] = useState<ModelOverrideFormState>({
    provider: '',
    base_url: '',
    api_key: '',
    chat_model: '',
    embedding_model: '',
    enabled: false,
    clear_api_key: false,
  });
  const roleText = roleLabel[user?.role ?? ''] ?? valueOrEmpty(user?.role);
  const trimmedIdentityName = identityForm.name.trim();
  const isIdentityChanged = trimmedIdentityName !== (user?.name ?? '').trim();
  const identityNameError = trimmedIdentityName.length === 0
    ? '显示名称不能为空。'
    : trimmedIdentityName.length > 120
      ? '显示名称不能超过 120 个字符。'
      : null;
  const modelStatus = defaultProvider
    ? `${providerStatusText(defaultProvider.status)} · ${defaultProvider.key_configured ? '密钥已托管' : '缺少密钥'}`
    : settings?.modelStatus ?? '未配置';
  const providerModel = defaultProvider
    ? [defaultProvider.display_name, defaultProvider.chat_model].filter(Boolean).join(' · ')
    : [settings?.provider, settings?.model].filter(Boolean).join(' · ') || '未配置';
  const modelTone = defaultProvider ? providerStatusTone(defaultProvider.status) : 'neutral';
  const privacyRetention = settings?.privacyRetention ?? '未配置';
  const documentCleanup = settings?.documentCleanup ?? '未配置';
  const localCacheText = `${localConversationCount} 个会话 / ${localMessageCount} 条消息`;
  const providerHelper = defaultProvider
    ? defaultProvider.key_configured
      ? '密钥由平台安全托管，本页只展示连接状态与模型名称。'
      : '默认服务商缺少密钥，请管理员在网关中心补齐配置。'
    : canUseAdminEndpoints
      ? '尚未配置默认聊天服务商，连接测试会保持不可用。'
      : '模型服务商由管理员统一维护，普通账号不可读取密钥状态。';

  function showToast(message: string, tone: ToastTone = 'info'): void {
    setToast({ id: `personal-settings-${Date.now()}`, message, tone });
  }

  useEffect(() => {
    function syncActiveSectionFromHash(): void {
      setActiveSectionId(resolveSettingsSectionId(window.location.hash));
    }

    syncActiveSectionFromHash();
    window.addEventListener('hashchange', syncActiveSectionFromHash);
    return () => window.removeEventListener('hashchange', syncActiveSectionFromHash);
  }, []);

  useEffect(() => {
    if (isIdentityEditing) return;
    setIdentityForm({ name: user?.name ?? '' });
  }, [isIdentityEditing, user?.name]);

  useEffect(() => {
    const override = modelOverrideQuery.data;
    if (!override) return;
    setModelOverrideForm({
      provider: override.provider ?? '',
      base_url: override.base_url ?? '',
      api_key: '',
      chat_model: override.chat_model ?? '',
      embedding_model: override.embedding_model ?? '',
      enabled: override.enabled,
      clear_api_key: false,
    });
  }, [modelOverrideQuery.data]);

  useEffect(() => {
    function handlePetVisibilityChanged(event: Event): void {
      const eventVisible = (event as CustomEvent<CodexPetVisibilityPayload>).detail?.visible;
      setPetVisible(typeof eventVisible === 'boolean' ? eventVisible : readCodexPetVisible());
    }

    function handleStorage(event: StorageEvent): void {
      if (event.key !== codexPetVisibleStorageKey) return;
      setPetVisible(readCodexPetVisible());
    }

    window.addEventListener(codexPetVisibilityChangedEventName, handlePetVisibilityChanged);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener(codexPetVisibilityChangedEventName, handlePetVisibilityChanged);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const updateIdentityMutation = useMutation({
    mutationFn: () => api.updateMe({ name: trimmedIdentityName }),
    onSuccess: ({ user: nextUser }) => {
      updateSessionUser(nextUser);
      setIdentityForm({ name: nextUser.name });
      setIsIdentityEditing(false);
      showToast('身份资料已更新。', 'success');
    },
    onError: (error) => showToast(getApiErrorMessage(error, '身份资料保存失败。'), 'error'),
  });

  const testProviderMutation = useMutation({
    mutationFn: async () => {
      if (!defaultProvider) throw new Error('未找到可测试的默认聊天服务商。');
      return api.testProvider(defaultProvider.provider);
    },
    onMutate: () => showToast('正在测试默认模型服务商', 'info'),
    onSuccess: (result) => {
      showToast(formatProviderTestNotice(result), result.status === 'passed' ? 'success' : 'error');
      queryClient.invalidateQueries({ queryKey: ['settings-model-providers'] });
      queryClient.invalidateQueries({ queryKey: ['model-providers'] });
    },
    onError: (error) => showToast(getApiErrorMessage(error, '连接测试失败。'), 'error'),
  });

  const saveModelOverrideMutation = useMutation({
    mutationFn: () => {
      if (!modelOverrideForm.provider.trim() || !modelOverrideForm.chat_model.trim()) {
        throw new Error('供应商编码和聊天模型不能为空。');
      }
      return api.saveUserModelOverride({
        provider: modelOverrideForm.provider.trim(),
        base_url: modelOverrideForm.base_url.trim() || null,
        api_key: modelOverrideForm.api_key || null,
        clear_api_key: modelOverrideForm.clear_api_key,
        chat_model: modelOverrideForm.chat_model.trim(),
        embedding_model: modelOverrideForm.embedding_model.trim() || null,
        enabled: modelOverrideForm.enabled,
      });
    },
    onMutate: () => showToast('正在保存个人模型覆盖', 'info'),
    onSuccess: (result) => {
      showToast(result.enabled ? '个人模型覆盖已保存并启用' : '个人模型覆盖已保存，尚未启用', 'success');
      setModelOverrideForm((current) => ({ ...current, api_key: '', clear_api_key: false }));
      queryClient.invalidateQueries({ queryKey: ['user-model-override'] });
    },
    onError: (error) => showToast(getApiErrorMessage(error, '个人模型覆盖保存失败。'), 'error'),
  });

  const deleteModelOverrideMutation = useMutation({
    mutationFn: api.deleteUserModelOverride,
    onMutate: () => showToast('正在移除个人模型覆盖', 'info'),
    onSuccess: (result) => {
      showToast(result.status === 'deleted' ? '个人模型覆盖已移除' : '当前没有已保存的个人覆盖', 'success');
      setModelOverrideForm({
        provider: '',
        base_url: '',
        api_key: '',
        chat_model: '',
        embedding_model: '',
        enabled: false,
        clear_api_key: false,
      });
      queryClient.invalidateQueries({ queryKey: ['user-model-override'] });
    },
    onError: (error) => showToast(getApiErrorMessage(error, '个人模型覆盖移除失败。'), 'error'),
  });

  const testModelOverrideMutation = useMutation({
    mutationFn: () => {
      if (!modelOverrideForm.provider.trim() || !modelOverrideForm.chat_model.trim()) {
        throw new Error('请先填写供应商编码和聊天模型。');
      }
      return api.testUserModelOverride({
        provider: modelOverrideForm.provider.trim(),
        base_url: modelOverrideForm.base_url.trim() || null,
        api_key: modelOverrideForm.api_key || null,
        chat_model: modelOverrideForm.chat_model.trim(),
      });
    },
    onMutate: () => showToast('正在测试个人模型配置', 'info'),
    onSuccess: (result) => showToast(formatProviderTestNotice(result), result.status === 'passed' ? 'success' : 'error'),
    onError: (error) => showToast(getApiErrorMessage(error, '个人模型连接测试失败。'), 'error'),
  });

  function startIdentityEdit(): void {
    setIdentityForm({ name: user?.name ?? '' });
    setIsIdentityEditing(true);
  }

  function cancelIdentityEdit(): void {
    setIdentityForm({ name: user?.name ?? '' });
    setIsIdentityEditing(false);
    updateIdentityMutation.reset();
  }

  function handleIdentitySubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!user) {
      showToast('登录状态已失效，请重新登录后再修改资料。', 'error');
      return;
    }
    if (identityNameError) {
      showToast(identityNameError, 'error');
      return;
    }
    if (!isIdentityChanged) {
      showToast('身份资料没有变化。', 'info');
      return;
    }
    updateIdentityMutation.mutate();
  }

  function exportMyData(): void {
    downloadJson(`zhike-personal-settings-${Date.now()}.json`, {
      exported_at: new Date().toISOString(),
      account: {
        id: user?.id ?? null,
        name: user?.name ?? null,
        email: user?.email ?? null,
        role: user?.role ?? null,
      },
      course_context: {
        current_course_id: currentCourseId || null,
        current_course_title: currentCourseTitle || null,
        available_courses: courses.map((course) => ({
          id: course.id,
          title: course.title,
          status: course.status ?? null,
        })),
      },
      model_provider: defaultProvider
        ? {
            provider: defaultProvider.provider,
            display_name: defaultProvider.display_name,
            status: defaultProvider.status,
            chat_model: defaultProvider.chat_model ?? null,
            key_configured: defaultProvider.key_configured ?? false,
          }
        : {
            provider: settings?.provider ?? null,
            model: settings?.model ?? null,
            status: settings?.modelStatus ?? null,
          },
      privacy: {
        retention: privacyRetention,
        document_cleanup: documentCleanup,
      },
      local_workspace: {
        local_conversations: localConversationCount,
        local_messages: localMessageCount,
      },
      codex_pet: {
        id: selectedPet.id,
        display_name: selectedPet.displayName,
        kind: selectedPet.kind,
        visible: petVisible,
      },
    });
    showToast('个人设置摘要已导出为 JSON 文件', 'success');
  }

  function handlePetSelect(pet: CodexPetDefinition): void {
    const nextPet = saveSelectedCodexPet(pet.id);
    setSelectedPet(nextPet);
    showToast(`已切换学习伙伴为 ${nextPet.displayName}`, 'success');
  }

  function handlePetVisibilityToggle(): void {
    const nextVisible = saveCodexPetVisibility(!petVisible);
    setPetVisible(nextVisible);
    showToast(nextVisible ? '学习伙伴已显示' : '学习伙伴已隐藏，可在这里重新开启', 'success');
  }

  /** 切换文字明暗模式，保留当前背景与遮罩设置。 */
  function handleAppearanceThemeChange(theme: AppearanceTheme): void {
    const next = saveAppearance({ ...appearance, theme });
    setAppearance(next);
  }

  /** 调整背景遮罩透明度。 */
  function handleAppearanceOverlayChange(opacity: number): void {
    const next = saveAppearance({ ...appearance, overlayOpacity: opacity });
    setAppearance(next);
  }

  /** 选择预设壁纸或颜色，保留用户当前手动选择的明暗模式。 */
  function handleAppearancePresetSelect(preset: PresetItem): void {
    const bgMode: AppearanceBgMode = preset.type === 'image' ? 'preset-image' : 'preset-color';
    const next = saveAppearance({
      ...appearance,
      bgMode,
      presetId: preset.id,
    });
    setAppearance(next);
    showToast(`已应用「${preset.label}」`, 'success');
  }

  /** 恢复默认外观：清除 localStorage 并回到系统渐变背景。 */
  function handleAppearanceUseDefault(): void {
    const next = resetAppearance();
    setAppearance(next);
    setAppearanceUploadError(null);
    showToast('已恢复默认外观', 'success');
  }

  /** 处理用户上传图片：压缩为 data URL 后写入 localStorage。 */
  async function handleAppearanceUpload(file: File): Promise<void> {
    setAppearanceUploading(true);
    setAppearanceUploadError(null);
    try {
      const dataUrl = await compressImageToDataUrl(file);
      const next = saveAppearance({
        ...appearance,
        bgMode: 'upload',
        presetId: undefined,
        customImageUrl: dataUrl,
        customImageName: file.name,
      });
      setAppearance(next);
      showToast('自定义背景已应用', 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : '图片处理失败，请重试';
      setAppearanceUploadError(message);
    } finally {
      setAppearanceUploading(false);
    }
  }

  /** 移除已上传的自定义背景，回退到默认外观。 */
  function handleAppearanceClearUpload(): void {
    const next = resetAppearance();
    setAppearance(next);
    setAppearanceUploadError(null);
    showToast('已移除自定义背景', 'info');
  }

  async function cleanupLocalData(): Promise<void> {
    const confirmed = await confirm({
      title: '清理本地学习草稿？',
      description: '此操作只清除当前设备中的学习草稿、消息缓存和页面位置，不会删除账号、课程知识库或学习画像。',
      confirmLabel: '清理学习草稿',
      tone: 'danger',
    });
    if (!confirmed) return;
    const removed = clearLocalLearningCache(user?.id ?? null);
    hydrateConversationStore();
    showToast(removed > 0 ? `已清理 ${removed} 组本地学习缓存` : '没有发现可清理的本地学习缓存', 'success');
  }

  async function handleLogout(): Promise<void> {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await api.logout();
    } catch {
      // 服务会话失效时仍然需要清理本地登录态。
    } finally {
      queryClient.clear();
      clearSession();
      setGeneralMode();
      setIsLoggingOut(false);
      navigate('/login', { replace: true });
    }
  }

  return (
    <div className="personal-settings-page">
      {/* Page Header 上移到双栏 grid 之上、独占整行，确保其顶部偏移与左对齐起点
         与其余学生端 overlay 页面完全一致；侧栏与内容区位于标题之下。 */}
      <PageHeader
        title="个人设置"
        subtitle="管理账号资料、外观主题、模型连接、学习伙伴与隐私数据，变更会同步到当前登录会话。"
      />
      <div className="personal-settings-layout">
        <aside className="personal-settings-sidebar" aria-label="设置导航与账号摘要">
          <button
            type="button"
            className="personal-settings-back"
            onClick={() => navigate('/dashboard')}
            title="返回工作台首页"
          >
            <ArrowLeft size={16} />
            <span>返回工作台</span>
          </button>

          <div className="personal-settings-sidebar__account">
            <div className="personal-settings-profile__avatar">{userInitial(user?.name)}</div>
            <div className="personal-settings-profile__identity">
              <span>当前账号</span>
              <h2>{valueOrEmpty(user?.name)}</h2>
              <p>{valueOrEmpty(user?.email)}</p>
            </div>
          </div>

          <nav className="personal-settings-nav" aria-label="个人设置分区">
            {settingsNavItems.map((item) => (
              <SettingsNavLink key={item.id} item={item} active={item.id === activeSectionId} onSelect={setActiveSectionId} />
            ))}
          </nav>

          <div className="personal-settings-profile__stats">
            <ProfileStat label="学习伙伴" value={`${selectedPet.displayName} · ${petVisible ? '显示中' : '已隐藏'}`} />
            <ProfileStat label="学习草稿" value={localCacheText} />
          </div>

          <div className="personal-settings-profile__actions">
            <SettingsAction label="导出设置摘要" Icon={Download} onClick={exportMyData} tone="primary" />
            <SettingsAction label="清理学习草稿" Icon={Eraser} onClick={() => void cleanupLocalData()} tone="danger" />
            <SettingsAction label={isLoggingOut ? '正在退出' : '安全退出'} Icon={LogOut} onClick={() => void handleLogout()} disabled={isLoggingOut} tone="danger" />
          </div>
        </aside>

        <main className="personal-settings-content" aria-label="个人设置内容">
          <div className="personal-settings-sheet">
            <section id="settings-identity" className={`personal-settings-section ${activeSectionId === 'settings-identity' ? 'is-active' : ''}`}>
              <div className="personal-settings-section__head">
                <div>
                  <h2>身份资料</h2>
                  <p>这些信息来自当前登录账号资料。</p>
                </div>
                <StatusChip label="登录有效" tone="success" Icon={CheckCircle2} />
              </div>
              <form className={`personal-settings-row personal-settings-identity-form ${isIdentityEditing ? 'is-editing' : ''}`} onSubmit={handleIdentitySubmit}>
                <div className="personal-settings-row__label">
                  <UserRound size={18} />
                  <span>显示名称</span>
                </div>
                <div className="personal-settings-row__body personal-settings-identity-form__body">
                  {isIdentityEditing ? (
                    <>
                      <label className="personal-settings-field" htmlFor="personal-settings-display-name">
                        <span>显示名称</span>
                        <input
                          id="personal-settings-display-name"
                          value={identityForm.name}
                          maxLength={120}
                          disabled={updateIdentityMutation.isPending}
                          onChange={(event) => setIdentityForm({ name: event.target.value })}
                          placeholder="请输入显示名称"
                        />
                      </label>
                      <p className={identityNameError ? 'personal-settings-field__error' : undefined}>
                        {identityNameError ?? '用于页面右上角、会话记录和学习报告展示。'}
                      </p>
                    </>
                  ) : (
                    <>
                      <strong>{valueOrEmpty(user?.name)}</strong>
                      <p>用于页面右上角、会话记录和学习报告展示。</p>
                    </>
                  )}
                </div>
                <div className="personal-settings-row__action personal-settings-identity-form__actions">
                  {isIdentityEditing ? (
                    <>
                      <button
                        type="submit"
                        className="personal-settings-action personal-settings-action--primary"
                        disabled={updateIdentityMutation.isPending || !isIdentityChanged || Boolean(identityNameError)}
                      >
                        {updateIdentityMutation.isPending ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                        <span>{updateIdentityMutation.isPending ? '保存中' : '保存'}</span>
                      </button>
                      <button
                        type="button"
                        className="personal-settings-action"
                        disabled={updateIdentityMutation.isPending}
                        onClick={cancelIdentityEdit}
                      >
                        <X size={16} />
                        <span>取消</span>
                      </button>
                    </>
                  ) : (
                    <SettingsAction label="修改" Icon={PencilLine} onClick={startIdentityEdit} disabled={!user} />
                  )}
                </div>
              </form>
              <SettingsRow label="登录邮箱" value={valueOrEmpty(user?.email)} helper="用于登录和区分账号的唯一联系方式。" Icon={Mail} />
              <SettingsRow label="账号 ID" value={valueOrEmpty(user?.id)} helper="系统生成的用户唯一标识，用于关联会话、课程和学习数据。" Icon={Fingerprint} />
              <SettingsRow label="权限角色" value={roleText} helper="普通用户不能进入管理中心，管理员权限由管理员统一分配。" Icon={ShieldCheck} />
            </section>

            <section id="settings-model" className={`personal-settings-section ${activeSectionId === 'settings-model' ? 'is-active' : ''}`}>
              <div className="personal-settings-section__head">
                <div>
                  <h2>模型与连接</h2>
                  <p>个人覆盖未配置时，使用管理员在网关中心维护的模型供应商。</p>
                </div>
                <StatusChip label={modelStatus} tone={modelTone} Icon={KeyRound} />
              </div>
              <SettingsRow label="默认服务商" value={providerModel} helper={providerHelper} Icon={KeyRound} />
              <SettingsRow
                label="连接测试"
                value={defaultProvider ? defaultProvider.display_name : '不可用'}
                helper={defaultProvider ? '发起连接检测并刷新服务商健康状态。' : '没有可测试的默认聊天服务商。'}
                Icon={PlugZap}
                action={
                  <SettingsAction
                    label="测试连接"
                    Icon={PlugZap}
                    onClick={() => testProviderMutation.mutate()}
                    disabled={!canUseAdminEndpoints || !defaultProvider}
                    pending={testProviderMutation.isPending}
                  />
                }
              />
              <div className="personal-settings-model-override">
                <div className="personal-settings-model-override__head">
                  <div>
                    <strong>个人模型覆盖</strong>
                    <p>保存后会优先用于普通对话，未启用时仍使用管理员维护的默认模型。</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={modelOverrideForm.enabled}
                    className={`personal-settings-switch ${modelOverrideForm.enabled ? 'is-on' : ''}`}
                    onClick={() => setModelOverrideForm((current) => ({ ...current, enabled: !current.enabled }))}
                  >
                    <span className="personal-settings-switch__track" aria-hidden="true">
                      <span className="personal-settings-switch__thumb" />
                    </span>
                    <span>{modelOverrideForm.enabled ? '已启用' : '已停用'}</span>
                  </button>
                </div>
                <div className="personal-settings-model-override__grid">
                  <label className="personal-settings-field">
                    <span>供应商编码</span>
                    <input
                      value={modelOverrideForm.provider}
                      maxLength={120}
                      placeholder="例如 deepseek"
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, provider: event.target.value }))}
                    />
                  </label>
                  <label className="personal-settings-field">
                    <span>聊天模型</span>
                    <input
                      value={modelOverrideForm.chat_model}
                      maxLength={120}
                      placeholder="例如 deepseek-chat"
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, chat_model: event.target.value }))}
                    />
                  </label>
                  <label className="personal-settings-field">
                    <span>Base URL</span>
                    <input
                      value={modelOverrideForm.base_url}
                      maxLength={500}
                      placeholder="https://api.deepseek.com"
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, base_url: event.target.value }))}
                    />
                  </label>
                  <label className="personal-settings-field">
                    <span>API Key</span>
                    <input
                      type="password"
                      value={modelOverrideForm.api_key}
                      maxLength={500}
                      placeholder={modelOverrideQuery.data?.key_configured ? '已保存密钥，留空保持不变' : '请输入 API Key'}
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, api_key: event.target.value }))}
                    />
                  </label>
                  <label className="personal-settings-field">
                    <span>Embedding 模型</span>
                    <input
                      value={modelOverrideForm.embedding_model}
                      maxLength={120}
                      placeholder="可选"
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, embedding_model: event.target.value }))}
                    />
                  </label>
                </div>
                {modelOverrideQuery.data?.key_configured && (
                  <label className="personal-settings-model-override__clear">
                    <input
                      type="checkbox"
                      checked={modelOverrideForm.clear_api_key}
                      onChange={(event) => setModelOverrideForm((current) => ({ ...current, clear_api_key: event.target.checked }))}
                    />
                    <span>移除已保存的 API Key</span>
                  </label>
                )}
                <div className="personal-settings-model-override__actions">
                  <button
                    type="button"
                    className="personal-settings-action personal-settings-action--primary"
                    disabled={saveModelOverrideMutation.isPending}
                    onClick={() => saveModelOverrideMutation.mutate()}
                  >
                    {saveModelOverrideMutation.isPending ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                    <span>{saveModelOverrideMutation.isPending ? '保存中' : '保存'}</span>
                  </button>
                  <button
                    type="button"
                    className="personal-settings-action"
                    disabled={testModelOverrideMutation.isPending}
                    onClick={() => testModelOverrideMutation.mutate()}
                  >
                    {testModelOverrideMutation.isPending ? <Loader2 className="animate-spin" size={16} /> : <PlugZap size={16} />}
                    <span>{testModelOverrideMutation.isPending ? '测试中' : '测试连接'}</span>
                  </button>
                  <button
                    type="button"
                    className="personal-settings-action"
                    disabled={deleteModelOverrideMutation.isPending}
                    onClick={() => deleteModelOverrideMutation.mutate()}
                  >
                    {deleteModelOverrideMutation.isPending ? <Loader2 className="animate-spin" size={16} /> : <Eraser size={16} />}
                    <span>{deleteModelOverrideMutation.isPending ? '移除中' : '移除'}</span>
                  </button>
                </div>
              </div>
            </section>

            <section id="settings-pet" className={`personal-settings-section ${activeSectionId === 'settings-pet' ? 'is-active' : ''}`}>
              <div className="personal-settings-section__head">
                <div>
                  <h2>学习伙伴</h2>
                  <p>选择悬浮在工作台右侧的 Codex Pet，切换后会立即应用到当前页面。</p>
                </div>
              </div>
              <div className="personal-settings-pet-control">
                <div className="personal-settings-pet-control__body">
                  <span className="personal-settings-pet-control__icon" aria-hidden="true">
                    <PawPrint size={18} />
                  </span>
                  <div>
                    <strong>悬浮学习伙伴</strong>
                    <p>当前伙伴：{selectedPet.displayName}</p>
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={petVisible}
                  className={`personal-settings-switch ${petVisible ? 'is-on' : ''}`}
                  onClick={handlePetVisibilityToggle}
                >
                  <span className="personal-settings-switch__track" aria-hidden="true">
                    <span className="personal-settings-switch__thumb">{petVisible ? <Eye size={12} /> : <EyeOff size={12} />}</span>
                  </span>
                  <span>{petVisible ? '已开启' : '已关闭'}</span>
                </button>
              </div>
              <div className="personal-settings-pet-grid" aria-label="宠物切换列表">
                {codexPetCatalog.map((pet) => (
                  <PetOptionCard key={pet.id} pet={pet} selected={pet.id === selectedPet.id} onSelect={handlePetSelect} />
                ))}
              </div>
            </section>

            <AppearanceSection
              state={appearance}
              active={activeSectionId === 'settings-appearance'}
              onThemeChange={handleAppearanceThemeChange}
              onOverlayChange={handleAppearanceOverlayChange}
              onPresetSelect={handleAppearancePresetSelect}
              onUpload={(file) => void handleAppearanceUpload(file)}
              onUseDefault={handleAppearanceUseDefault}
              onClearUpload={handleAppearanceClearUpload}
              uploading={appearanceUploading}
              uploadError={appearanceUploadError}
            />

            <section id="settings-privacy" className={`personal-settings-section ${activeSectionId === 'settings-privacy' ? 'is-active' : ''}`}>
              <div className="personal-settings-section__head">
                <div>
                  <h2>隐私与数据</h2>
                  <p>导出当前设置摘要，或清理当前设备中的学习草稿。</p>
                </div>
                <StatusChip label="不展示密钥" tone="success" Icon={ShieldCheck} />
              </div>
              <SettingsRow label="学习行为保留" value={privacyRetention} helper="学习行为保留策略由平台统一管控。" Icon={Database} />
              <SettingsRow label="个人文档清理" value={documentCleanup} helper="课程知识库文档由管理员在知识库管理页维护。" Icon={Database} />
              <SettingsRow
                label="数据导出"
                value="JSON 摘要"
                helper="导出账号、课程、模型和学习草稿统计，不包含密码或模型密钥。"
                Icon={Download}
                action={<SettingsAction label="导出" Icon={Download} onClick={exportMyData} tone="primary" />}
              />
              <SettingsRow
                label="学习草稿"
                value={localCacheText}
                helper="只清除当前设备中的会话草稿、消息缓存和页面位置。"
                Icon={Eraser}
                action={<SettingsAction label="清理" Icon={Eraser} onClick={() => void cleanupLocalData()} tone="danger" />}
              />
            </section>
          </div>
        </main>
      </div>
      <WorkspaceToast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
