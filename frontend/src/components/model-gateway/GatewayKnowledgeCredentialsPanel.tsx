import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Edit3,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { api } from '../../api/endpoints';
import { getApiErrorMessage } from '../../api/client';
import {
  chatdocTestToSnapshot,
  ConnectionTestResultPanel,
  EditorActionFeedbackPanel,
  type ConnectionTestSnapshot,
  type EditorActionFeedback,
} from './ConnectionTestResultPanel';
import { knowledgeIntegrationCopy as kb } from '../../config/knowledgeIntegration';
import { useConfirm } from '../../context/ConfirmContext';
import {
  buildKnowledgePickerTemplates,
  buildTemplateEditorConfig,
  createEmptyGenericRagFormValues,
  defaultCredentialValues,
  findRagTemplate,
  GENERIC_RAG_TEMPLATE_KEY,
  generateKnowledgeInstanceKey,
  getBundledRagIntegrationTemplates,
  bundledRagIntegrationTemplatesQueryData,
  isGenericRagTemplate,
  loadRagIntegrationTemplates,
  RAG_TEMPLATE_PICK_PLACEHOLDER,
  resolveGenericRagTemplate,
  resolveTemplateApiBaseUrl,
  shouldShowPresetTemplateApiBaseUrl,
} from '../../data/ragIntegrationTemplates';
import { ChatdocVendorQuotaSection } from './ChatdocVendorQuotaSection';
import { CustomRagKnowledgeFields } from './CustomRagKnowledgeFields';
import { ProviderIconBadge, ProviderIconPicker } from './ProviderIconPicker';
import { RagTemplateCredentialBlock, RagTemplateLockedSummary } from './RagTemplateCredentialBlock';
import { formatDateTimeZh } from '../../utils/formatDateTime';
import {
  clearKnowledgeDraft,
  loadKnowledgeDraft,
  saveKnowledgeDraft,
} from '../../utils/gatewayPageDraft';
import { formatValidationNotice, validateRagCredentialForm } from '../../utils/providerFormValidation';
import { ErrorState, LoadingState } from '../shared/StateBlock';
import { InfoDialog } from '../shared/InfoDialog';
import type { ToastTone } from '../shared/WorkspaceToast';
import type { ChatdocConfigView, RagCredentialField, RagIntegrationTemplate } from '../../types';
import {
  adminCredentialsSaved,
  buildSavePayload,
  canDeleteKnowledgeConfig,
  cardHealthStatus,
  matchesKnowledgeFilters,
  mapConfigToForm,
  resolveKnowledgeIconFile,
  shouldShowChatdocVendorQuota,
  sourceLabel,
  stripChatdocConfigPayload,
  type KnowledgeFilters,
  type KnowledgeSaveArgs,
  type KnowledgeSavePayload,
} from './gatewayKnowledgeCredentialsUtils';

export type GatewayKnowledgeCredentialsPanelProps = {
  enabled?: boolean;
  /** 顶部悬浮 Toast（网关页） */
  onToast?: (message: string, tone?: ToastTone) => void;
  /** embedded 等无 Toast 容器时回退 */
  onSaved?: (message: string) => void;
  /** gateway：网关页签（工具栏 + 卡片 + 侧滑编辑）；embedded：抽屉内嵌表单 */
  variant?: 'gateway' | 'embedded';
};

function CredentialFieldInput({
  field,
  value,
  secretPlaceholder,
  onChange,
  help,
}: {
  field: RagCredentialField;
  value: string;
  secretPlaceholder?: string;
  onChange: (next: string) => void;
  help?: { title: string; description: ReactNode };
}): JSX.Element {
  const [helpOpen, setHelpOpen] = useState(false);
  const inputType = field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text';
  const label = field.key === 'wiki_filter_score' ? kb.wikiFilterScoreLabel : field.label;

  return (
    <>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1.5 font-medium text-slate-700">
          {label}
          {help && (
            <button
              type="button"
              className="inline-flex rounded-full p-0.5 text-slate-400 transition hover:bg-slate-100 hover:text-primary"
              aria-label={`查看${label}说明`}
              onClick={() => setHelpOpen(true)}
            >
              <CircleHelp size={15} />
            </button>
          )}
        </span>
        <input
          className="input h-10"
          type={inputType}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          step={field.type === 'number' ? 0.01 : undefined}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.type === 'password' ? secretPlaceholder ?? field.placeholder ?? undefined : field.placeholder ?? undefined}
        />
      </label>
      {help && (
        <InfoDialog
          open={helpOpen}
          title={help.title}
          description={help.description}
          onClose={() => setHelpOpen(false)}
        />
      )}
    </>
  );
}

function wikiFilterScoreHelpContent(): JSX.Element {
  return (
    <>
      <p>{kb.wikiFilterScoreHelpIntro}</p>
      <ul className="list-disc space-y-1 pl-5">
        <li>{kb.wikiFilterScoreHelpTuneHigher}</li>
        <li>{kb.wikiFilterScoreHelpTuneLower}</li>
      </ul>
      <p>{kb.wikiFilterScoreHelpDefault}</p>
      <p className="text-xs text-slate-500">{kb.wikiFilterScoreHelpScope}</p>
    </>
  );
}

function KnowledgeIntegrationToolbar({
  total,
  visible,
  filters,
  onFiltersChange,
  onCheckAll,
  checking,
  onAdd,
}: {
  total: number;
  visible: number;
  filters: KnowledgeFilters;
  onFiltersChange: (filters: KnowledgeFilters) => void;
  onCheckAll: () => void;
  checking: boolean;
  onAdd: () => void;
}): JSX.Element {
  return (
    <div className="mb-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">知识向量化 / 云端 RAG</h2>
          <div className="mt-0.5 text-xs text-slate-500">显示 {visible} / {total} 个供应商</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary h-9 gap-2" type="button" disabled={checking} onClick={onCheckAll}>
            <Activity size={15} />
            检查全部
          </button>
          <button className="btn-primary h-9 gap-2" type="button" onClick={onAdd}>
            <Plus size={16} />
            新增供应商
          </button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-[minmax(220px,1fr)_180px_auto]">
        <label className="relative block">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="input h-9 w-full pl-9"
            placeholder="搜索供应商、模型或协议"
            value={filters.query}
            onChange={(event) => onFiltersChange({ ...filters, query: event.target.value })}
          />
        </label>
        <select
          className="input h-9 w-full"
          value={filters.status}
          onChange={(event) => onFiltersChange({ ...filters, status: event.target.value })}
        >
          <option value="all">全部状态</option>
          <option value="active">当前启用</option>
          <option value="configured">已配置</option>
          <option value="unconfigured">未配置</option>
          <option value="passed">测试通过</option>
          <option value="failed">测试失败</option>
          <option value="abnormal">仅异常/未配置</option>
        </select>
        <button
          type="button"
          className={`btn-secondary h-9 px-3 ${filters.status === 'abnormal' ? 'border-amber-300 bg-amber-50 text-amber-700' : ''}`}
          onClick={() => onFiltersChange({ ...filters, status: filters.status === 'abnormal' ? 'all' : 'abnormal' })}
        >
          <AlertTriangle size={15} />
          仅异常
        </button>
      </div>
    </div>
  );
}

