import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Download, Eye, Loader2, Plus, Send, Sparkles, XCircle } from 'lucide-react';
import {
  taAiGrade, taCloseQuiz, taCreateQuiz, taExportGradingCsv, taGradingStats, taListClasses,
  taListGrading, taListQuizzes, taManualGrade, taPublishQuiz, taQuizStats,
  type TaGradingRecord, type TaQuiz, type TaQuizQuestion,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type GradeForm = { recordId: string; score: string; comment: string };
type QuizQuestionDraft = { prompt: string; question_type: string; options: string; answer: string; score: string };
type QuizForm = { title: string; class_id: string; description: string; questions: QuizQuestionDraft[] };

const emptyQuestion = (): QuizQuestionDraft => ({ prompt: '', question_type: 'single_choice', options: '', answer: 'A', score: '10' });

/**
 * 作业批改：批改中心（AI 批改/手动评分/导出）与随堂测验管理双模块。
 */
export function TaGradingPage(): JSX.Element {
  const [tab, setTab] = useState<'grading' | 'quizzes'>('grading');

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="作业批改" subtitle="集中处理学生作业批改任务，管理随堂测验的发布与成绩统计。" />

      <PageHeaderToolbar variant="tabs">
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${tab === 'grading' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setTab('grading')}>
          批改中心
        </button>
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${tab === 'quizzes' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setTab('quizzes')}>
          测验管理
        </button>
      </PageHeaderToolbar>

      {tab === 'grading' ? <GradingPanel /> : <QuizPanel />}
    </div>
  );
}

