import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Eye, Loader2, Pencil, Send, Sparkles } from 'lucide-react';
import { api } from '../../api/endpoints';
import { taGenerateLessonPlan, taListLessonPlans, taPublishLessonPlan, taUpdateLessonPlan, type TaLessonPlan } from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type GenerateForm = { course_id: string; chapter: string; title: string };
type EditForm = { title: string; chapter: string; outline: string };

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
      title: generateForm.title || undefined,
    }),
    onSuccess: () => {
      invalidate();
      setGenerateOpen(false);
      setGenerateError(null);
    },
    onError: (error) => setGenerateError((error as Error).message),
  });

  const publishMutation = useMutation({ mutationFn: (planId: string) => taPublishLessonPlan(planId), onSuccess: () => invalidate() });

  const saveMutation = useMutation({
    mutationFn: () => (editing ? taUpdateLessonPlan(editing.id, {
      title: editForm.title,
      chapter: editForm.chapter || null,
      outline: editForm.outline || null,
    }) : Promise.resolve({ id: '' })),
    onSuccess: () => { invalidate(); setEditing(null); },
  });

  const contentText = (plan: TaLessonPlan): string => {
    if (typeof plan.outline === 'string' && plan.outline) return plan.outline;
    if (plan.content && typeof plan.content === 'object') {
      return JSON.stringify(plan.content, null, 2).slice(0, 2000);
    }
    return '（暂无大纲内容）';
  };

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
      </PageHeaderToolbar>

      {plansQuery.isLoading ? (
        <LoadingState label="正在加载教案列表..." />
      ) : plansQuery.isError ? (
        <ErrorState label={(plansQuery.error as Error)?.message || '教案列表加载失败'} />
      ) : (plansQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有教案，点击「AI 生成教案」开始备课。" />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {(plansQuery.data ?? []).map((plan) => (
            <div key={plan.id} className="rounded-lg border border-zinc-200 bg-white p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
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
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-zinc-600">{contentText(plan)}</p>
              <div className="mt-4 flex items-center gap-2">
                <button type="button" className={secondaryButtonClass} onClick={() => setPreview(plan)}>
                  <Eye size={14} /> 查看
                </button>
                <button
                  type="button"
                  className={secondaryButtonClass}
                  onClick={() => {
                    setEditing(plan);
                    setEditForm({ title: plan.title, chapter: plan.chapter ?? '', outline: typeof plan.outline === 'string' ? plan.outline : '' });
                  }}
                >
                  <Pencil size={14} /> 编辑
                </button>
                {!plan.is_published ? (
                  <button type="button" className="inline-flex items-center gap-1.5 rounded-md bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600" onClick={() => publishMutation.mutate(plan.id)}>
                    <Send size={14} /> 发布
                  </button>
                ) : null}
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
            <p className="mt-4 flex-1 whitespace-pre-wrap overflow-auto rounded-md border border-zinc-100 bg-zinc-50 p-4 text-sm text-zinc-700">{contentText(preview)}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
