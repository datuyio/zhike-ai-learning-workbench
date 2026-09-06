import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  Eye,
  FolderOpen,
  Image as ImageIcon,
  Link as LinkIcon,
  Loader2,
  Monitor,
  Palette,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  SlidersHorizontal,
  Upload,
  Video,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import { AdminMetricCard, AdminPageHeader, AdminPageShell } from '../../components/admin/AdminScaffold';
import {
  DEFAULT_LOGIN_BACKGROUND_SETTINGS,
  normalizeLoginBackgroundSettings,
} from '../../config/loginBackground';
import type { LoginBackgroundMediaAsset, LoginBackgroundMediaType, LoginBackgroundSettings } from '../../types';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

type SliderDefinition = {
  key: keyof Pick<LoginBackgroundSettings, 'position_x' | 'position_y' | 'scale' | 'brightness' | 'contrast' | 'saturate' | 'blur' | 'overlay_opacity'>;
  label: string;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  format?: (value: number) => string;
};

const sliderDefinitions: SliderDefinition[] = [
  { key: 'position_x', label: '水平焦点', min: 0, max: 100, step: 1, suffix: '%' },
  { key: 'position_y', label: '垂直焦点', min: 0, max: 100, step: 1, suffix: '%' },
  { key: 'scale', label: '画面缩放', min: 1, max: 1.35, step: 0.01, format: (value) => value.toFixed(2) },
  { key: 'brightness', label: '亮度', min: 0.5, max: 1.4, step: 0.01, format: (value) => value.toFixed(2) },
  { key: 'contrast', label: '对比度', min: 0.5, max: 1.6, step: 0.01, format: (value) => value.toFixed(2) },
  { key: 'saturate', label: '饱和度', min: 0, max: 2, step: 0.01, format: (value) => value.toFixed(2) },
  { key: 'blur', label: '模糊', min: 0, max: 12, step: 0.5, suffix: 'px', format: (value) => value.toFixed(1) },
  { key: 'overlay_opacity', label: '遮罩强度', min: 0, max: 0.85, step: 0.01, format: (value) => value.toFixed(2) },
];

function cleanLoginBackgroundDraft(draft: LoginBackgroundSettings): Partial<LoginBackgroundSettings> {
  return {
    enabled: draft.enabled,
    media_type: draft.media_type,
    media_url: draft.media_url.trim(),
    fit: draft.fit,
    position_x: draft.position_x,
    position_y: draft.position_y,
    scale: draft.scale,
    brightness: draft.brightness,
    contrast: draft.contrast,
    saturate: draft.saturate,
    blur: draft.blur,
    overlay_opacity: draft.overlay_opacity,
    fallback_color: draft.fallback_color,
  };
}

function formatSliderValue(definition: SliderDefinition, value: number): string {
  const text = definition.format ? definition.format(value) : String(value);
  return `${text}${definition.suffix ?? ''}`;
}

function formatUploadSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

function formatAssetSize(size?: number | null): string {
  return typeof size === 'number' ? formatUploadSize(size) : '内置资源';
}

function ServerAssetPreview({ asset }: { asset: LoginBackgroundMediaAsset }): JSX.Element {
  if (asset.media_type === 'video') {
    return (
      <video muted playsInline loop preload="metadata">
        <source src={asset.media_url} type={asset.media_url.toLowerCase().includes('.webm') ? 'video/webm' : 'video/mp4'} />
      </video>
    );
  }
  return <img src={asset.media_url} alt="" />;
}