function GradingPanel(): JSX.Element {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [detail, setDetail] = useState<TaGradingRecord | null>(null);
  const [gradeForm, setGradeForm] = useState<GradeForm>({ recordId: '', score: '', comment: '' });
  const [gradeError, setGradeError] = useState<string | null>(null);

  const filterParams = {
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(classFilter ? { class_id: classFilter } : {}),
  };
  const listQuery = useQuery({
    queryKey: ['ta-grading', statusFilter, classFilter],
    queryFn: () => taListGrading(Object.keys(filterParams).length ? filterParams : undefined),
  });
  const statsQuery = useQuery({ queryKey: ['ta-grading-stats'], queryFn: () => taGradingStats() });
  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['ta-grading'] });
    void queryClient.invalidateQueries({ queryKey: ['ta-grading-stats'] });
    void queryClient.invalidateQueries({ queryKey: ['ta-dashboard'] });
  };

  const aiGradeMutation = useMutation({
    mutationFn: (recordId: string) => taAiGrade(recordId),
    onSuccess: () => invalidate(),
  });

  const batchAiGradeMutation = useMutation({
    mutationFn: async () => {
      const pending = (listQuery.data ?? []).filter((r) => r.status === 'pending');
      for (const record of pending) {
        await taAiGrade(record.id);
      }
    },
    onSuccess: () => invalidate(),
  });

  const manualGradeMutation = useMutation({
    mutationFn: (form: GradeForm) => taManualGrade(form.recordId, Number(form.score), form.comment || undefined),
    onSuccess: () => {
      invalidate();
      setDetail(null);
      setGradeError(null);
    },
    onError: (error) => setGradeError((error as Error).message),
  });

  async function exportCsv(): Promise<void> {
    try {
      const blob = await taExportGradingCsv();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = '批改记录.csv';
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // 忽略导出失败，交全局提示
    }
  }

  const classLabel = (classId: string | null): string => {
    if (!classId) return '—';
    return classesQuery.data?.find((item) => item.id === classId)?.name ?? '—';
  };

  const stats = statsQuery.data;
  return (
    <>
      <PageHeaderToolbar>
        <div className="flex items-center gap-2">
          <select className={inputClass} value={classFilter} onChange={(e) => setClassFilter(e.target.value)}>
            <option value="">全部班级</option>
            {(classesQuery.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select className={inputClass} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">待批改</option>
            <option value="graded">已批改</option>
          </select>
          <button type="button" className={secondaryButtonClass} onClick={() => void exportCsv()}>
            <Download size={15} /> 导出 CSV
          </button>
          <button
            type="button"
            className={primaryButtonClass}
            disabled={batchAiGradeMutation.isPending || (listQuery.data ?? []).filter((r) => r.status === 'pending').length === 0}
            onClick={() => batchAiGradeMutation.mutate()}
          >
            {batchAiGradeMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            AI 一键批改全部待批改
          </button>
        </div>
        <span className="text-xs text-zinc-500">
          共 {stats?.total ?? 0} 条 · 待批改 {stats?.pending ?? 0} · 平均分 {stats?.avg_score ?? '—'}
        </span>
      </PageHeaderToolbar>

      {listQuery.isLoading ? (
        <LoadingState label="正在加载批改记录..." />
      ) : listQuery.isError ? (
        <ErrorState label={(listQuery.error as Error)?.message || '批改记录加载失败'} />
      ) : (listQuery.data ?? []).length === 0 ? (
        <EmptyState label="当前筛选条件下没有批改记录" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">作业标题</th>
                <th className="px-4 py-3 font-medium">班级</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">得分</th>
                <th className="px-4 py-3 font-medium">提交时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {(listQuery.data ?? []).map((record) => (
                <tr key={record.id} className="transition-colors hover:bg-zinc-50">
                  <td className="max-w-64 truncate px-4 py-3 font-medium text-zinc-800">{record.title}</td>
                  <td className="px-4 py-3 text-zinc-500">{classLabel(record.class_id)}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${record.status === 'graded' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                      {record.status === 'graded' ? '已批改' : '待批改'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-600">{record.score != null ? `${record.score} / ${record.total_score ?? 100}` : '—'}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatBeijingDateTimeCompact(record.created_at, '—')}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button type="button" title="查看与评分" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => { setDetail(record); setGradeForm({ recordId: record.id, score: record.score != null ? String(record.score) : '', comment: record.ta_comment ?? '' }); setGradeError(null); }}>
                        <Eye size={15} />
                      </button>
                      <button
                        type="button"
                        title="AI 批改"
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
                        disabled={aiGradeMutation.isPending}
                        onClick={() => aiGradeMutation.mutate(record.id)}
                      >
                        {aiGradeMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} AI 批改
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">{detail.title}</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setDetail(null)}>✕</button>
            </div>
            <div className="mt-4 flex-1 space-y-4 overflow-auto">
              <div>
                <div className="text-xs font-medium text-zinc-500">学生作答</div>
                <p className="mt-1 whitespace-pre-wrap rounded-md border border-zinc-100 bg-zinc-50 p-3 text-sm text-zinc-800">{detail.student_answer || '（未提交作答内容）'}</p>
              </div>
              {detail.ai_comment ? (
                <div>
                  <div className="text-xs font-medium text-zinc-500">AI 批改意见</div>
                  <p className="mt-1 whitespace-pre-wrap rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-zinc-800">{detail.ai_comment}</p>
                </div>
              ) : null}
              <div>
                <div className="text-xs font-medium text-zinc-500">手动评分</div>
                <div className="mt-1 flex items-center gap-2">
                  <input className={inputClass} type="number" min={0} value={gradeForm.score} placeholder="得分" onChange={(e) => setGradeForm({ ...gradeForm, score: e.target.value })} />
                  <span className="text-sm text-zinc-400">/ {detail.total_score ?? 100}</span>
                </div>
                <textarea className={`${inputClass} mt-2`} rows={3} value={gradeForm.comment} placeholder="评语（选填）" onChange={(e) => setGradeForm({ ...gradeForm, comment: e.target.value })} />
                {gradeError ? <p className="mt-1 text-xs text-red-600">{gradeError}</p> : null}
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setDetail(null)}>关闭</button>
              <button type="button" className={primaryButtonClass} disabled={!gradeForm.score || manualGradeMutation.isPending} onClick={() => manualGradeMutation.mutate(gradeForm)}>
                {manualGradeMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} 提交评分
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function QuizPanel(): JSX.Element {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<QuizForm>({ title: '', class_id: '', description: '', questions: [emptyQuestion()] });
  const [formError, setFormError] = useState<string | null>(null);
  const [statsFor, setStatsFor] = useState<TaQuiz | null>(null);

  const quizzesQuery = useQuery({ queryKey: ['ta-quizzes'], queryFn: () => taListQuizzes() });
  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });
  const statsQuery = useQuery({
    queryKey: ['ta-quiz-stats', statsFor?.id],
    queryFn: () => (statsFor ? taQuizStats(statsFor.id) : null),
    enabled: Boolean(statsFor),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['ta-quizzes'] });
  };

  const createMutation = useMutation({
    mutationFn: () => {
      const questions: TaQuizQuestion[] = form.questions
        .filter((q) => q.prompt.trim())
        .map((q) => ({
          prompt: q.prompt.trim(),
          question_type: q.question_type,
          options: q.options ? q.options.split(/[,\n]/).map((item) => item.trim()).filter(Boolean) : null,
          answer: q.answer.trim(),
          score: Number(q.score) || 10,
        }));
      return taCreateQuiz({
        title: form.title,
        class_id: form.class_id,
        description: form.description || null,
        questions,
      });
    },
    onSuccess: () => { invalidate(); setFormOpen(false); setFormError(null); },
    onError: (error) => setFormError((error as Error).message),
  });

  const publishMutation = useMutation({ mutationFn: (quizId: string) => taPublishQuiz(quizId), onSuccess: () => invalidate() });
  const closeMutation = useMutation({ mutationFn: (quizId: string) => taCloseQuiz(quizId), onSuccess: () => invalidate() });

  const classLabel = (classId: string): string => classesQuery.data?.find((item) => item.id === classId)?.name ?? classId;

  return (
    <>
      <PageHeaderToolbar>
        <button
          type="button"
          className={primaryButtonClass}
          onClick={() => {
            setForm({ title: '', class_id: classesQuery.data?.[0]?.id ?? '', description: '', questions: [emptyQuestion()] });
            setFormError(null);
            setFormOpen(true);
          }}
        >
          <Plus size={15} /> 创建测验
        </button>
      </PageHeaderToolbar>

      {quizzesQuery.isLoading ? (
        <LoadingState label="正在加载测验列表..." />
      ) : quizzesQuery.isError ? (
        <ErrorState label={(quizzesQuery.error as Error)?.message || '测验列表加载失败'} />
      ) : (quizzesQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有测验，点击「创建测验」开始。" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">测验标题</th>
                <th className="px-4 py-3 font-medium">班级</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">创建时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {(quizzesQuery.data ?? []).map((quiz) => (
                <tr key={quiz.id} className="transition-colors hover:bg-zinc-50">
                  <td className="px-4 py-3 font-medium text-zinc-800">{quiz.title}</td>
                  <td className="px-4 py-3 text-zinc-500">{classLabel(quiz.class_id)}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${quiz.status === 'published' ? 'bg-emerald-100 text-emerald-700' : quiz.status === 'closed' ? 'bg-zinc-100 text-zinc-600' : 'bg-amber-100 text-amber-700'}`}>
                      {quiz.status === 'published' ? '已发布' : quiz.status === 'closed' ? '已关闭' : '草稿'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-500">{formatBeijingDateTimeCompact(quiz.created_at, '—')}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100" onClick={() => setStatsFor(quiz)}>
                        统计
                      </button>
                      {quiz.status === 'draft' ? (
                        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50" onClick={() => publishMutation.mutate(quiz.id)}>
                          <Send size={13} /> 发布
                        </button>
                      ) : null}
                      {quiz.status === 'published' ? (
                        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100" onClick={() => closeMutation.mutate(quiz.id)}>
                          <XCircle size={13} /> 关闭
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">创建随堂测验</h3>
            <div className="mt-4 flex-1 space-y-3 overflow-auto">
              <label className="block text-xs text-zinc-500">
                测验标题
                <input className={`${inputClass} mt-1`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-zinc-500">
                  班级
                  <select className={`${inputClass} mt-1`} value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}>
                    {(classesQuery.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                <label className="block text-xs text-zinc-500">
                  说明
                  <input className={`${inputClass} mt-1`} value={form.description} placeholder="选填" onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </label>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-zinc-500">题目（选择题填写选项，用逗号分隔；answer 填 A/B/C...）</span>
                  <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => setForm({ ...form, questions: [...form.questions, emptyQuestion()] })}>
                    + 添加题目
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  {form.questions.map((question, index) => (
                    <div key={index} className="rounded-md border border-zinc-100 bg-zinc-50 p-3">
                      <div className="flex items-center gap-2">
                        <input className={`${inputClass} flex-1`} placeholder="题目内容" value={question.prompt} onChange={(e) => {
                          const next = [...form.questions];
                          next[index] = { ...next[index], prompt: e.target.value };
                          setForm({ ...form, questions: next });
                        }} />
                        <button type="button" className="text-xs text-red-500 hover:underline" onClick={() => {
                          const next = form.questions.filter((_, i) => i !== index);
                          setForm({ ...form, questions: next.length ? next : [emptyQuestion()] });
                        }}>
                          删除
                        </button>
                      </div>
                      <div className="mt-2 grid grid-cols-4 gap-2">
                        <select className={inputClass} value={question.question_type} onChange={(e) => {
                          const next = [...form.questions];
                          next[index] = { ...next[index], question_type: e.target.value };
                          setForm({ ...form, questions: next });
                        }}>
                          <option value="single_choice">单选题</option>
                          <option value="multiple_choice">多选题</option>
                          <option value="true_false">判断题</option>
                        </select>
                        <input className={inputClass} placeholder="选项，逗号分隔" value={question.options} onChange={(e) => {
                          const next = [...form.questions];
                          next[index] = { ...next[index], options: e.target.value };
                          setForm({ ...form, questions: next });
                        }} />
                        <input className={inputClass} placeholder="答案 A/B/C" value={question.answer} onChange={(e) => {
                          const next = [...form.questions];
                          next[index] = { ...next[index], answer: e.target.value };
                          setForm({ ...form, questions: next });
                        }} />
                        <input className={inputClass} type="number" placeholder="分值" value={question.score} onChange={(e) => {
                          const next = [...form.questions];
                          next[index] = { ...next[index], score: e.target.value };
                          setForm({ ...form, questions: next });
                        }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setFormOpen(false)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!form.title.trim() || !form.class_id || createMutation.isPending} onClick={() => createMutation.mutate()}>
                {createMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 创建
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {statsFor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">成绩统计 · {statsFor.title}</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setStatsFor(null)}>✕</button>
            </div>
            {statsQuery.isLoading ? (
              <LoadingState label="正在加载统计数据..." />
            ) : statsQuery.data ? (
              <div className="mt-4 space-y-3">
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-md border border-zinc-100 p-3 text-center">
                    <div className="text-lg font-semibold text-zinc-900">{statsQuery.data.submission_count}</div>
                    <div className="text-xs text-zinc-500">提交人数</div>
                  </div>
                  <div className="rounded-md border border-zinc-100 p-3 text-center">
                    <div className="text-lg font-semibold text-zinc-900">{statsQuery.data.avg_score ?? '—'}</div>
                    <div className="text-xs text-zinc-500">平均分</div>
                  </div>
                  <div className="rounded-md border border-zinc-100 p-3 text-center">
                    <div className="text-lg font-semibold text-zinc-900">{statsQuery.data.full_score}</div>
                    <div className="text-xs text-zinc-500">满分</div>
                  </div>
                </div>
                <ul className="space-y-2">
                  {statsQuery.data.questions.map((question) => (
                    <li key={question.question_id} className="rounded-md border border-zinc-100 px-3 py-2">
                      <div className="text-sm text-zinc-800">{question.prompt}</div>
                      <div className="mt-1 text-xs text-zinc-500">正确率 {Math.round(question.accuracy * 100)}%（{question.correct_count}/{question.total_count}）</div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <ErrorState label="统计数据加载失败" />
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