function KnowledgeIntegrationCardGrid({
  items,
  activeKey,
  busyKey,
  onEdit,
  onTest,
  onDelete,
  deletePending,
}: {
  items: Array<{ instanceKey: string; template: RagIntegrationTemplate; config?: ChatdocConfigView }>;
  activeKey?: string;
  busyKey?: string;
  deletePending?: boolean;
  onEdit: (instanceKey: string) => void;
  onTest: (instanceKey: string) => void;
  onDelete: (instanceKey: string, label: string) => void | Promise<void>;
}): JSX.Element {
  if (items.length === 0) {
    return <div className="gateway-empty">暂无供应商</div>;
  }

  return (
    <div className="gateway-card-grid gateway-card-grid--list">
      {items.map(({ instanceKey, template, config }) => {
        const health = cardHealthStatus(config);
        const isActive = instanceKey === activeKey;
        const displayName = config?.template_label?.trim() || template.label;
        const iconFile = resolveKnowledgeIconFile(config, template);
        const websiteUrl = typeof template.meta_json?.website_url === 'string' ? template.meta_json.website_url : '';
        const comingSoonHint =
          typeof template.meta_json?.coming_soon_hint === 'string' ? template.meta_json.coming_soon_hint : '';

        return (
          <article
            key={instanceKey}
            className={`gateway-provider-card gateway-provider-card--compact${isActive ? ' gateway-provider-card--active' : ''}`}
          >
            <div className="gateway-provider-card__row">
              <div className="gateway-provider-card__main">
                <ProviderIconBadge displayName={displayName} iconFile={iconFile} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="gateway-provider-card__name">{displayName}</div>
                    {isActive && (
                      <span className="gateway-provider-card__active-tag">启用中</span>
                    )}
                  </div>
                  <div className="gateway-provider-card__meta">
                    {instanceKey}
                    {websiteUrl ? (
                      <>
                        {' · '}
                        <a className="text-primary hover:underline" href={websiteUrl} target="_blank" rel="noreferrer">
                          官网
                        </a>
                      </>
                    ) : null}
                    {!template.available ? ' · 即将支持' : ''}
                  </div>
                </div>
              </div>

              {shouldShowChatdocVendorQuota(template, config) && (
                <ChatdocVendorQuotaSection
                  integrationKey={instanceKey}
                  variant="card"
                  embeddedQuota={config?.vendor_quota ?? undefined}
                />
              )}

              <div className="gateway-provider-card__hover-actions" aria-label="供应商操作">
                <button
                  type="button"
                  className="gateway-provider-card__icon-btn"
                  title="编辑"
                  onClick={() => onEdit(instanceKey)}
                >
                  <Edit3 size={15} />
                </button>
                <button
                  type="button"
                  className="gateway-provider-card__icon-btn"
                  title="测试连接"
                  disabled={busyKey === instanceKey || !template.available}
                  onClick={() => onTest(instanceKey)}
                >
                  <Activity size={15} />
                </button>
                <button
                  type="button"
                  className="gateway-provider-card__icon-btn gateway-provider-card__icon-btn--danger"
                  title="删除"
                  disabled={deletePending}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onDelete(instanceKey, displayName);
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>

            {!template.available && comingSoonHint && (
              <p className="gateway-provider-card__hint">{comingSoonHint}</p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function KnowledgeCredentialsEditor({
  addMode,
  genericCustomDraft,
  instanceKey,
  templateKey,
  template,
  pickerTemplates,
  templatesLoading,
  templatesUsingBundledFallback,
  config,
  formValues,
  instanceDisplayName,
  isActive,
  setAsDefault,
  iconFile,
  iconItems,
  saving,
  testing,
  deleting,
  testResult,
  editorFeedback,
  onClose,
  onTemplateChange,
  onFieldChange,
  onInstanceDisplayNameChange,
  onActiveChange,
  onSetAsDefaultChange,
  onIconPreviewChange,
  onIconUpload,
  onSave,
  onTest,
  onDelete,
}: {
  addMode: boolean;
  genericCustomDraft: boolean;
  instanceKey?: string;
  templateKey: string;
  template?: RagIntegrationTemplate;
  pickerTemplates: RagIntegrationTemplate[];
  templatesLoading: boolean;
  templatesUsingBundledFallback: boolean;
  config?: ChatdocConfigView;
  formValues: Record<string, string>;
  instanceDisplayName?: string;
  isActive: boolean;
  setAsDefault: boolean;
  iconFile?: string;
  iconItems: import('../../utils/providerIcon').ModelProviderIconItem[];
  saving: boolean;
  testing: boolean;
  deleting: boolean;
  testResult?: ConnectionTestSnapshot | null;
  editorFeedback?: EditorActionFeedback | null;
  onClose: () => void;
  onTemplateChange: (key: string) => void;
  onFieldChange: (key: string, value: string) => void;
  onInstanceDisplayNameChange: (value: string) => void;
  onActiveChange: (value: boolean) => void;
  onSetAsDefaultChange: (value: boolean) => void;
  onIconPreviewChange: (filename: string) => void;
  onIconUpload: (file: File) => Promise<string>;
  onSave: () => void;
  onTest: () => void;
  onDelete: () => void;
}): JSX.Element {
  const websiteUrl =
    template && typeof template.meta_json?.website_url === 'string' ? template.meta_json.website_url : '';
  const comingSoonHint =
    template && typeof template.meta_json?.coming_soon_hint === 'string' ? template.meta_json.coming_soon_hint : '';
  const genericForm = template ? isGenericRagTemplate(template) : false;
  const bodyConfig = config ?? (template && genericCustomDraft
    ? buildTemplateEditorConfig(template.key, template)
    : undefined);
  const formReady = Boolean(template && bodyConfig);
  const awaitingTemplatePick = addMode && !genericCustomDraft && !templateKey;
  const selectValue = genericCustomDraft
    ? ''
    : templateKey || (awaitingTemplatePick ? RAG_TEMPLATE_PICK_PLACEHOLDER : '');
  const templateApiBaseUrl = template && bodyConfig ? resolveTemplateApiBaseUrl(template, formValues, bodyConfig) : '';

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/20 backdrop-blur-[1px]">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭配置面板" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">供应商配置</h2>
            <p className="mt-1 text-sm text-slate-500">
              {addMode
                ? (genericForm ? kb.knowledgeGenericBaseUrlHint : template ? kb.knowledgeEditorCredentialHint : kb.knowledgeEditorAddHint)
                : genericForm
                  ? kb.knowledgeGenericApiKeyHint
                  : kb.knowledgeEditorHint}
            </p>
          </div>
          <button type="button" className="btn-secondary h-8 px-3" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="flex-1 overflow-auto px-5 py-4">
          <label className="mb-4 block text-xs text-slate-500">
            {kb.credentialsProviderTemplateLabel}
            <select
              className="input mt-1 w-full"
              value={selectValue}
              disabled={templatesLoading || !addMode}
              onChange={(event) => onTemplateChange(event.target.value)}
            >
              <>
                <option value={RAG_TEMPLATE_PICK_PLACEHOLDER} disabled>
                  {templatesLoading ? '加载模板中…' : kb.credentialsProviderTemplatePlaceholder}
                </option>
                {pickerTemplates.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                    {!item.available ? ' · 即将支持' : ''}
                  </option>
                ))}
                <option value="">{kb.knowledgeCustomTemplatePlaceholder}</option>
              </>
            </select>
            {templatesUsingBundledFallback && (
              <p className="mt-1 text-[11px] text-amber-700">{kb.credentialsTemplateBundledFallback}</p>
            )}
          </label>

          {!formReady && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
              {awaitingTemplatePick
                ? kb.knowledgeEditorPickTemplateHint
                : templatesLoading
                  ? '正在加载接入模板…'
                  : '当前模板无效或未加载，请重新选择预置模板。'}
            </div>
          )}

          {formReady && template && bodyConfig && (
          <>
          {genericForm ? (
            <CustomRagKnowledgeFields
              displayName={instanceDisplayName ?? ''}
              remarks={formValues.remarks ?? ''}
              websiteUrl={formValues.website_url ?? ''}
              iconFile={iconFile}
              iconItems={iconItems}
              onDisplayNameChange={onInstanceDisplayNameChange}
              onRemarksChange={(value) => onFieldChange('remarks', value)}
              onWebsiteChange={(value) => onFieldChange('website_url', value)}
              onIconChange={onIconPreviewChange}
              onIconUpload={onIconUpload}
            />
          ) : (
            <div className="mb-5 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <ProviderIconPicker
                displayName={addMode ? (instanceDisplayName || template.label) : template.label}
                iconFile={iconFile}
                icons={iconItems}
                onIconChange={onIconPreviewChange}
                onUpload={onIconUpload}
              />
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="text-xs text-slate-500 md:col-span-2">
                  供应商名称
                  {addMode ? (
                    <input
                      className="input mt-1 w-full"
                      value={instanceDisplayName || template.label}
                      onChange={(event) => onInstanceDisplayNameChange(event.target.value)}
                      placeholder={template.label}
                    />
                  ) : (
                    <input className="input mt-1 w-full bg-slate-50" value={template.label} readOnly tabIndex={-1} />
                  )}
                </label>
                {shouldShowPresetTemplateApiBaseUrl(template) && (
                  <label className="md:col-span-2 text-xs text-slate-500">
                    API 请求地址
                    {addMode ? (
                      <input
                        className="input mt-1 w-full"
                        value={formValues.base_url ?? templateApiBaseUrl ?? ''}
                        onChange={(event) => onFieldChange('base_url', event.target.value)}
                        placeholder={templateApiBaseUrl || ''}
                      />
                    ) : (
                      <input
                        className="input mt-1 w-full bg-slate-50 font-mono text-xs"
                        value={templateApiBaseUrl || '—'}
                        readOnly
                        tabIndex={-1}
                      />
                    )}
                  </label>
                )}
                {websiteUrl && (
                  <label className="md:col-span-2 text-xs text-slate-500">
                    官网地址
                    {addMode ? (
                      <input
                        className="input mt-1 w-full"
                        value={formValues.website_url ?? websiteUrl}
                        onChange={(event) => onFieldChange('website_url', event.target.value)}
                        placeholder={websiteUrl}
                      />
                    ) : (
                      <input className="input mt-1 w-full bg-slate-50" value={websiteUrl} readOnly tabIndex={-1} />
                    )}
                  </label>
                )}
                {template.docs_url && (
                  <label className="md:col-span-2 text-xs text-slate-500">
                    接入文档
                    <input className="input mt-1 w-full bg-slate-50 text-xs" value={template.docs_url} readOnly tabIndex={-1} />
                  </label>
                )}
              </div>
              {websiteUrl && (
                <p className="mt-2 text-xs text-slate-500">
                  协议说明与错误码以
                  <a className="mx-1 text-primary hover:underline" href={websiteUrl} target="_blank" rel="noreferrer">
                    官方文档
                  </a>
                  为准；{kb.knowledgeEditorTroubleshootHint}
                </p>
              )}
            </div>
          )}

          <RagTemplateCredentialBlock
            template={template}
            config={bodyConfig}
            formValues={formValues}
            onFieldChange={onFieldChange}
            wikiFilterScoreHelp={wikiFilterScoreHelpContent()}
          />

          <div className="mb-4 flex flex-wrap gap-4 text-sm">
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={isActive} onChange={(event) => onActiveChange(event.target.checked)} />
              启用
            </label>
            <label className="inline-flex items-center gap-2">
              <input type="checkbox" checked={setAsDefault} onChange={(event) => onSetAsDefaultChange(event.target.checked)} />
              设为默认
            </label>
          </div>

          <RagTemplateLockedSummary template={template} config={bodyConfig} formValues={formValues} />

          {!addMode && instanceKey && !awaitingTemplatePick && shouldShowChatdocVendorQuota(template, bodyConfig) && (
            <ChatdocVendorQuotaSection
              integrationKey={instanceKey}
              variant="editor"
            />
          )}

          {!template.available && comingSoonHint && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
              {comingSoonHint}
            </div>
          )}
          </>
          )}
        </div>

        <div className="border-t border-slate-200 px-5 py-4">
          <EditorActionFeedbackPanel feedback={editorFeedback} />
          <ConnectionTestResultPanel loading={testing} result={testResult} />
          <div className="flex justify-end gap-2">
            {!addMode && canDeleteKnowledgeConfig(config) && (
              <button
                type="button"
                className="btn-secondary mr-auto gap-2 text-red-600"
                disabled={deleting}
                onClick={onDelete}
              >
                <Trash2 size={16} />
                删除
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={onClose}>
              取消
            </button>
            <button
              type="button"
              className="btn-secondary gap-2"
              disabled={testing}
              title="使用当前表单中的凭证测试连通性（无需先保存）"
              onClick={onTest}
            >
              <Activity size={16} />
              {testing ? '测试中…' : '测试连接'}
            </button>
            <button
              type="button"
              className="btn-primary gap-2"
              disabled={saving || (!templateKey && !genericCustomDraft) || !template}
              onClick={onSave}
            >
              <Save size={16} />
              保存配置
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function EmbeddedKnowledgeForm({
  templates,
  templatesUsingBundledFallback,
  templatesLoading,
  selectedTemplateKey,
  onTemplateChange,
  data,
  activeTemplate,
  formValues,
  isActive,
  onFieldChange,
  onActiveChange,
  onSave,
  onTest,
  saving,
  testing,
}: {
  templates: RagIntegrationTemplate[];
  templatesUsingBundledFallback: boolean;
  templatesLoading: boolean;
  selectedTemplateKey: string;
  onTemplateChange: (key: string) => void;
  data: ChatdocConfigView;
  activeTemplate: RagIntegrationTemplate;
  formValues: Record<string, string>;
  instanceDisplayName?: string;
  isActive: boolean;
  onFieldChange: (key: string, value: string) => void;
  onActiveChange: (value: boolean) => void;
  onSave: () => void;
  onTest: () => void;
  saving: boolean;
  testing: boolean;
}): JSX.Element {
  const configured = adminCredentialsSaved(data);
  const testPassed = data.last_test_status === 'passed';
  const isActiveTemplate = data.active_integration_key === selectedTemplateKey;
  const comingSoonHint =
    typeof activeTemplate.meta_json?.coming_soon_hint === 'string' ? activeTemplate.meta_json.coming_soon_hint : '';
  const iconFile = typeof activeTemplate.meta_json?.icon_file === 'string' ? activeTemplate.meta_json.icon_file : null;

  return (
    <div className="max-w-3xl">
      {templates.length > 0 && (
        <label className="mb-4 block text-sm">
          <span className="font-medium text-slate-700">{kb.credentialsTemplateLabel}</span>
          <select
            className="input mt-1 h-10 w-full"
            value={selectedTemplateKey}
            disabled={templatesLoading}
            onChange={(event) => onTemplateChange(event.target.value)}
          >
            <option value="">{templatesLoading ? '加载模板中…' : kb.credentialsTemplatePlaceholder}</option>
            {templates.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
                {!item.available ? '（即将支持）' : ''}
              </option>
            ))}
          </select>
          {templatesUsingBundledFallback && (
            <p className="mt-1 text-[11px] text-amber-700">{kb.credentialsTemplateBundledFallback}</p>
          )}
        </label>
      )}

      <div className="space-y-5">
        <div className={`rounded-lg border p-4 ${configured ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
          <div className="flex items-center gap-2 text-sm font-semibold">
            {configured ? <CheckCircle2 className="text-emerald-600" size={18} /> : <ShieldAlert className="text-amber-600" size={18} />}
            {configured ? '凭证已就绪' : '凭证未就绪'}
          </div>
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-600">
            <ProviderIconBadge displayName={activeTemplate.label} iconFile={iconFile} size="sm" />
            <span>
              当前模板：{activeTemplate.label}
              {isActiveTemplate ? '（已启用）' : '（未启用）'}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            来源：{sourceLabel[data.credential_source] ?? data.credential_source}
            <br />
            RAG_BACKEND：{data.rag_backend}
          </p>
        </div>

        {!activeTemplate.available && comingSoonHint && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
            {comingSoonHint}
          </div>
        )}

        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <KeyRound size={16} className="text-primary" />
            凭证配置
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {activeTemplate.credential_fields.map((field) => (
              <CredentialFieldInput
                key={field.key}
                field={field}
                value={formValues[field.key] ?? ''}
                secretPlaceholder={
                  field.type === 'password' && data.has_stored_secret
                    ? `已保存 ${data.api_secret_masked ?? ''}，留空不修改`
                    : field.placeholder ?? undefined
                }
                help={
                  field.key === 'wiki_filter_score'
                    ? { title: kb.wikiFilterScoreHelpTitle, description: wikiFilterScoreHelpContent() }
                    : undefined
                }
                onChange={(next) => onFieldChange(field.key, next)}
              />
            ))}
            <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-700 sm:col-span-2">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0"
                checked={isActive}
                onChange={(event) => onActiveChange(event.target.checked)}
              />
              <span>
                <span className="font-medium text-slate-800">{kb.useSavedCredentialsLabel}</span>
                <span className="mt-0.5 block text-xs font-normal leading-5 text-slate-500">{kb.useSavedCredentialsHint}</span>
              </span>
            </label>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" className="btn-primary h-10 gap-2 px-4" disabled={saving} onClick={onSave}>
              {saving ? <Loader2 className="animate-spin" size={15} /> : <Save size={15} />}
              保存
            </button>
            <button
              type="button"
              className="btn-secondary h-10 gap-2 px-4"
              disabled={testing || !activeTemplate.available}
              onClick={onTest}
            >
              {testing ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
              测试连接
            </button>
          </div>
        </section>

        {data.last_test_status && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
            <div className="font-semibold text-slate-950">最近测试</div>
            <div className={`mt-1 ${testPassed ? 'text-emerald-700' : 'text-red-600'}`}>
              {testPassed ? '通过' : data.last_test_status === 'failed' ? '失败' : data.last_test_status}
            </div>
            {data.last_test_message && <p className="mt-2 text-xs leading-5 text-slate-600">{data.last_test_message}</p>}
            {data.last_tested_at && (
              <p className="mt-1 text-xs text-slate-500">测试时间：{formatDateTimeZh(data.last_tested_at)}</p>
            )}
          </div>
        )}

        <p className="text-xs leading-5 text-slate-500">
          {data.env_fallback_hint || activeTemplate.env_fallback_hint}{' '}
          <a
            className="text-primary hover:underline"
            href={data.docs_url ?? activeTemplate.docs_url ?? '#'}
            target="_blank"
            rel="noreferrer"
          >
            {kb.credentialsApiDocLabel}
          </a>
        </p>
      </div>
    </div>
  );
}

export function GatewayKnowledgeCredentialsPanel({
  enabled = true,
  onToast,
  onSaved,
  variant = 'gateway',
}: GatewayKnowledgeCredentialsPanelProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const [selectedTemplateKey, setSelectedTemplateKey] = useState('');
  const [editingTemplateKey, setEditingTemplateKey] = useState<string | null>(null);
  /** 新增模式下选中的预置模板 key（与实例 integration_key 分离） */
  const [selectedPresetKey, setSelectedPresetKey] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [isActive, setIsActive] = useState(true);
  const [filters, setFilters] = useState<KnowledgeFilters>({ query: '', status: 'all' });
  const [busyTestKey, setBusyTestKey] = useState<string | undefined>();
  const [editorTestResult, setEditorTestResult] = useState<ConnectionTestSnapshot | null>(null);
  const [editorFeedback, setEditorFeedback] = useState<EditorActionFeedback | null>(null);
  const [setAsDefault, setSetAsDefault] = useState(true);
  const confirmDialog = useConfirm();
  const [editorIconFile, setEditorIconFile] = useState<string | undefined>();
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [genericCustomDraft, setGenericCustomDraft] = useState(false);
  const [instanceDisplayName, setInstanceDisplayName] = useState('');
  const [draftHydrated, setDraftHydrated] = useState(variant !== 'gateway');
  const formSyncedRef = useRef(false);
  const saveFromAddModeRef = useRef(false);
  const enabledPrevRef = useRef(enabled);
  const queryAlwaysOn = variant === 'gateway';

  useEffect(() => {
    if (variant !== 'gateway' || draftHydrated) return;
    const draft = loadKnowledgeDraft();
    if (!draft) {
      setDraftHydrated(true);
      return;
    }
    setIsAddingNew(draft.isAddingNew);
    setGenericCustomDraft(draft.genericCustomDraft);
    setEditingTemplateKey(draft.editingTemplateKey);
    setFormValues(draft.formValues);
    setInstanceDisplayName(draft.instanceDisplayName);
    setIsActive(draft.isActive);
    setSetAsDefault(draft.setAsDefault);
    setEditorIconFile(draft.editorIconFile);
    setDraftHydrated(true);
  }, [draftHydrated, variant]);

  const iconsQuery = useQuery({
    queryKey: ['model-provider-icons', 'knowledge-editor'],
    queryFn: () => api.modelProviderIcons(),
    enabled: enabled && variant === 'gateway' && (isAddingNew || Boolean(editingTemplateKey)),
  });
  const iconItems = iconsQuery.data?.items ?? [];

  const templatesQuery = useQuery({
    queryKey: ['rag-integration-templates'],
    queryFn: () => loadRagIntegrationTemplates(),
    enabled: queryAlwaysOn || enabled,
    staleTime: 60_000,
    placeholderData: bundledRagIntegrationTemplatesQueryData(),
  });

  const templates = templatesQuery.data?.items ?? getBundledRagIntegrationTemplates();
  const templatesUsingBundledFallback = templatesQuery.data?.source === 'bundled';

  const summaryQuery = useQuery({
    queryKey: ['chatdoc-config', 'summary'],
    queryFn: () => api.chatdocConfig(),
    enabled: enabled && variant === 'embedded',
    staleTime: 30_000,
  });

  const instancesQuery = useQuery({
    queryKey: ['chatdoc-config-instances'],
    queryFn: () => api.listChatdocConfigInstances(),
    enabled: queryAlwaysOn || (enabled && queryAlwaysOn),
    staleTime: 0,
    refetchOnMount: 'always',
    retry: 1,
  });

  useEffect(() => {
    if (variant !== 'gateway') return;
    const wasEnabled = enabledPrevRef.current;
    enabledPrevRef.current = enabled;
    if (!enabled || wasEnabled) return;
    void queryClient.invalidateQueries({ queryKey: ['chatdoc-config-instances'] });
    void queryClient.refetchQueries({ queryKey: ['chatdoc-config-instances'] });
  }, [enabled, queryClient, variant]);

  const instanceItems = useMemo(() => {
    const items = instancesQuery.data?.items ?? [];
    return items
      .map((config) => {
        const instanceKey = config.integration_key;
        const presetKey = config.template_key ?? config.integration_key;
        const presetTemplate = findRagTemplate(templates, presetKey);
        const template: RagIntegrationTemplate = presetTemplate ?? {
          key: presetKey,
          label: config.template_label ?? presetKey,
          rag_backend: config.rag_backend,
          available: config.template_available ?? false,
          credential_fields: [],
          env_prefix: '',
          env_fallback_hint: config.env_fallback_hint ?? '',
          docs_url: config.docs_url ?? null,
        };
        return { instanceKey, presetKey, template, config };
      });
  }, [instancesQuery.data?.items, templates]);

  const pickerTemplates = useMemo(
    () => buildKnowledgePickerTemplates(
      templates,
      genericCustomDraft ? null : (isAddingNew ? selectedPresetKey : null),
    ),
    [templates, isAddingNew, selectedPresetKey, genericCustomDraft],
  );

  const configByKey = useMemo(() => {
    const map = new Map<string, ChatdocConfigView>();
    for (const { instanceKey, config } of instanceItems) {
      map.set(instanceKey, config);
    }
    return map;
  }, [instanceItems]);

  const activeKey =
    instancesQuery.data?.active_integration_key
    ?? summaryQuery.data?.active_integration_key
    ?? instanceItems[0]?.instanceKey;

  const embeddedConfigQuery = useQuery({
    queryKey: ['chatdoc-config', selectedTemplateKey || 'active'],
    queryFn: () => api.chatdocConfig(selectedTemplateKey || undefined),
    enabled: enabled && variant === 'embedded',
  });

  const editingInstanceKey = isAddingNew ? null : editingTemplateKey;

  const effectivePresetKey = genericCustomDraft
    ? GENERIC_RAG_TEMPLATE_KEY
    : (isAddingNew ? selectedPresetKey : null)
      ?? (editingInstanceKey ? configByKey.get(editingInstanceKey)?.template_key : null)
      ?? selectedPresetKey;

  const editorConfigQuery = useQuery({
    queryKey: ['chatdoc-config', 'editor', editingInstanceKey],
    queryFn: () => api.chatdocConfig(editingInstanceKey!),
    enabled:
      enabled
      && variant === 'gateway'
      && Boolean(editingInstanceKey)
      && !genericCustomDraft,
  });

  const activeTemplate = useMemo(
    () => findRagTemplate(
      templates,
      selectedTemplateKey || embeddedConfigQuery.data?.template_key || embeddedConfigQuery.data?.integration_key,
    ),
    [templates, selectedTemplateKey, embeddedConfigQuery.data?.integration_key, embeddedConfigQuery.data?.template_key],
  );

  const editingTemplate = useMemo(() => {
    if (genericCustomDraft) return resolveGenericRagTemplate(templates);
    return findRagTemplate(templates, effectivePresetKey);
  }, [templates, effectivePresetKey, genericCustomDraft]);

  const editingConfig = useMemo(() => {
    if (!effectivePresetKey || !editingTemplate) return undefined;
    const saved = genericCustomDraft
      ? undefined
      : (
        editorConfigQuery.data
        ?? (editingInstanceKey
          ? queryClient.getQueryData<ChatdocConfigView>(['chatdoc-config', 'editor', editingInstanceKey])
          : undefined)
        ?? (editingInstanceKey ? configByKey.get(editingInstanceKey) : undefined)
      );
    const draftKey = editingInstanceKey ?? effectivePresetKey;
    return buildTemplateEditorConfig(draftKey, editingTemplate, activeKey, saved);
  }, [
    activeKey,
    configByKey,
    editingInstanceKey,
    editingTemplate,
    effectivePresetKey,
    editorConfigQuery.data,
    genericCustomDraft,
    queryClient,
  ]);

  useEffect(() => {
    if (!enabled || selectedTemplateKey || variant !== 'embedded') return;
    const key =
      embeddedConfigQuery.data?.template_key ??
      embeddedConfigQuery.data?.integration_key ??
      embeddedConfigQuery.data?.active_integration_key ??
      templates[0]?.key ??
      '';
    if (key) setSelectedTemplateKey(key);
  }, [enabled, embeddedConfigQuery.data, selectedTemplateKey, templates, variant]);

  const editorOpen = isAddingNew || Boolean(editingTemplateKey) || genericCustomDraft;

  const uploadIconMutation = useMutation({
    mutationFn: api.uploadModelProviderIcon,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['model-provider-icons'] });
    },
  });

  async function handleKnowledgeIconUpload(file: File): Promise<string> {
    const result = await uploadIconMutation.mutateAsync(file);
    return result.filename;
  }

  function notifyPage(message: string, tone: ToastTone = 'success'): void {
    if (onToast) {
      onToast(message, tone);
      return;
    }
    onSaved?.(message);
  }

  function notifyEditor(message: string, tone: EditorActionFeedback['tone'] = 'info'): void {
    setEditorFeedback({ message, tone });
  }

  function syncEditorFormFromConfig(data: ChatdocConfigView, template: RagIntegrationTemplate): void {
    const values = mapConfigToForm(data, template);
    for (const field of template.credential_fields) {
      if (field.type === 'password') values[field.key] = '';
    }
    setFormValues(values);
    setIsActive(data.is_active);
    setSetAsDefault(data.active_integration_key === data.integration_key);
    if (isGenericRagTemplate(template)) {
      setInstanceDisplayName(data.template_label ?? template.label);
    }
    setEditorIconFile(resolveKnowledgeIconFile(data, template));
    formSyncedRef.current = true;
  }

  useEffect(() => {
    if (variant !== 'gateway' || !draftHydrated) return;
    if (!editorOpen) {
      clearKnowledgeDraft();
      return;
    }
    saveKnowledgeDraft({
      isAddingNew,
      genericCustomDraft,
      editingTemplateKey,
      formValues,
      instanceDisplayName,
      isActive,
      setAsDefault,
      editorIconFile,
    });
  }, [
    draftHydrated,
    editorIconFile,
    editingTemplateKey,
    editorOpen,
    formValues,
    genericCustomDraft,
    instanceDisplayName,
    isActive,
    isAddingNew,
    setAsDefault,
    variant,
  ]);

  const saveMutation = useMutation({
    mutationFn: (args: KnowledgeSaveArgs) => {
      const template = findRagTemplate(templates, args.presetTemplateKey);
      const activate = args.setActive ?? args.setActiveSnapshot;
      return api.updateChatdocConfig(
        buildSavePayload(
          args.instanceKey,
          args.presetTemplateKey,
          template,
          args.formSnapshot,
          args.isActiveSnapshot,
          activate,
          args.iconFile,
          args.displayLabel,
        ),
      );
    },
    onSuccess: (result) => {
      const view = stripChatdocConfigPayload(result);
      queryClient.setQueryData(['chatdoc-config', result.integration_key], view);
      queryClient.setQueryData(['chatdoc-config', 'editor', result.integration_key], view);
      void queryClient.invalidateQueries({ queryKey: ['chatdoc-config'] });
      void queryClient.refetchQueries({ queryKey: ['chatdoc-config-instances'] });
      const label = result.template_label
        ?? findRagTemplate(templates, result.template_key)?.label
        ?? result.integration_key;
      const template = findRagTemplate(templates, result.template_key);
      const wasAdd = saveFromAddModeRef.current;
      saveFromAddModeRef.current = false;
      if (variant === 'gateway') {
        if (wasAdd) {
          closeEditor();
          notifyPage(`「${label}」${kb.knowledgeAddSaveSuccess}`);
        } else {
          setIsAddingNew(false);
          setGenericCustomDraft(false);
          setEditingTemplateKey(result.integration_key);
          if (template) syncEditorFormFromConfig(view, template);
          notifyEditor(`「${label}」${kb.knowledgeEditorSaveSuccess}`, 'success');
          setEditorTestResult(chatdocTestToSnapshot(view));
        }
      } else {
        setSelectedTemplateKey(result.integration_key);
        notifyPage(`「${label}」知识向量化凭证已保存。`);
      }
      clearKnowledgeDraft();
    },
    onError: (error) => {
      saveFromAddModeRef.current = false;
      const message = getApiErrorMessage(error, '保存失败，请检查填写项后重试。');
      if (variant === 'gateway') notifyEditor(message, 'error');
      else notifyPage(message, 'error');
    },
  });

  type KnowledgeTestArgs = { instanceKey: string; draft?: KnowledgeSavePayload };

  const testMutation = useMutation({
    mutationFn: (args: KnowledgeTestArgs) => (
      args.draft
        ? api.testChatdocConfigDraft(args.draft)
        : api.testChatdocConfig(args.instanceKey || undefined)
    ),
    onMutate: (args) => {
      setBusyTestKey(args.instanceKey);
      if (args.draft) setEditorFeedback(null);
    },
    onSettled: () => {
      setBusyTestKey(undefined);
    },
    onSuccess: (result, args) => {
      queryClient.setQueryData(['chatdoc-config', args.instanceKey], result);
      if (args.draft) {
        queryClient.setQueryData(['chatdoc-config', 'editor', args.instanceKey], result);
      }
      void queryClient.invalidateQueries({ queryKey: ['chatdoc-config'] });
      const snapshot = chatdocTestToSnapshot(result);
      const testingInEditor = Boolean(args.draft) && editorOpen && args.instanceKey === (editingInstanceKey ?? args.instanceKey);
      if (testingInEditor) {
        setEditorTestResult(
          snapshot ?? { status: 'failed', message: '测试完成，但响应中缺少 last_test_status / last_test_message。' },
        );
        return;
      }
      const detail = result.last_test_message?.trim();
      const label = result.template_label ?? findRagTemplate(templates, result.template_key)?.label ?? args.instanceKey;
      if (result.last_test_status === 'passed') {
        notifyPage(detail ? `「${label}」连接测试通过：${detail}` : `「${label}」连接测试通过。`, 'success');
      } else {
        notifyPage(detail ?? `「${label}」连接测试未通过。`, 'error');
      }
    },
    onError: (error, args) => {
      const message = getApiErrorMessage(error, '连接测试失败，未收到服务器详情。');
      const testingInEditor = Boolean(args?.draft) && editorOpen && args?.instanceKey === (editingInstanceKey ?? args.instanceKey);
      if (testingInEditor) {
        setEditorTestResult({ status: 'failed', message });
        return;
      }
      notifyPage(message, 'error');
    },
  });

  useEffect(() => {
    const data = variant === 'gateway' ? editorConfigQuery.data : embeddedConfigQuery.data;
    const template = variant === 'gateway' ? editingTemplate : activeTemplate;
    if (variant === 'gateway' && (isAddingNew || genericCustomDraft)) return;
    if (saveMutation.isPending) return;
    if (!data || !template) return;
    if (variant === 'gateway' && !enabled && formSyncedRef.current) return;
    const values = mapConfigToForm(data, template);
    for (const field of template.credential_fields) {
      if (field.type === 'password') values[field.key] = '';
    }
    setFormValues(values);
    setIsActive(data.is_active);
    if (variant === 'gateway') {
      setSetAsDefault(data.active_integration_key === (editingTemplateKey ?? data.integration_key));
      setEditorIconFile(resolveKnowledgeIconFile(data, template));
      if (isGenericRagTemplate(template)) {
        setInstanceDisplayName(data.template_label ?? template.label);
      }
      formSyncedRef.current = true;
    }
  }, [
    activeTemplate,
    editingTemplate,
    editingTemplateKey,
    embeddedConfigQuery.data,
    editorConfigQuery.data,
    enabled,
    genericCustomDraft,
    isAddingNew,
    saveMutation.isPending,
    variant,
  ]);

  const deleteMutation = useMutation({
    mutationFn: (templateKey: string) => api.deleteChatdocConfig(templateKey),
    onSuccess: (result, templateKey) => {
      const view = stripChatdocConfigPayload(result);
      queryClient.setQueryData(['chatdoc-config', templateKey], view);
      queryClient.setQueryData(['chatdoc-config', 'editor', templateKey], view);
      void queryClient.invalidateQueries({ queryKey: ['chatdoc-config-instances'] });
      void queryClient.refetchQueries({ queryKey: ['chatdoc-config'] });

      let message = '已删除该供应商的管理端凭证。';
      if (result.removed === false) {
        message = '移除失败或记录不存在。';
      } else if (view.credential_source === 'environment') {
        message = `${message} ${kb.credentialsDeletedWithEnv}`;
      }
      notifyPage(message);

      if (editingTemplateKey === templateKey) {
        setIsAddingNew(false);
        setEditingTemplateKey(null);
        setEditorIconFile(undefined);
      }
    },
    onError: (error) => {
      notifyPage(error instanceof Error ? error.message : '删除失败，请稍后重试。');
    },
  });

  function handleTemplateChange(nextKey: string): void {
    setSelectedTemplateKey(nextKey);
    const template = findRagTemplate(templates, nextKey);
    setFormValues(template ? defaultCredentialValues(template) : {});
  }

  function beginGenericCustomDraft(generic: RagIntegrationTemplate): void {
    setGenericCustomDraft(true);
    setSelectedPresetKey(null);
    setEditingTemplateKey(null);
    setFormValues(createEmptyGenericRagFormValues(generic));
    setInstanceDisplayName('');
    setIsActive(true);
    setSetAsDefault(true);
    setEditorIconFile(undefined);
  }

  function handlePickerTemplateChange(nextKey: string): void {
    if (isAddingNew) {
      if (nextKey === RAG_TEMPLATE_PICK_PLACEHOLDER) {
        setGenericCustomDraft(false);
        setSelectedPresetKey(null);
        setFormValues({});
        setInstanceDisplayName('');
        setEditorIconFile(undefined);
        return;
      }
      if (!nextKey) {
        const generic = resolveGenericRagTemplate(templates);
        if (!generic) {
          notifyEditor('通用模板未加载，请刷新页面。', 'error');
          return;
        }
        beginGenericCustomDraft(generic);
        return;
      }
      setGenericCustomDraft(false);
      setSelectedPresetKey(nextKey);
      const nextTemplate = findRagTemplate(templates, nextKey);
      if (nextTemplate) {
        setFormValues(defaultCredentialValues(nextTemplate));
        setIsActive(true);
        setSetAsDefault(true);
        setEditorIconFile(resolveKnowledgeIconFile(undefined, nextTemplate));
        setInstanceDisplayName('');
      }
      return;
    }
    if (!nextKey || !editingInstanceKey) return;
    notifyEditor('编辑已有实例时不可更换预置模板；请新建供应商以使用其他预置。', 'info');
  }

  function validateCurrentRagForm(templateKey: string, config?: ChatdocConfigView): string | null {
    if (!templateKey && !genericCustomDraft) {
      return kb.knowledgeEditorPickTemplateHint;
    }
    const template = findRagTemplate(templates, templateKey);
    if (!template) return '请先选择有效的预置供应商模板。';
    const errors = validateRagCredentialForm(template, formValues, config, {
      wikiFilterScoreLabel: kb.wikiFilterScoreLabel,
      displayName: instanceDisplayName,
    });
    return formatValidationNotice(errors);
  }

  async function handleEditorSave(): Promise<void> {
    const presetKey = effectivePresetKey;
    const template = presetKey ? findRagTemplate(templates, presetKey) : undefined;
    if (!presetKey || !template) {
      notifyEditor('请先选择预置供应商模板或通用云端 RAG。', 'error');
      return;
    }
    const instanceKey = isAddingNew
      ? generateKnowledgeInstanceKey(presetKey, instanceDisplayName)
      : (editingInstanceKey ?? '');
    if (!instanceKey) {
      notifyEditor('无法确定供应商实例，请关闭后重新打开编辑器。', 'error');
      return;
    }
    const config = configByKey.get(instanceKey) ?? editorConfigQuery.data;
    const error = validateCurrentRagForm(presetKey, config);
    if (error) {
      notifyEditor(error, 'error');
      return;
    }
    setEditorFeedback(null);
    saveFromAddModeRef.current = isAddingNew;
    const formSnapshot = { ...formValues };
    const displayLabel = (instanceDisplayName.trim() || undefined)
      ?? (isAddingNew ? template?.label : undefined);
    const saveArgs: KnowledgeSaveArgs = {
      instanceKey,
      presetTemplateKey: presetKey,
      displayLabel,
      formSnapshot,
      isActiveSnapshot: isActive,
      setActiveSnapshot: setAsDefault,
      iconFile: editorIconFile?.trim() || undefined,
    };
    try {
      setGenericCustomDraft(false);
      setSelectedPresetKey(null);
      setIsAddingNew(false);
      setEditingTemplateKey(instanceKey);
      await saveMutation.mutateAsync(saveArgs);
    } catch (error) {
      saveFromAddModeRef.current = false;
      notifyEditor(error instanceof Error ? error.message : '添加失败，请稍后重试。', 'error');
    }
  }

  async function handleEditorTest(): Promise<void> {
    const presetKey = effectivePresetKey;
    const template = presetKey ? findRagTemplate(templates, presetKey) : undefined;
    if (!presetKey || !template) {
      notifyEditor('请先选择预置供应商模板或通用云端 RAG。', 'error');
      return;
    }
    const instanceKey = isAddingNew
      ? generateKnowledgeInstanceKey(presetKey, instanceDisplayName)
      : (editingInstanceKey ?? '');
    if (!instanceKey) {
      notifyEditor('无法确定供应商实例。', 'error');
      return;
    }
    const config = configByKey.get(instanceKey) ?? editorConfigQuery.data;
    const error = validateCurrentRagForm(presetKey, config);
    if (error) {
      notifyEditor(error, 'error');
      return;
    }
    setEditorFeedback(null);
    const displayLabel = (instanceDisplayName.trim() || undefined)
      ?? (isAddingNew ? template?.label : undefined);
    testMutation.mutate({
      instanceKey,
      draft: buildSavePayload(
        instanceKey,
        presetKey,
        template,
        formValues,
        isActive,
        false,
        editorIconFile?.trim() || undefined,
        displayLabel,
      ),
    });
  }

  function closeEditor(): void {
    setIsAddingNew(false);
    setGenericCustomDraft(false);
    setSelectedPresetKey(null);
    setEditingTemplateKey(null);
    setInstanceDisplayName('');
    setEditorIconFile(undefined);
    setEditorTestResult(null);
    setEditorFeedback(null);
    formSyncedRef.current = false;
    clearKnowledgeDraft();
  }

  async function requestDelete(templateKey: string, label: string): Promise<void> {
    const ok = await confirmDialog({
      title: kb.credentialsDeleteTitle,
      tone: 'danger',
      confirmLabel: '确认删除',
      description: (
        <>
          <p>
            确认删除供应商「{label}」
            <span className="font-mono text-slate-500">（{templateKey}）</span>
            的管理端凭证？
          </p>
          <p className="mt-2 text-red-600">{kb.credentialsDeleteHint}</p>
        </>
      ),
    });
    if (!ok) return;

    deleteMutation.mutate(templateKey);
  }

  function openEditor(instanceKey: string): void {
    setIsAddingNew(false);
    setGenericCustomDraft(false);
    setSelectedPresetKey(null);
    setEditingTemplateKey(instanceKey);
    setEditorFeedback(null);
    formSyncedRef.current = false;
    void queryClient.invalidateQueries({ queryKey: ['chatdoc-config', 'editor', instanceKey] });
    void queryClient.fetchQuery({
      queryKey: ['chatdoc-config', 'editor', instanceKey],
      queryFn: () => api.chatdocConfig(instanceKey),
    });
    const data = configByKey.get(instanceKey);
    const presetKey = data?.template_key ?? instanceKey;
    const template = findRagTemplate(templates, presetKey);
    if (data && template) {
      const values = mapConfigToForm(data, template);
      for (const field of template.credential_fields) {
        if (field.type === 'password') values[field.key] = '';
      }
      setFormValues(values);
      setIsActive(data.is_active);
      setEditorIconFile(resolveKnowledgeIconFile(data, template));
    }
  }

  function runCheckAll(): void {
    const targets = instanceItems.filter((item) => item.template.available && adminCredentialsSaved(item.config));
    if (targets.length === 0) {
      notifyPage('暂无已配置且可测试的供应商。');
      return;
    }
    void (async () => {
      for (const item of targets) {
        await testMutation.mutateAsync({ instanceKey: item.instanceKey });
      }
    })();
  }

  function handleAddProvider(): void {
    if (templates.length === 0) {
      notifyPage('接入模板尚未加载，请稍后重试。', 'error');
      return;
    }
    setIsAddingNew(true);
    setEditorTestResult(null);
    setEditorFeedback(null);
    setGenericCustomDraft(false);
    setSelectedPresetKey(null);
    setEditingTemplateKey(null);
    setFormValues({});
    setInstanceDisplayName('');
    setIsActive(true);
    setSetAsDefault(true);
    setEditorIconFile(undefined);
  }

  const visibleTemplates = useMemo(
    () => instanceItems.filter((item) => matchesKnowledgeFilters(item.template, item.config, activeKey, filters)),
    [activeKey, filters, instanceItems],
  );

  useEffect(() => {
    if (variant !== 'gateway' || !editorOpen) return;
    setEditorTestResult(editingConfig ? chatdocTestToSnapshot(editingConfig) : null);
  }, [variant, editorOpen, editingInstanceKey, effectivePresetKey, editingConfig, editorConfigQuery.data]);

  if (variant === 'embedded' && !enabled) return null;

  const loadError =
    templatesQuery.isError
    || (variant === 'gateway' && instancesQuery.isError)
    || (variant === 'embedded' && embeddedConfigQuery.isError);

  if (variant === 'embedded') {
    return (
      <>
        {(templatesQuery.isLoading || embeddedConfigQuery.isLoading) && <LoadingState />}
        {embeddedConfigQuery.isError && <ErrorState label={kb.credentialsLoadError} />}
        {embeddedConfigQuery.data && activeTemplate && (
          <EmbeddedKnowledgeForm
            templates={templates}
            templatesUsingBundledFallback={templatesUsingBundledFallback}
            templatesLoading={templatesQuery.isLoading}
            selectedTemplateKey={selectedTemplateKey}
            onTemplateChange={handleTemplateChange}
            data={embeddedConfigQuery.data}
            activeTemplate={activeTemplate}
            formValues={formValues}
            isActive={isActive}
            onFieldChange={(key, value) => setFormValues((prev) => ({ ...prev, [key]: value }))}
            onActiveChange={setIsActive}
            onSave={() => {
              const data = embeddedConfigQuery.data!;
              const presetKey = data.template_key ?? data.integration_key;
              const error = validateCurrentRagForm(presetKey, data);
              if (error) {
                notifyPage(error);
                return;
              }
              saveMutation.mutate({
                instanceKey: data.integration_key,
                presetTemplateKey: presetKey,
                setActive: true,
                formSnapshot: { ...formValues },
                isActiveSnapshot: isActive,
                setActiveSnapshot: true,
              });
            }}
            onTest={() => {
              const data = embeddedConfigQuery.data!;
              const presetKey = data.template_key ?? data.integration_key;
              const error = validateCurrentRagForm(presetKey, data);
              if (error) {
                notifyPage(error);
                return;
              }
              testMutation.mutate({
                instanceKey: data.integration_key,
                draft: buildSavePayload(
                  data.integration_key,
                  presetKey,
                  activeTemplate,
                  formValues,
                  isActive,
                  false,
                  editorIconFile?.trim() || undefined,
                ),
              });
            }}
            saving={saveMutation.isPending}
            testing={testMutation.isPending}
          />
        )}
      </>
    );
  }

  return (
    <section>
      {loadError && (
        <div className="mb-3">
          <ErrorState
            label={
              instancesQuery.isError
                ? `${kb.credentialsLoadError}（若接口 404，请执行数据库迁移 0026 并重启后端）`
                : kb.credentialsLoadError
            }
          />
        </div>
      )}

      {!loadError && enabled && (
        <>
          <KnowledgeIntegrationToolbar
            total={instanceItems.length}
            visible={visibleTemplates.length}
            filters={filters}
            onFiltersChange={setFilters}
            onCheckAll={runCheckAll}
            checking={testMutation.isPending}
            onAdd={handleAddProvider}
          />
          {templatesUsingBundledFallback && (
            <p className="mb-3 text-[11px] text-amber-700">{kb.credentialsTemplateBundledFallback}</p>
          )}
          {visibleTemplates.length === 0 ? (
            <div className="gateway-empty">{kb.knowledgeInstancesEmpty}</div>
          ) : (
            <KnowledgeIntegrationCardGrid
              items={visibleTemplates}
              activeKey={activeKey}
              busyKey={busyTestKey}
              onEdit={openEditor}
              onTest={(key) => testMutation.mutate({ instanceKey: key })}
              onDelete={requestDelete}
              deletePending={deleteMutation.isPending}
            />
          )}
        </>
      )}

      {editorOpen && !isAddingNew && editingTemplateKey && editingTemplate && editorConfigQuery.isLoading && !editingConfig && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20 backdrop-blur-[1px]">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-lg">
            <LoadingState />
          </div>
        </div>
      )}

      {editorOpen && enabled && (
        <KnowledgeCredentialsEditor
          addMode={isAddingNew}
          genericCustomDraft={genericCustomDraft}
          instanceKey={editingInstanceKey || undefined}
          templateKey={
            isAddingNew
              ? (selectedPresetKey ?? '')
              : (editingConfig?.template_key ?? effectivePresetKey ?? '')
          }
          template={editingTemplate}
          pickerTemplates={pickerTemplates}
          templatesLoading={templatesQuery.isLoading}
          templatesUsingBundledFallback={templatesUsingBundledFallback}
          config={editingConfig}
          formValues={formValues}
          instanceDisplayName={instanceDisplayName}
          isActive={isActive}
          setAsDefault={setAsDefault}
          iconFile={editorIconFile}
          iconItems={iconItems}
          saving={saveMutation.isPending}
          onIconUpload={handleKnowledgeIconUpload}
          testing={testMutation.isPending && (isAddingNew || busyTestKey === editingInstanceKey)}
          deleting={deleteMutation.isPending}
          testResult={editorTestResult}
          editorFeedback={editorFeedback}
          onClose={closeEditor}
          onTemplateChange={handlePickerTemplateChange}
          onFieldChange={(key, value) => {
            setFormValues((prev) => ({ ...prev, [key]: value }));
          }}
          onInstanceDisplayNameChange={setInstanceDisplayName}
          onActiveChange={setIsActive}
          onSetAsDefaultChange={setSetAsDefault}
          onIconPreviewChange={setEditorIconFile}
          onSave={() => { void handleEditorSave(); }}
          onTest={() => { void handleEditorTest(); }}
          onDelete={() => {
            if (!editingTemplateKey || !editingTemplate) return;
            void requestDelete(editingTemplateKey, editingTemplate.label);
          }}
        />
      )}

    </section>
  );
}