function SliderField({
  definition,
  value,
  onChange,
}: {
  definition: SliderDefinition;
  value: number;
  onChange: (value: number) => void;
}): JSX.Element {
  return (
    <label className="interface-settings-slider">
      <span>
        <b>{definition.label}</b>
        <em>{formatSliderValue(definition, value)}</em>
      </span>
      <input
        type="range"
        min={definition.min}
        max={definition.max}
        step={definition.step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export function InterfaceSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = useState<LoginBackgroundSettings>(DEFAULT_LOGIN_BACKGROUND_SETTINGS);
  const [notice, setNotice] = useState('');
  const [serverPickerOpen, setServerPickerOpen] = useState(false);

  const settingsQuery = useQuery({
    queryKey: ['admin-login-background-settings'],
    queryFn: () => api.adminLoginBackgroundSettings(),
  });
  const serverAssetsQuery = useQuery({
    queryKey: ['admin-login-background-media-assets'],
    queryFn: () => api.loginBackgroundMediaAssets(),
    enabled: serverPickerOpen,
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setDraft(normalizeLoginBackgroundSettings(settingsQuery.data));
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = cleanLoginBackgroundDraft(draft);
      if (!payload.media_url) throw new Error('背景媒体地址不能为空');
      return api.updateLoginBackgroundSettings(payload);
    },
    onSuccess: (result) => {
      const next = normalizeLoginBackgroundSettings(result);
      setDraft(next);
      setNotice('登录背景已保存');
      window.setTimeout(() => setNotice(''), 2400);
      void queryClient.invalidateQueries({ queryKey: ['admin-login-background-settings'] });
      void queryClient.invalidateQueries({ queryKey: ['login-background-settings'] });
    },
    onError: (error) => {
      setNotice(error instanceof Error ? error.message : '保存失败');
    },
  });
  const uploadMutation = useMutation({
    mutationFn: api.uploadLoginBackgroundMedia,
    onSuccess: (result) => {
      setDraft((current) => ({
        ...current,
        media_type: result.media_type,
        media_url: result.media_url,
      }));
      setNotice(`已上传 ${result.filename}（${formatUploadSize(result.size)}），保存后生效`);
      void queryClient.invalidateQueries({ queryKey: ['admin-login-background-media-assets'] });
    },
    onError: (error) => {
      setNotice(error instanceof Error ? error.message : '上传失败');
    },
  });

  function updateDraft<K extends keyof LoginBackgroundSettings>(key: K, value: LoginBackgroundSettings[K]): void {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function handleUploadChange(file: File | null): void {
    if (!file) return;
    uploadMutation.mutate(file);
    if (uploadInputRef.current) uploadInputRef.current.value = '';
  }

  function selectServerAsset(asset: LoginBackgroundMediaAsset): void {
    setDraft((current) => ({
      ...current,
      media_type: asset.media_type,
      media_url: asset.media_url,
      enabled: true,
    }));
    setNotice(`已选择服务器资源 ${asset.filename}，保存后生效`);
    setServerPickerOpen(false);
  }

  const mediaTypeLabel = draft.media_type === 'video' ? '视频背景' : '图片背景';
  const serverAssets = serverAssetsQuery.data?.items ?? [];

  return (
    <AdminPageShell className="interface-settings-page">
      <AdminPageHeader
        title="界面设置"
        description="管理登录页背景媒体、画面焦点、滤镜和遮罩强度，保存后对登录页立即生效。"
        actions={(
        <>
          {notice && <span className="admin-announcement-notice">{notice}</span>}
          <button type="button" className="btn-secondary" onClick={() => setDraft(DEFAULT_LOGIN_BACKGROUND_SETTINGS)}>
            <RotateCcw size={16} />
            恢复默认
          </button>
          <button type="button" className="btn-primary" disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
            保存配置
          </button>
        </>
        )}
      />

      <section className="interface-settings-summary" aria-label="登录背景状态">
        <AdminMetricCard label="当前媒体" value={mediaTypeLabel} hint="登录页背景" icon={Monitor} tone="neutral" />
        <AdminMetricCard label="背景状态" value={draft.enabled ? '已启用' : '仅显示底色'} hint="保存后生效" icon={CheckCircle2} tone={draft.enabled ? 'success' : 'processing'} />
        <AdminMetricCard label="回退底色" value={draft.fallback_color} hint="媒体不可用时展示" icon={Palette} tone="neutral" />
        <AdminMetricCard label="上次保存" value={formatBeijingDateTimeCompact(draft.updated_at, settingsQuery.isLoading ? '加载中' : '未保存')} hint="配置更新时间" icon={Eye} tone="neutral" />
      </section>

      <div className="interface-settings-layout">
        <section className="interface-settings-panel" aria-label="登录背景配置">
          <div className="interface-settings-panel__head">
            <div>
              <span><ImageIcon size={16} /> 媒体源</span>
              <p>支持站内路径、公开 http(s) 地址和本地上传后的静态资源。</p>
            </div>
            {settingsQuery.isLoading && <Loader2 className="animate-spin text-slate-400" size={18} />}
          </div>

          <div className="interface-settings-form">
            <div className="interface-settings-segmented" aria-label="背景媒体类型">
              {([
                ['image', ImageIcon, '图片'] as const,
                ['video', Video, '视频'] as const,
              ]).map(([value, Icon, label]) => (
                <button
                  key={value}
                  type="button"
                  className={draft.media_type === value ? 'is-active' : ''}
                  onClick={() => updateDraft('media_type', value as LoginBackgroundMediaType)}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>

            <label className="interface-settings-field">
              <span>媒体地址</span>
              <div className="interface-settings-url-input">
                <LinkIcon size={15} />
                <input
                  value={draft.media_url}
                  onChange={(event) => updateDraft('media_url', event.target.value)}
                  placeholder="/auth/login-hero.mp4"
                />
              </div>
            </label>

            <input
              ref={uploadInputRef}
              type="file"
              className="sr-only"
              accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm"
              onChange={(event) => handleUploadChange(event.target.files?.[0] ?? null)}
            />
            <div className="interface-settings-source-actions">
              <button
                type="button"
                className="interface-settings-upload"
                disabled={uploadMutation.isPending}
                onClick={() => uploadInputRef.current?.click()}
              >
                {uploadMutation.isPending ? <Loader2 className="animate-spin" size={17} /> : <Upload size={17} />}
                {uploadMutation.isPending ? '正在上传' : '上传背景媒体'}
              </button>
              <button
                type="button"
                className="interface-settings-server-button"
                onClick={() => setServerPickerOpen((current) => !current)}
              >
                <FolderOpen size={17} />
                {serverPickerOpen ? '收起服务器资源' : '从服务器选择'}
              </button>
            </div>

            {serverPickerOpen && (
              <section className="interface-settings-library" aria-label="服务器背景媒体">
                <div className="interface-settings-library__head">
                  <span><Server size={15} /> 服务器资源</span>
                  <button type="button" onClick={() => void serverAssetsQuery.refetch()}>
                    {serverAssetsQuery.isFetching ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                    刷新
                  </button>
                </div>
                {serverAssetsQuery.isLoading && (
                  <p className="interface-settings-library__state">正在读取服务器媒体资源...</p>
                )}
                {serverAssetsQuery.isError && (
                  <p className="interface-settings-library__state">读取失败，请稍后重试。</p>
                )}
                {!serverAssetsQuery.isLoading && !serverAssetsQuery.isError && serverAssets.length === 0 && (
                  <p className="interface-settings-library__state">服务器暂无可选背景媒体。</p>
                )}
                {serverAssets.length > 0 && (
                  <div className="interface-settings-asset-list">
                    {serverAssets.map((asset) => {
                      const selected = draft.media_url === asset.media_url;
                      return (
                        <button
                          key={`${asset.source}-${asset.media_url}`}
                          type="button"
                          className={`interface-settings-asset ${selected ? 'is-selected' : ''}`}
                          onClick={() => selectServerAsset(asset)}
                        >
                          <span className="interface-settings-asset__preview">
                            <ServerAssetPreview asset={asset} />
                            <i>{asset.media_type === 'video' ? '视频' : '图片'}</i>
                          </span>
                          <span className="interface-settings-asset__meta">
                            <strong>{asset.filename}</strong>
                            <em>
                              {asset.source === 'built_in' ? '内置资源' : '服务器上传'}
                              {' · '}
                              {formatAssetSize(asset.size)}
                            </em>
                            <small>{formatBeijingDateTimeCompact(asset.updated_at, asset.source === 'built_in' ? '默认可用' : '时间未知')}</small>
                          </span>
                          {selected && <b>当前</b>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </section>
            )}

            <div className="interface-settings-form__grid">
              <label className="interface-settings-check">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => updateDraft('enabled', event.target.checked)}
                />
                <span>启用背景媒体</span>
              </label>
              <label className="interface-settings-field">
                <span>填充方式</span>
                <select className="input" value={draft.fit} onChange={(event) => updateDraft('fit', event.target.value as LoginBackgroundSettings['fit'])}>
                  <option value="cover">铺满裁切</option>
                  <option value="contain">完整显示</option>
                </select>
              </label>
              <label className="interface-settings-field">
                <span>回退底色</span>
                <input
                  className="input"
                  type="color"
                  value={draft.fallback_color}
                  onChange={(event) => updateDraft('fallback_color', event.target.value)}
                />
              </label>
            </div>
          </div>

          <div className="interface-settings-panel__head interface-settings-panel__head--compact">
            <div>
              <span><SlidersHorizontal size={16} /> 预览调整</span>
              <p>调整焦点、缩放和画面质感。</p>
            </div>
          </div>

          <div className="interface-settings-slider-grid">
            {sliderDefinitions.map((definition) => (
              <SliderField
                key={definition.key}
                definition={definition}
                value={Number(draft[definition.key])}
                onChange={(value) => updateDraft(definition.key, value)}
              />
            ))}
          </div>
        </section>

        <section className="interface-settings-preview-shell" aria-label="登录页预览">
          <div className="interface-settings-preview-shell__head">
            <span><Eye size={15} /> 登录页预览</span>
            <strong>{draft.fit === 'cover' ? '铺满画布' : '完整显示'}</strong>
          </div>
          <div className="interface-settings-preview auth-page">
            <div className="interface-settings-preview__dynamic" aria-hidden="true">
              <div className="interface-settings-preview__grid" />
              <div className="interface-settings-preview__hub">
                <span>AI</span>
                <i />
                <i />
                <i />
              </div>
              <div className="interface-settings-preview__panel interface-settings-preview__panel--one" />
              <div className="interface-settings-preview__panel interface-settings-preview__panel--two" />
            </div>
            <div className="interface-settings-preview__content">
              <header className="interface-settings-preview__nav">
                <span>智课未来</span>
                <div><b>登录</b><em>创建账号</em></div>
              </header>
              <div className="interface-settings-preview__body">
                <div>
                  <span className="interface-settings-preview__eyebrow">私有化 · 可信问答 · 学练评闭环</span>
                  <h2 className="auth-display">私有化 AI 学伴，<em>懂课程，会进化。</em></h2>
                  <p>本地 AI、混合检索、多智能体编排和学情画像串成可信闭环，覆盖学习、教学与管理。</p>
                </div>
                <aside>
                  <span>账号入口</span>
                  <strong>登录智课未来</strong>
                  <i />
                  <i />
                  <button type="button">登录工作台</button>
                </aside>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AdminPageShell>
  );
}
