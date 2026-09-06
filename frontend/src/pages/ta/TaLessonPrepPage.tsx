import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Eye, Loader2, Pencil, Send, Sparkles, Trash2 } from 'lucide-react';
import { api } from '../../api/endpoints';
import {
  taDeleteLessonPlan, taDeleteLessonPlans, taGenerateLessonPlan, taListLessonPlans, taPublishLessonPlan,
  taUpdateLessonPlan, type TaLessonPlan,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { WorkspaceToast, type WorkspaceToastItem } from '../../components/shared/WorkspaceToast';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type GenerateForm = { course_id: string; chapter: string; title: string };
type EditForm = { title: string; chapter: string; outline: string };

type LessonPlanProcessStep = { step: string; content: string; duration: string };
type LessonPlanContent = {
  objectives: string[];
  key_points: string[];
  difficulties: string[];
  process: LessonPlanProcessStep[];
  homework: string;
  board: string;
};

/** 判断教案是否为结构化内容（AI 生成并解析成功的 JSON 教案）。 */
function isStructuredContent(plan: TaLessonPlan): plan is TaLessonPlan & { content: LessonPlanContent } {
  const c = plan.content as LessonPlanContent | null | undefined;
  return Boolean(c && Array.isArray(c.objectives) && c.objectives.length > 0);
}

/** 结构化教案 → 卡片摘要纯文本（目标 + 环节数）。 */
function planSummary(plan: TaLessonPlan): string {
  if (isStructuredContent(plan)) {
    const c = plan.content;
    const objective = c.objectives[0] ?? '';
    const processCount = c.process.length;
    const parts = [objective ? `教学目标：${objective}` : ''];
    if (processCount > 0) parts.push(`教学过程：${processCount} 个环节`);
    return parts.filter(Boolean).join('；') || '（结构化教案）';
  }
  return plan.outline ?? '（暂无内容）';
}

/** 结构化教案分组渲染（预览/详情用），无结构化内容时回退 Markdown 文本。 */
function StructuredPlanView({ plan }: { plan: TaLessonPlan }): JSX.Element {
  if (!isStructuredContent(plan)) {
    return <p className="whitespace-pre-wrap text-sm text-zinc-700">{plan.outline || '（暂无内容）'}</p>;
  }
  const c = plan.content;
  const renderList = (title: string, items: string[]): JSX.Element | null => {
    if (!items.length) return null;
    return (
      <div>
        <div className="text-xs font-medium text-zinc-500">{title}</div>
        <ul className="mt-1 space-y-1">
          {items.map((item, index) => <li key={index} className="text-sm text-zinc-700">· {item}</li>)}
        </ul>
      </div>
    );
  };
  return (
    <div className="space-y-4">
      {renderList('教学目标', c.objectives)}
      {renderList('教学重点', c.key_points)}
      {renderList('教学难点', c.difficulties)}
      <div>
        <div className="text-xs font-medium text-zinc-500">教学过程</div>
        <div className="mt-1 space-y-3">
          {c.process.map((step, index) => (
            <div key={index} className="rounded-md border border-zinc-100 bg-zinc-50 p-3">
              <div className="text-sm font-medium text-zinc-800">
                {index + 1}. {step.step}
                {step.duration ? <span className="ml-2 text-xs font-normal text-zinc-400">预计 {step.duration}</span> : null}
              </div>
              {step.content ? <p className="mt-1 text-sm text-zinc-600">{step.content}</p> : null}
            </div>
          ))}
          {c.process.length === 0 ? <p className="text-sm text-zinc-400">（暂无教学过程）</p> : null}
        </div>
      </div>
      {c.homework ? (
        <div>
          <div className="text-xs font-medium text-zinc-500">课后作业</div>
          <p className="mt-1 text-sm text-zinc-700">{c.homework}</p>
        </div>
      ) : null}
      {c.board ? (
        <div>
          <div className="text-xs font-medium text-zinc-500">板书设计</div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-700">{c.board}</p>
        </div>
      ) : null}
    </div>
  );
}

/** 教案编辑弹窗：AI 生成后弹出，展示并允许教师编辑教学重点/目标/难点/过程/作业/板书。 */
function LessonPlanEditorModal({ planId, initialTitle, initialContent, onClose, onSaved }: {
  planId: string;
  initialTitle: string;
  initialContent: LessonPlanContent;
  onClose: () => void;
  onSaved: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(initialTitle);
  const [content, setContent] = useState<LessonPlanContent>(initialContent);
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: () => taUpdateLessonPlan(planId, { title, content: content as unknown as Record<string, unknown> }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ta-lesson-plans'] });
      onSaved();
    },
    onError: (saveError) => setError((saveError as Error).message),
  });

  const editListItem = (field: 'objectives' | 'key_points' | 'difficulties') => (index: number, value: string): void => {
    setContent((prev) => ({ ...prev, [field]: prev[field].map((item, i) => (i === index ? value : item)) }));
  };
  const addListItem = (field: 'objectives' | 'key_points' | 'difficulties') => (): void => {
    setContent((prev) => ({ ...prev, [field]: [...prev[field], ''] }));
  };
  const removeListItem = (field: 'objectives' | 'key_points' | 'difficulties') => (index: number): void => {
    setContent((prev) => ({ ...prev, [field]: prev[field].filter((_, i) => i !== index) }));
  };
  const editStep = (index: number, key: 'step' | 'content' | 'duration', value: string): void => {
    setContent((prev) => ({ ...prev, process: prev.process.map((s, i) => (i === index ? { ...s, [key]: value } : s)) }));
  };
  const addStep = (): void => setContent((prev) => ({ ...prev, process: [...prev.process, { step: '', content: '', duration: '' }] }));
  const removeStep = (index: number): void => setContent((prev) => ({ ...prev, process: prev.process.filter((_, i) => i !== index) }));

  const listEditor = (label: string, field: 'objectives' | 'key_points' | 'difficulties'): JSX.Element => (
    <div>
      <div className="text-xs font-medium text-zinc-500">{label}</div>
      <div className="mt-1 space-y-1.5">
        {content[field].map((item, index) => (
          <div key={index} className="flex items-center gap-2">
            <input className={`${inputClass} flex-1`} value={item} placeholder={`${label} ${index + 1}`} onChange={(e) => editListItem(field)(index, e.target.value)} />
            <button type="button" className="shrink-0 text-xs text-red-500 hover:underline" onClick={() => removeListItem(field)(index)}>删除</button>
          </div>
        ))}
      </div>
      <button type="button" className="mt-1.5 text-xs text-blue-600 hover:underline" onClick={addListItem(field)}>+ 添加{label}</button>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-zinc-900">教案编辑</h3>
          <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={onClose}>✕</button>
        </div>
        <div className="mt-4 flex-1 space-y-4 overflow-auto pr-1">
          <label className="block text-xs text-zinc-500">
            教案标题
            <input className={`${inputClass} mt-1`} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>

          {/* 教学重点：核心编辑区，AI 生成后教师可增删改 */}
          <div className="rounded-md border border-amber-200 bg-amber-50/60 p-3">
            {listEditor('教学重点', 'key_points')}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {listEditor('教学目标', 'objectives')}
            {listEditor('教学难点', 'difficulties')}
          </div>

          <div>
            <div className="text-xs font-medium text-zinc-500">教学过程</div>
            <div className="mt-1 space-y-2">
              {content.process.map((step, index) => (
                <div key={index} className="rounded-md border border-zinc-100 bg-zinc-50 p-2">
                  <div className="flex items-center gap-2">
                    <input className={`${inputClass} flex-1`} placeholder="环节名" value={step.step} onChange={(e) => editStep(index, 'step', e.target.value)} />
                    <input className={`${inputClass} w-28`} placeholder="时长" value={step.duration} onChange={(e) => editStep(index, 'duration', e.target.value)} />
                    <button type="button" className="shrink-0 text-xs text-red-500 hover:underline" onClick={() => removeStep(index)}>删除</button>
                  </div>
                  <textarea className={`${inputClass} mt-1.5`} rows={2} placeholder="环节内容" value={step.content} onChange={(e) => editStep(index, 'content', e.target.value)} />
                </div>
              ))}
            </div>
            <button type="button" className="mt-1.5 text-xs text-blue-600 hover:underline" onClick={addStep}>+ 添加环节</button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-zinc-500">
              课后作业
              <textarea className={`${inputClass} mt-1`} rows={3} value={content.homework} onChange={(e) => setContent((prev) => ({ ...prev, homework: e.target.value }))} />
            </label>
            <label className="block text-xs text-zinc-500">
              板书设计
              <textarea className={`${inputClass} mt-1`} rows={3} value={content.board} onChange={(e) => setContent((prev) => ({ ...prev, board: e.target.value }))} />
            </label>
          </div>
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className={secondaryButtonClass} onClick={onClose}>取消</button>
          <button type="button" className={primaryButtonClass} disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            {saveMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 保存教案
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * 智能备课：AI 生成教案、编辑大纲并发布给学生端。
 */
export function TaLessonPrepPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateForm, setGenerateForm] = useState<GenerateForm>({ course_id: '', chapter: '', title: '' });
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [editing, setEditing] = useState<TaLessonPlan | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({ title: '', chapter: '', outline: '' });
  const [preview, setPreview] = useState<TaLessonPlan | null>(null);
  // 结构化教案编辑弹窗（AI 生成后自动弹出 / 列表「编辑」打开）
  const [editor, setEditor] = useState<{ planId: string; title: string; content: LessonPlanContent } | null>(null);
  // 教案多选（批量删除）与操作提示
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [toast, setToast] = useState<WorkspaceToastItem | null>(null);

  const plansQuery = useQuery({ queryKey: ['ta-lesson-plans'], queryFn: () => taListLessonPlans() });
  const coursesQuery = useQuery({
    queryKey: ['ta-lesson-courses'],
    queryFn: async () => {
      const data = await api.courses();
      return data.items;
    },
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['ta-lesson-plans'] });

  const generateMutation = useMutation({
    mutationFn: () => taGenerateLessonPlan({
      course_id: generateForm.course_id,
      chapter: generateForm.chapter,
      title: generateForm.title,
    }),
    onSuccess: (data) => {
      invalidate();
      setGenerateOpen(false);
      setGenerateError(null);
      // 生成成功后弹出教案编辑弹窗，教师可先校对/编辑教学重点再保存
      if (data.content && typeof data.content === 'object') {
        setEditor({ planId: data.id, title: data.title, content: data.content as LessonPlanContent });
      }
    },
    onError: (error) => setGenerateError((error as Error).message),
  });

  const publishMutation = useMutation({ mutationFn: (planId: string) => taPublishLessonPlan(planId), onSuccess: () => invalidate() });

  // 删除（单个/批量）：草稿与已发布教案均可删，删除后学生端同步不可见
  const deleteMutation = useMutation({
    mutationFn: (planId: string) => taDeleteLessonPlan(planId),
    onSuccess: () => {
      invalidate();
      setToast({ id: `ta-plan-delete-${Date.now()}`, message: '教案已删除', tone: 'success' });
    },
    onError: (error) => setToast({ id: `ta-plan-delete-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const batchDeleteMutation = useMutation({
    mutationFn: () => taDeleteLessonPlans(selectedIds),
    onSuccess: (result) => {
      invalidate();
      setSelectedIds([]);
      setToast({
        id: `ta-plan-batch-${Date.now()}`,
        message: result.message,
        tone: result.skipped.length > 0 && result.deleted === 0 ? 'error' : 'success',
      });
    },
    onError: (error) => setToast({ id: `ta-plan-batch-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const confirmDeletePlan = (plan: TaLessonPlan): void => {
    if (window.confirm(`确定删除教案「${plan.title}」吗？删除后学生端将同步不可见。`)) {
      deleteMutation.mutate(plan.id);
    }
  };

  const confirmBatchDelete = (): void => {
    if (selectedIds.length === 0) return;
    if (window.confirm(`确定删除选中的 ${selectedIds.length} 个教案吗？删除后无法恢复。`)) {
      batchDeleteMutation.mutate();
    }
  };

  const toggleSelect = (planId: string): void => {
    setSelectedIds((prev) => (prev.includes(planId) ? prev.filter((id) => id !== planId) : [...prev, planId]));
  };

  const plans = plansQuery.data ?? [];

  const saveMutation = useMutation({
    mutationFn: () => (editing ? taUpdateLessonPlan(editing.id, {
      title: editForm.title,
      chapter: editForm.chapter || null,
      outline: editForm.outline || null,
    }) : Promise.resolve({ id: '' })),
    onSuccess: () => { invalidate(); setEditing(null); },
  });

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="智能备课" subtitle="按课程与章节生成教案大纲，编辑确认后发布给学生端使用。" />

      <PageHeaderToolbar>
        <button
          type="button"
          className={primaryButtonClass}
          onClick={() => {
            setGenerateForm({ course_id: coursesQuery.data?.[0]?.id ?? '', chapter: '', title: '' });
            setGenerateError(null);
            setGenerateOpen(true);
          }}
        >
          <Sparkles size={15} /> AI 生成教案
        </button>
        <button type="button" className={secondaryButtonClass} onClick={() => plansQuery.refetch()}>
          <Loader2 size={15} className={plansQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
        {plans.length > 0 ? (
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => setSelectedIds(selectedIds.length === plans.length ? [] : plans.map((plan) => plan.id))}
          >
            {selectedIds.length === plans.length ? '取消全选' : '全选'}
          </button>
        ) : null}
        {selectedIds.length > 0 ? (
          <button
            type="button"
            className={`${secondaryButtonClass} border-red-200 text-red-600 hover:bg-red-50`}
            disabled={batchDeleteMutation.isPending}
            onClick={confirmBatchDelete}
          >
            {batchDeleteMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} 批量删除（{selectedIds.length}）
          </button>
        ) : null}
      </PageHeaderToolbar>

      {plansQuery.isLoading ? (
        <LoadingState label="正在加载教案列表..." />
      ) : plansQuery.isError ? (
        <ErrorState label={(plansQuery.error as Error)?.message || '教案列表加载失败'} />
      ) : (plansQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有教案，点击「AI 生成教案」开始备课。" />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {plans.map((plan) => (
            <div key={plan.id} className={`rounded-lg border bg-white p-5 ${selectedIds.includes(plan.id) ? 'border-blue-300 bg-blue-50/40' : 'border-zinc-200'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`选择教案 ${plan.title}`}
                    checked={selectedIds.includes(plan.id)}
                    onChange={() => toggleSelect(plan.id)}
                  />
                  <span className="flex h-8 w-8 items-center justify-center rounded-md bg-zinc-100 text-zinc-600"><BookOpen size={15} /></span>
                  <div>
                    <div className="text-sm font-semibold text-zinc-900">{plan.title}</div>
                    <div className="text-xs text-zinc-400">第 {plan.version} 版 · {formatBeijingDateTimeCompact(plan.updated_at ?? plan.created_at, '—')}</div>
                  </div>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-xs ${plan.is_published ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                  {plan.is_published ? '已发布' : '草稿'}
                </span>
              </div>
              {plan.chapter ? <div className="mt-3 text-xs text-zinc-500">章节：{plan.chapter}</div> : null}
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-zinc-600">{planSummary(plan)}</p>
              <div className="mt-4 flex items-center gap-2">
                <button type="button" className={secondaryButtonClass} onClick={() => setPreview(plan)}>
                  <Eye size={14} /> 查看
                </button>
                <button
                  type="button"
                  className={secondaryButtonClass}
                  onClick={() => {
                    if (isStructuredContent(plan)) {
                      // 结构化教案：弹窗编辑重点/目标/过程等内容
                      setEditor({ planId: plan.id, title: plan.title, content: plan.content });
                    } else {
                      // 历史 Markdown 教案：继续按大纲文本编辑
                      setEditing(plan);
                      setEditForm({ title: plan.title, chapter: plan.chapter ?? '', outline: typeof plan.outline === 'string' ? plan.outline : '' });
                    }
                  }}
                >
                  <Pencil size={14} /> 编辑
                </button>
                {!plan.is_published ? (
                  <button type="button" className="inline-flex items-center gap-1.5 rounded-md bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600" onClick={() => publishMutation.mutate(plan.id)}>
                    <Send size={14} /> 发布
                  </button>
                ) : null}
                <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-red-600 hover:bg-red-50" disabled={deleteMutation.isPending} onClick={() => confirmDeletePlan(plan)}>
                  <Trash2 size={13} /> 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {generateOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">AI 生成教案</h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs text-zinc-500">
                课程
                <select className={`${inputClass} mt-1`} value={generateForm.course_id} onChange={(e) => setGenerateForm({ ...generateForm, course_id: e.target.value })}>
                  {(coursesQuery.data ?? []).map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
                </select>
              </label>
              <label className="block text-xs text-zinc-500">
                章节
                <input className={`${inputClass} mt-1`} value={generateForm.chapter} placeholder="例如：第三章 卷积神经网络" onChange={(e) => setGenerateForm({ ...generateForm, chapter: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                教案标题（选填）
                <input className={`${inputClass} mt-1`} value={generateForm.title} placeholder="默认按章节生成" onChange={(e) => setGenerateForm({ ...generateForm, title: e.target.value })} />
              </label>
              {generateError ? <p className="text-xs text-red-600">{generateError}</p> : null}
              <p className="text-xs text-zinc-400">未配置模型密钥时将使用内置降级大纲，仍可完成备课闭环。</p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setGenerateOpen(false)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!generateForm.course_id || !generateForm.chapter.trim() || generateMutation.isPending} onClick={() => generateMutation.mutate()}>
                {generateMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} 生成
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[80vh] w-full max-w-xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">编辑教案</h3>
            <div className="mt-4 flex-1 space-y-3 overflow-auto">
              <label className="block text-xs text-zinc-500">
                标题
                <input className={`${inputClass} mt-1`} value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                章节
                <input className={`${inputClass} mt-1`} value={editForm.chapter} onChange={(e) => setEditForm({ ...editForm, chapter: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                大纲
                <textarea className={`${inputClass} mt-1`} rows={12} value={editForm.outline} onChange={(e) => setEditForm({ ...editForm, outline: e.target.value })} />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setEditing(null)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!editForm.title.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                {saveMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 保存
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {preview ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">{preview.title}</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setPreview(null)}>✕</button>
            </div>
            <div className="mt-4 flex-1 overflow-auto rounded-md border border-zinc-100 bg-zinc-50 p-4">
              <StructuredPlanView plan={preview} />
            </div>
          </div>
        </div>
      ) : null}

      {editor ? (
        <LessonPlanEditorModal
          planId={editor.planId}
          initialTitle={editor.title}
          initialContent={editor.content}
          onClose={() => setEditor(null)}
          onSaved={() => setEditor(null)}
        />
      ) : null}

      <WorkspaceToast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
