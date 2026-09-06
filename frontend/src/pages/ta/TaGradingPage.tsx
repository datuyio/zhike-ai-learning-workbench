import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ClipboardList, Download, Eye, Loader2, Plus, Send, Sparkles, Trash2, XCircle } from 'lucide-react';
import {
  taAiGrade, taAiGradeBatch, taCloseAssignment, taCloseQuiz, taCreateAssignment, taCreateQuiz, taDeleteQuizzes, taDeleteQuiz,
  taExportGradingCsv, taGetGradingDetail, taGradingStats, taListAssignmentSubmissions, taListAssignments, taListClasses, taListGrading,
  taListQuestionBank, taListQuizzes, taManualGrade, taPublishAssignment, taPublishQuiz, taQuizStats,
  type TaAssignment, type TaGradingRecord, type TaQuestionBankItem, type TaQuiz, type TaQuizQuestion,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { WorkspaceToast, type WorkspaceToastItem } from '../../components/shared/WorkspaceToast';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type GradeForm = { recordId: string; score: string; comment: string };
type QuizQuestionDraft = { prompt: string; question_type: string; options: string; answer: string; score: string };
type QuizForm = { title: string; class_id: string; description: string; questions: QuizQuestionDraft[] };
type QuestionSourceTab = 'bank' | 'manual';
type AssignmentForm = {
  title: string;
  class_id: string;
  description: string;
  due_at: string;
  late_policy: string;
  questions: QuizQuestionDraft[];
};

const emptyAssignmentForm = (classId: string): AssignmentForm => ({
  title: '',
  class_id: classId,
  description: '',
  due_at: '',
  late_policy: 'allow_penalty',
  questions: [emptyQuestion()],
});

const questionTypeLabel = (type: string | null | undefined): string => {
  switch (type) {
    case 'single_choice': return '单选';
    case 'multiple_choice': return '多选';
    case 'true_false': return '判断';
    case 'code': return '代码';
    case 'blank': return '填空';
    case 'short_answer': return '简答';
    case 'multi': return '多题';
    default: return '综合';
  }
};

const emptyQuestion = (): QuizQuestionDraft => ({ prompt: '', question_type: 'single_choice', options: '', answer: 'A', score: '10' });

/**
 * 作业批改：批改中心（课后作业发布 + AI/手动批改）与随堂测验管理双模块。
 */
export function TaGradingPage(): JSX.Element {
  const [tab, setTab] = useState<'grading' | 'quizzes'>('grading');

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="作业批改" subtitle="布置课后作业并处理批改，管理随堂测验的发布与成绩统计。" />

      <PageHeaderToolbar variant="tabs">
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${tab === 'grading' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setTab('grading')}>
          批改中心
        </button>
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${tab === 'quizzes' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setTab('quizzes')}>
          随堂测验
        </button>
      </PageHeaderToolbar>

      {tab === 'grading' ? <GradingPanel /> : <QuizPanel />}
    </div>
  );
}

function GradingPanel(): JSX.Element {
  const [section, setSection] = useState<'assignments' | 'records'>('assignments');

  return (
    <>
      <PageHeaderToolbar variant="tabs">
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${section === 'assignments' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSection('assignments')}>
          课后作业
        </button>
        <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${section === 'records' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSection('records')}>
          批改记录
        </button>
      </PageHeaderToolbar>

      {section === 'assignments' ? <AssignmentSection /> : <GradingRecordsSection />}
    </>
  );
}

function AssignmentSection(): JSX.Element {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<AssignmentForm>(emptyAssignmentForm(''));
  const [formError, setFormError] = useState<string | null>(null);
  const [sourceTab, setSourceTab] = useState<QuestionSourceTab>('bank');
  const [selectedItems, setSelectedItems] = useState<TaQuestionBankItem[]>([]);
  const [bankFilter, setBankFilter] = useState<{ question_type: string; keyword: string }>({ question_type: '', keyword: '' });
  const [submissionsFor, setSubmissionsFor] = useState<TaAssignment | null>(null);
  const [toast, setToast] = useState<WorkspaceToastItem | null>(null);

  const assignmentsQuery = useQuery({ queryKey: ['ta-assignments'], queryFn: () => taListAssignments() });
  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });
  const bankQuery = useQuery({
    queryKey: ['ta-assignment-bank', bankFilter.question_type, bankFilter.keyword],
    queryFn: () => taListQuestionBank({
      question_type: bankFilter.question_type || undefined,
      keyword: bankFilter.keyword || undefined,
    }),
  });
  const submissionsQuery = useQuery({
    queryKey: ['ta-assignment-submissions', submissionsFor?.id],
    queryFn: () => (submissionsFor ? taListAssignmentSubmissions(submissionsFor.id) : null),
    enabled: Boolean(submissionsFor),
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['ta-assignments'] });

  const toggleSelected = (item: TaQuestionBankItem): void => {
    setSelectedItems((prev) => (prev.some((it) => it.id === item.id) ? prev.filter((it) => it.id !== item.id) : [...prev, item]));
  };

  const createMutation = useMutation({
    mutationFn: () => {
      // 手动出题仅在非空时提交；从题库选题通过 question_ids 提交（逻辑与布置测验一致）
      const manualQuestions = form.questions
        .filter((q) => q.prompt.trim())
        .map((q) => ({
          prompt: q.prompt.trim(),
          question_type: q.question_type,
          options: q.question_type === 'true_false'
            ? ['正确', '错误']
            : (q.options ? q.options.split(/[,\n]/).map((item) => item.trim()).filter(Boolean) : null),
          answer: q.answer.trim() || null,
          score: Number(q.score) || 10,
        }));
      return taCreateAssignment({
        title: form.title,
        class_id: form.class_id,
        description: form.description || null,
        due_at: form.due_at || null,
        late_policy: form.late_policy,
        question_ids: selectedItems.length ? selectedItems.map((item) => item.id) : undefined,
        questions: manualQuestions.length ? manualQuestions : undefined,
      });
    },
    onSuccess: () => {
      invalidate();
      setFormOpen(false);
      setFormError(null);
      setToast({ id: `ta-assignment-create-${Date.now()}`, message: '作业草稿已创建，可继续发布', tone: 'success' });
    },
    onError: (error) => setFormError((error as Error).message),
  });

  const publishMutation = useMutation({
    mutationFn: (assignmentId: string) => taPublishAssignment(assignmentId),
    onSuccess: () => {
      invalidate();
      setToast({ id: `ta-assignment-publish-${Date.now()}`, message: '作业已发布', tone: 'success' });
    },
    onError: (error) => setToast({ id: `ta-assignment-publish-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const closeMutation = useMutation({
    mutationFn: (assignmentId: string) => taCloseAssignment(assignmentId),
    onSuccess: () => {
      invalidate();
      setToast({ id: `ta-assignment-close-${Date.now()}`, message: '作业已关闭', tone: 'success' });
    },
    onError: (error) => setToast({ id: `ta-assignment-close-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const classLabel = (classId: string): string => classesQuery.data?.find((item) => item.id === classId)?.name ?? classId;
  const assignments = assignmentsQuery.data ?? [];

  return (
    <>
      <PageHeaderToolbar>
        <button type="button" className={primaryButtonClass} onClick={() => {
          setForm(emptyAssignmentForm(classesQuery.data?.[0]?.id ?? ''));
          setFormError(null);
          setSelectedItems([]);
          setSourceTab('bank');
          setBankFilter({ question_type: '', keyword: '' });
          setFormOpen(true);
        }}>
          <Plus size={15} /> 布置作业
        </button>
        <button type="button" className={secondaryButtonClass} onClick={() => assignmentsQuery.refetch()}>
          <Loader2 size={15} className={assignmentsQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
      </PageHeaderToolbar>

      {assignmentsQuery.isLoading ? (
        <LoadingState label="正在加载作业列表..." />
      ) : assignmentsQuery.isError ? (
        <ErrorState label={(assignmentsQuery.error as Error)?.message || '作业列表加载失败'} />
      ) : assignments.length === 0 ? (
        <EmptyState label="还没有课后作业，点击「布置作业」开始。" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">作业标题</th>
                <th className="px-4 py-3 font-medium">班级</th>
                <th className="px-4 py-3 font-medium">题型</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">截止时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {assignments.map((assignment) => (
                <tr key={assignment.id} className="transition-colors hover:bg-zinc-50">
                  <td className="max-w-64 truncate px-4 py-3 font-medium text-zinc-800">{assignment.title}</td>
                  <td className="px-4 py-3 text-zinc-500">{classLabel(assignment.class_id)}</td>
                  <td className="px-4 py-3 text-zinc-500">
                    {assignment.question_type === 'multi'
                      ? `多题（${assignment.question_count ?? 0} 题）`
                      : questionTypeLabel(assignment.question_type)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${assignment.status === 'published' ? 'bg-emerald-100 text-emerald-700' : assignment.status === 'closed' ? 'bg-zinc-100 text-zinc-600' : 'bg-amber-100 text-amber-700'}`}>
                      {assignment.status === 'published' ? '已发布' : assignment.status === 'closed' ? '已关闭' : '草稿'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-500">{formatBeijingDateTimeCompact(assignment.due_at, '不限')}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100" onClick={() => setSubmissionsFor(assignment)}>
                        <ClipboardList size={13} /> 提交情况
                      </button>
                      {assignment.status === 'draft' ? (
                        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50" onClick={() => publishMutation.mutate(assignment.id)}>
                          <Send size={13} /> 发布
                        </button>
                      ) : null}
                      {assignment.status === 'published' ? (
                        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100" onClick={() => closeMutation.mutate(assignment.id)}>
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
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">布置课后作业</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setFormOpen(false)}>✕</button>
            </div>
            <div className="mt-4 flex-1 space-y-3 overflow-auto">
              <label className="block text-xs text-zinc-500">
                作业标题
                <input className={`${inputClass} mt-1`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="例如：深度学习第 4 章课后作业" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-zinc-500">
                  班级
                  <select className={`${inputClass} mt-1`} value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}>
                    {(classesQuery.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
                <label className="block text-xs text-zinc-500">
                  作业说明
                  <input className={`${inputClass} mt-1`} value={form.description} placeholder="选填" onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${sourceTab === 'bank' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSourceTab('bank')}>
                  从题库选题
                </button>
                <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${sourceTab === 'manual' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSourceTab('manual')}>
                  手动出题
                </button>
                <span className="ml-auto text-xs text-zinc-500">
                  已选 {selectedItems.length + form.questions.filter((q) => q.prompt.trim()).length} 题
                </span>
              </div>
              {sourceTab === 'bank' ? (
                <>
                  <div className="flex items-center gap-2">
                    <select className={inputClass} value={bankFilter.question_type} onChange={(e) => setBankFilter({ ...bankFilter, question_type: e.target.value })}>
                      <option value="">全部题型</option>
                      <option value="single_choice">单选题</option>
                      <option value="multiple_choice">多选题</option>
                      <option value="true_false">判断题</option>
                      <option value="blank">填空题</option>
                    </select>
                    <input className={`${inputClass} flex-1`} placeholder="搜索题干关键词" value={bankFilter.keyword} onChange={(e) => setBankFilter({ ...bankFilter, keyword: e.target.value })} />
                    <button type="button" className={secondaryButtonClass} onClick={() => bankQuery.refetch()}>
                      <Loader2 size={14} className={bankQuery.isFetching ? 'animate-spin' : ''} /> 刷新
                    </button>
                  </div>
                  {bankQuery.isLoading ? (
                    <LoadingState label="正在加载题库..." />
                  ) : bankQuery.isError ? (
                    <ErrorState label={(bankQuery.error as Error)?.message || '题库加载失败'} />
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-auto rounded-md border border-zinc-100 p-2">
                      {(bankQuery.data ?? []).map((item) => (
                        <label key={item.id} className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-2 transition-colors hover:bg-zinc-50">
                          <input type="checkbox" className="mt-0.5" checked={selectedItems.some((it) => it.id === item.id)} onChange={() => toggleSelected(item)} />
                          <span className="flex-1 text-sm text-zinc-800">{item.prompt}</span>
                          <span className="shrink-0 text-xs text-zinc-500">{questionTypeLabel(item.question_type)} · {item.score}分 · 答案{item.answer}</span>
                        </label>
                      ))}
                      {(bankQuery.data ?? []).length === 0 ? <p className="px-2 py-4 text-center text-xs text-zinc-400">题库暂无匹配题目</p> : null}
                    </div>
                  )}
                  {selectedItems.length > 0 ? (
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-zinc-500">已选题目（{selectedItems.length}）</div>
                      {selectedItems.map((item) => (
                        <div key={item.id} className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
                          <span className="flex-1 text-sm text-zinc-800">{item.prompt}</span>
                          <span className="shrink-0 text-xs text-zinc-500">{questionTypeLabel(item.question_type)} · {item.score}分</span>
                          <button type="button" className="shrink-0 text-xs text-red-500 hover:underline" onClick={() => toggleSelected(item)}>移除</button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-zinc-500">手动题目（客观题填写选项与答案；简答/代码题仅填题干，AI 批改）</span>
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
                            <option value="blank">填空题</option>
                            <option value="short_answer">简答题</option>
                            <option value="code">代码题</option>
                          </select>
                          {question.question_type === 'short_answer' || question.question_type === 'code' ? (
                            <input className={`${inputClass} col-span-2`} placeholder="参考答案/评分要点（选填，供 AI 批改参考）" value={question.options} onChange={(e) => {
                              const next = [...form.questions];
                              next[index] = { ...next[index], options: e.target.value };
                              setForm({ ...form, questions: next });
                            }} />
                          ) : (
                            <input className={inputClass} placeholder={question.question_type === 'true_false' ? '正确,错误' : '选项，逗号分隔'} value={question.options} onChange={(e) => {
                              const next = [...form.questions];
                              next[index] = { ...next[index], options: e.target.value };
                              setForm({ ...form, questions: next });
                            }} />
                          )}
                          {question.question_type === 'true_false' ? (
                            <select className={inputClass} value={question.answer} onChange={(e) => {
                              const next = [...form.questions];
                              next[index] = { ...next[index], answer: e.target.value };
                              setForm({ ...form, questions: next });
                            }}>
                              <option value="T">T（正确）</option>
                              <option value="F">F（错误）</option>
                            </select>
                          ) : (
                            <input className={inputClass} placeholder={question.question_type === 'short_answer' || question.question_type === 'code' ? '—' : '答案，如 B 或 A,C'} value={question.answer} onChange={(e) => {
                              const next = [...form.questions];
                              next[index] = { ...next[index], answer: e.target.value };
                              setForm({ ...form, questions: next });
                            }} />
                          )}
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
              )}
              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-zinc-500">
                  截止时间
                  <input className={`${inputClass} mt-1`} type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
                </label>
                <label className="block text-xs text-zinc-500">
                  迟交策略
                  <select className={`${inputClass} mt-1`} value={form.late_policy} onChange={(e) => setForm({ ...form, late_policy: e.target.value })}>
                    <option value="allow_penalty">允许并扣分</option>
                    <option value="allow">允许不扣分</option>
                    <option value="reject">拒绝迟交</option>
                  </select>
                </label>
              </div>
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setFormOpen(false)}>取消</button>
              <button
                type="button"
                className={primaryButtonClass}
                disabled={!form.title.trim() || !form.class_id || (selectedItems.length === 0 && form.questions.every((q) => !q.prompt.trim())) || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 创建草稿
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {submissionsFor ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">提交情况 · {submissionsFor.title}</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setSubmissionsFor(null)}>✕</button>
            </div>
            <div className="mt-4 flex-1 overflow-auto">
              {submissionsQuery.isLoading ? (
                <LoadingState label="正在加载提交列表..." />
              ) : (submissionsQuery.data ?? []).length === 0 ? (
                <p className="py-8 text-center text-sm text-zinc-400">还没有学生提交</p>
              ) : (
                <ul className="space-y-2">
                  {(submissionsQuery.data ?? []).map((submission) => (
                    <li key={submission.id} className="rounded-md border border-zinc-100 p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-zinc-800">{submission.student_name}</span>
                        <span className="text-xs text-zinc-500">
                          {submission.score != null ? `得分 ${submission.score} / ${submission.total_score ?? '—'}` : '待批改'} · 第 {submission.attempt_number} 次{submission.is_late ? ' · 迟交' : ''}
                        </span>
                      </div>
                      {submission.answers && submission.questions && submission.questions.length > 0 ? (
                        // 多题作业：逐题展示学生作答与标准答案
                        <div className="mt-1 space-y-1.5">
                          {submission.questions.map((q, index) => (
                            <div key={q.id} className="rounded-md bg-zinc-50 px-3 py-2">
                              <div className="text-sm text-zinc-700">{index + 1}. {q.prompt}</div>
                              <div className="mt-0.5 text-xs text-zinc-600">学生答案：{submission.answers?.[q.id] ?? '（未作答）'}</div>
                              <div className="text-xs text-zinc-400">标准答案：{q.answer ?? '（主观题）'} · {q.score} 分</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-1 whitespace-pre-wrap rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{submission.answer}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <WorkspaceToast toast={toast} onDismiss={() => setToast(null)} />
    </>
  );
}

function GradingRecordsSection(): JSX.Element {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [detail, setDetail] = useState<TaGradingRecord | null>(null);
  const [gradeForm, setGradeForm] = useState<GradeForm>({ recordId: '', score: '', comment: '' });
  const [gradeError, setGradeError] = useState<string | null>(null);
  const [aiGradeError, setAiGradeError] = useState<string | null>(null);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const [selectedRecordIds, setSelectedRecordIds] = useState<string[]>([]);

  const listQuery = useQuery({
    queryKey: ['ta-grading', statusFilter],
    queryFn: () => taListGrading(statusFilter ? { status: statusFilter } : undefined),
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
    onSuccess: () => {
      setAiGradeError(null);
      invalidate();
    },
    onError: (error) => setAiGradeError((error as Error).message || 'AI 批改失败，请稍后重试'),
  });

  // 批量 AI 批改：勾选多条记录后一键批改，失败条数在提示中体现
  const batchAiGradeMutation = useMutation({
    mutationFn: (recordIds: string[]) => taAiGradeBatch(recordIds),
    onSuccess: (result) => {
      invalidate();
      setSelectedRecordIds([]);
      setBatchMessage(result.message);
      setAiGradeError(null);
    },
    onError: (error) => setAiGradeError((error as Error).message || '批量 AI 批改失败，请稍后重试'),
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

  const toggleRecordSelect = (recordId: string): void => {
    setSelectedRecordIds((prev) => (prev.includes(recordId) ? prev.filter((id) => id !== recordId) : [...prev, recordId]));
  };

  const records = listQuery.data ?? [];
  const allSelected = records.length > 0 && records.every((r) => selectedRecordIds.includes(r.id));

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
          <select className={inputClass} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">全部状态</option>
            <option value="pending">待批改</option>
            <option value="graded">已批改</option>
          </select>
          <button
            type="button"
            className={`${secondaryButtonClass} border-blue-200 text-blue-600 hover:bg-blue-50`}
            disabled={selectedRecordIds.length === 0 || batchAiGradeMutation.isPending}
            onClick={() => batchAiGradeMutation.mutate(selectedRecordIds)}
          >
            {batchAiGradeMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} 批量 AI 批改（{selectedRecordIds.length}）
          </button>
          <button type="button" className={secondaryButtonClass} onClick={() => void exportCsv()}>
            <Download size={15} /> 导出 CSV
          </button>
        </div>
        <span className="text-xs text-zinc-500">
          共 {stats?.total ?? 0} 条 · 待批改 {stats?.pending ?? 0} · 平均分 {stats?.avg_score ?? '—'}
        </span>
      </PageHeaderToolbar>

      {aiGradeError ? (
        <p className="mt-3 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-600" role="alert">
          AI 批改失败：{aiGradeError}
        </p>
      ) : null}
      {batchMessage ? (
        <p className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700" role="status">
          {batchMessage}
        </p>
      ) : null}

      {listQuery.isLoading ? (
        <LoadingState label="正在加载批改记录..." />
      ) : listQuery.isError ? (
        <ErrorState label={(listQuery.error as Error)?.message || '批改记录加载失败'} />
      ) : records.length === 0 ? (
        <EmptyState label="当前筛选条件下没有批改记录" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label="全选批改记录"
                    checked={allSelected}
                    onChange={() => setSelectedRecordIds(allSelected ? [] : records.map((r) => r.id))}
                  />
                </th>
                <th className="px-4 py-3 font-medium">作业标题</th>
                <th className="px-4 py-3 font-medium">班级</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">得分</th>
                <th className="px-4 py-3 font-medium">提交时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {records.map((record) => (
                <tr key={record.id} className={`transition-colors hover:bg-zinc-50 ${selectedRecordIds.includes(record.id) ? 'bg-blue-50/40' : ''}`}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label={`选择批改记录 ${record.title}`}
                      checked={selectedRecordIds.includes(record.id)}
                      onChange={() => toggleRecordSelect(record.id)}
                    />
                  </td>
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
                      <button type="button" title="查看与评分" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => {
                        setDetail(record);
                        setGradeForm({ recordId: record.id, score: record.score != null ? String(record.score) : '', comment: record.ta_comment ?? '' });
                        setGradeError(null);
                        // 拉取完整详情（含多题作业的逐题作答与题目快照）
                        void taGetGradingDetail(record.id)
                          .then((full) => setDetail(full))
                          .catch(() => { /* 保留列表数据展示 */ });
                      }}>
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
              {detail.student_answers && detail.questions && detail.questions.length > 0 ? (
                // 多题作业：逐题展示学生作答与标准答案
                <div>
                  <div className="text-xs font-medium text-zinc-500">学生作答（多题作业）</div>
                  <div className="mt-1 space-y-2">
                    {detail.questions.map((q, index) => (
                      <div key={q.id} className="rounded-md border border-zinc-100 bg-zinc-50 p-3">
                        <div className="text-sm text-zinc-800">{index + 1}. {q.prompt}</div>
                        <div className="mt-1 text-xs text-zinc-700">学生答案：{detail.student_answers?.[q.id] ?? '（未作答）'}</div>
                        <div className="mt-0.5 text-xs text-zinc-400">标准答案：{q.answer ?? '（主观题）'} · {q.score} 分</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div>
                  <div className="text-xs font-medium text-zinc-500">学生作答</div>
                  <p className="mt-1 whitespace-pre-wrap rounded-md border border-zinc-100 bg-zinc-50 p-3 text-sm text-zinc-800">{detail.student_answer || '（未提交作答内容）'}</p>
                </div>
              )}
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
  // 题目来源：默认从题库选题；sourceTab 切换「从题库选题 / 手动出题」
  const [sourceTab, setSourceTab] = useState<QuestionSourceTab>('bank');
  const [selectedItems, setSelectedItems] = useState<TaQuestionBankItem[]>([]);
  const [bankFilter, setBankFilter] = useState<{ question_type: string; keyword: string }>({ question_type: '', keyword: '' });
  // 测验列表多选（用于批量删除）与操作提示
  const [selectedQuizIds, setSelectedQuizIds] = useState<string[]>([]);
  const [toast, setToast] = useState<WorkspaceToastItem | null>(null);

  const quizzesQuery = useQuery({ queryKey: ['ta-quizzes'], queryFn: () => taListQuizzes() });
  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });
  const bankQuery = useQuery({
    queryKey: ['ta-question-bank', bankFilter.question_type, bankFilter.keyword],
    queryFn: () => taListQuestionBank({
      question_type: bankFilter.question_type || undefined,
      keyword: bankFilter.keyword || undefined,
    }),
  });
  const statsQuery = useQuery({
    queryKey: ['ta-quiz-stats', statsFor?.id],
    queryFn: () => (statsFor ? taQuizStats(statsFor.id) : null),
    enabled: Boolean(statsFor),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['ta-quizzes'] });
  };

  const toggleSelected = (item: TaQuestionBankItem): void => {
    setSelectedItems((prev) => (prev.some((it) => it.id === item.id) ? prev.filter((it) => it.id !== item.id) : [...prev, item]));
  };

  const toggleQuizSelect = (quizId: string): void => {
    setSelectedQuizIds((prev) => (prev.includes(quizId) ? prev.filter((id) => id !== quizId) : [...prev, quizId]));
  };

  const createMutation = useMutation({
    mutationFn: () => {
      // 手动出题的题目仅在非空时提交；从题库选题通过 question_ids 提交
      const manualQuestions: TaQuizQuestion[] = form.questions
        .filter((q) => q.prompt.trim())
        .map((q) => ({
          prompt: q.prompt.trim(),
          question_type: q.question_type,
          options: q.question_type === 'true_false'
            ? ['正确', '错误']
            : (q.options ? q.options.split(/[,\n]/).map((item) => item.trim()).filter(Boolean) : null),
          answer: q.answer.trim(),
          score: Number(q.score) || 10,
        }));
      return taCreateQuiz({
        title: form.title,
        class_id: form.class_id,
        description: form.description || null,
        question_ids: selectedItems.length ? selectedItems.map((item) => item.id) : undefined,
        questions: manualQuestions.length ? manualQuestions : undefined,
      });
    },
    onSuccess: () => { invalidate(); setFormOpen(false); setFormError(null); },
    onError: (error) => setFormError((error as Error).message),
  });

  const publishMutation = useMutation({ mutationFn: (quizId: string) => taPublishQuiz(quizId), onSuccess: () => invalidate() });
  const closeMutation = useMutation({ mutationFn: (quizId: string) => taCloseQuiz(quizId), onSuccess: () => invalidate() });

  // 删除（单个/批量）：仅草稿可删；已发布/已关闭的测验后端会拒绝或跳过
  const deleteMutation = useMutation({
    mutationFn: (quizId: string) => taDeleteQuiz(quizId),
    onSuccess: () => {
      invalidate();
      setToast({ id: `ta-delete-${Date.now()}`, message: '测验已删除', tone: 'success' });
    },
    onError: (error) => setToast({ id: `ta-delete-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const batchDeleteMutation = useMutation({
    mutationFn: () => taDeleteQuizzes(selectedQuizIds),
    onSuccess: (result) => {
      invalidate();
      setSelectedQuizIds([]);
      setToast({
        id: `ta-batch-delete-${Date.now()}`,
        message: result.message,
        tone: result.skipped.length > 0 && result.deleted === 0 ? 'error' : 'success',
      });
    },
    onError: (error) => setToast({ id: `ta-batch-delete-${Date.now()}`, message: (error as Error).message, tone: 'error' }),
  });

  const confirmDeleteQuiz = (quiz: TaQuiz): void => {
    if (window.confirm(`确定删除测验「${quiz.title}」吗？删除后不可恢复。`)) {
      deleteMutation.mutate(quiz.id);
    }
  };

  const confirmBatchDelete = (): void => {
    if (selectedQuizIds.length === 0) return;
    if (window.confirm(`确定删除选中的 ${selectedQuizIds.length} 个测验吗？仅草稿会删除，已发布/已关闭的将被跳过。`)) {
      batchDeleteMutation.mutate();
    }
  };

  const classLabel = (classId: string): string => classesQuery.data?.find((item) => item.id === classId)?.name ?? classId;

  const quizzes = quizzesQuery.data ?? [];

  return (
    <>
      <PageHeaderToolbar>
        <button
          type="button"
          className={primaryButtonClass}
          onClick={() => {
            setForm({ title: '', class_id: classesQuery.data?.[0]?.id ?? '', description: '', questions: [emptyQuestion()] });
            setFormError(null);
            setSelectedItems([]);
            setSourceTab('bank');
            setBankFilter({ question_type: '', keyword: '' });
            setFormOpen(true);
          }}
        >
          <Plus size={15} /> 布置测验
        </button>
        {selectedQuizIds.length > 0 ? (
          <button
            type="button"
            className={`${secondaryButtonClass} border-red-200 text-red-600 hover:bg-red-50`}
            disabled={batchDeleteMutation.isPending}
            onClick={confirmBatchDelete}
          >
            {batchDeleteMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} 批量删除（{selectedQuizIds.length}）
          </button>
        ) : null}
        <span className="ml-auto text-xs text-zinc-500">
          共 {quizzes.length} 个测验 · 勾选后可批量删除草稿
        </span>
      </PageHeaderToolbar>

      {quizzesQuery.isLoading ? (
        <LoadingState label="正在加载测验列表..." />
      ) : quizzesQuery.isError ? (
        <ErrorState label={(quizzesQuery.error as Error)?.message || '测验列表加载失败'} />
      ) : (quizzesQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有随堂测验，点击「布置测验」开始。" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label="全选测验"
                    checked={quizzes.length > 0 && quizzes.every((q) => selectedQuizIds.includes(q.id))}
                    onChange={() => setSelectedQuizIds(quizzes.every((q) => selectedQuizIds.includes(q.id)) ? [] : quizzes.map((q) => q.id))}
                  />
                </th>
                <th className="px-4 py-3 font-medium">测验标题</th>
                <th className="px-4 py-3 font-medium">班级</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">创建时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {quizzes.map((quiz) => (
                <tr key={quiz.id} className={`transition-colors hover:bg-zinc-50 ${selectedQuizIds.includes(quiz.id) ? 'bg-blue-50/40' : ''}`}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      aria-label={`选择测验 ${quiz.title}`}
                      checked={selectedQuizIds.includes(quiz.id)}
                      onChange={() => toggleQuizSelect(quiz.id)}
                    />
                  </td>
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
                      {quiz.status === 'draft' ? (
                        <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50" disabled={deleteMutation.isPending} onClick={() => confirmDeleteQuiz(quiz)}>
                          <Trash2 size={13} /> 删除
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
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">布置随堂测验</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setFormOpen(false)}>✕</button>
            </div>
            <div className="mt-4 flex-1 space-y-3 overflow-auto">
              <label className="block text-xs text-zinc-500">
                测验标题
                <input className={`${inputClass} mt-1`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="例如：深度学习第 3 章随堂练习" />
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
              <div className="flex items-center gap-2">
                <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${sourceTab === 'bank' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSourceTab('bank')}>
                  从题库选题
                </button>
                <button type="button" className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${sourceTab === 'manual' ? 'bg-zinc-900 text-white' : 'text-zinc-600 hover:bg-zinc-100'}`} onClick={() => setSourceTab('manual')}>
                  手动出题
                </button>
                <span className="ml-auto text-xs text-zinc-500">已选 {selectedItems.length} 题</span>
              </div>
              {sourceTab === 'bank' ? (
                <>
                  <div className="flex items-center gap-2">
                    <select className={inputClass} value={bankFilter.question_type} onChange={(e) => setBankFilter({ ...bankFilter, question_type: e.target.value })}>
                      <option value="">全部题型</option>
                      <option value="single_choice">单选题</option>
                      <option value="multiple_choice">多选题</option>
                      <option value="true_false">判断题</option>
                      <option value="blank">填空题</option>
                    </select>
                    <input className={`${inputClass} flex-1`} placeholder="搜索题干关键词" value={bankFilter.keyword} onChange={(e) => setBankFilter({ ...bankFilter, keyword: e.target.value })} />
                    <button type="button" className={secondaryButtonClass} onClick={() => bankQuery.refetch()}>
                      <Loader2 size={14} className={bankQuery.isFetching ? 'animate-spin' : ''} /> 刷新
                    </button>
                  </div>
                  {bankQuery.isLoading ? (
                    <LoadingState label="正在加载题库..." />
                  ) : bankQuery.isError ? (
                    <ErrorState label={(bankQuery.error as Error)?.message || '题库加载失败'} />
                  ) : (
                    <div className="max-h-64 space-y-1 overflow-auto rounded-md border border-zinc-100 p-2">
                      {(bankQuery.data ?? []).map((item) => (
                        <label key={item.id} className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-2 transition-colors hover:bg-zinc-50">
                          <input type="checkbox" className="mt-0.5" checked={selectedItems.some((it) => it.id === item.id)} onChange={() => toggleSelected(item)} />
                          <span className="flex-1 text-sm text-zinc-800">{item.prompt}</span>
                          <span className="shrink-0 text-xs text-zinc-500">{questionTypeLabel(item.question_type)} · {item.score}分 · 答案{item.answer}</span>
                        </label>
                      ))}
                      {(bankQuery.data ?? []).length === 0 ? <p className="px-2 py-4 text-center text-xs text-zinc-400">题库暂无匹配题目</p> : null}
                    </div>
                  )}
                  {selectedItems.length > 0 ? (
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-zinc-500">已选题目（{selectedItems.length}）</div>
                      {selectedItems.map((item) => (
                        <div key={item.id} className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
                          <span className="flex-1 text-sm text-zinc-800">{item.prompt}</span>
                          <span className="shrink-0 text-xs text-zinc-500">{item.score}分</span>
                          <button type="button" className="shrink-0 text-xs text-red-500 hover:underline" onClick={() => toggleSelected(item)}>移除</button>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
              <>
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-zinc-500">手动题目（选择题填写选项，用逗号分隔；answer 填 A/B/C...）</span>
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
                          <option value="blank">填空题</option>
                        </select>
                        {question.question_type === 'blank' ? (
                          <input className={`${inputClass} col-span-2`} placeholder="题目中可留空，学生填答案" value={question.options} onChange={(e) => {
                            const next = [...form.questions];
                            next[index] = { ...next[index], options: e.target.value };
                            setForm({ ...form, questions: next });
                          }} />
                        ) : (
                          <input className={inputClass} placeholder={question.question_type === 'true_false' ? '正确,错误' : '选项，逗号分隔'} value={question.options} onChange={(e) => {
                            const next = [...form.questions];
                            next[index] = { ...next[index], options: e.target.value };
                            setForm({ ...form, questions: next });
                          }} />
                        )}
                        {question.question_type === 'true_false' ? (
                          <select className={inputClass} value={question.answer} onChange={(e) => {
                            const next = [...form.questions];
                            next[index] = { ...next[index], answer: e.target.value };
                            setForm({ ...form, questions: next });
                          }}>
                            <option value="T">T（正确）</option>
                            <option value="F">F（错误）</option>
                          </select>
                        ) : (
                          <input className={inputClass} placeholder={question.question_type === 'blank' ? '答案，如 ReLU' : '答案，如 B 或 A,C'} value={question.answer} onChange={(e) => {
                            const next = [...form.questions];
                            next[index] = { ...next[index], answer: e.target.value };
                            setForm({ ...form, questions: next });
                          }} />
                        )}
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
              </>
              )}
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setFormOpen(false)}>取消</button>
              <button
                type="button"
                className={primaryButtonClass}
                disabled={!form.title.trim() || !form.class_id || (selectedItems.length === 0 && form.questions.every((q) => !q.prompt.trim())) || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
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

      <WorkspaceToast toast={toast} onDismiss={() => setToast(null)} />
    </>
  );
}
