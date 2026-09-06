import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ClipboardList, Loader2, Send } from 'lucide-react';
import {
  studentGetAssignmentQuestions,
  studentListAssignments,
  studentSubmitAssignment,
  type StudentAssignment,
  type StudentAssignmentQuestion,
} from '../../api/ta';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

const questionTypeLabel = (type: string): string => {
  switch (type) {
    case 'single_choice': return '单选题';
    case 'multiple_choice': return '多选题';
    case 'true_false': return '判断题';
    case 'blank': return '填空题';
    case 'code': return '代码题';
    case 'short_answer': return '简答题';
    default: return '综合题';
  }
};

/** 判断某题是否已有作答（多选按选中集合判断） */
function isAnswered(question: StudentAssignmentQuestion, answer: string | undefined): boolean {
  if (question.question_type === 'multiple_choice') return Boolean(answer && answer.length > 0);
  return Boolean(answer && answer.trim().length > 0);
}

/**
 * 学生端课程作业：查看已发布作业，多题作业逐题作答（客观题提交后即时判分），
 * 单题旧作业沿用文本框提交（AI/人工批改）。
 */
export function StudentAssignmentsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [singleAnswer, setSingleAnswer] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{ score: number | null; message: string } | null>(null);

  const assignmentsQuery = useQuery({
    queryKey: ['student-assignments'],
    queryFn: () => studentListAssignments(),
  });
  const detailQuery = useQuery({
    queryKey: ['student-assignment-detail', activeId],
    queryFn: () => studentGetAssignmentQuestions(activeId ?? ''),
    enabled: Boolean(activeId),
  });

  const submitMutation = useMutation({
    mutationFn: () => {
      if (!activeId) return Promise.resolve(null);
      const detail = detailQuery.data;
      // 多题作业提交逐题作答；单题旧作业提交文本
      if (detail && detail.questions.length > 0) {
        return studentSubmitAssignment(activeId, { answers });
      }
      return studentSubmitAssignment(activeId, { answer: singleAnswer });
    },
    onSuccess: (result) => {
      if (!result) return;
      void queryClient.invalidateQueries({ queryKey: ['student-assignments'] });
      setLastResult({ score: result.score ?? null, message: result.message });
      setSubmitError(null);
    },
    onError: (error) => setSubmitError((error as Error).message),
  });

  const detail = detailQuery.data;
  const isMulti = Boolean(detail && detail.questions.length > 0);
  const allAnswered = isMulti
    ? (detail?.questions ?? []).every((q) => isAnswered(q, answers[q.id]))
    : singleAnswer.trim().length > 0;

  /** 更新单题作答（多选按字母集合存储，如 "A,C"） */
  function updateAnswer(questionId: string, value: string): void {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  function toggleMultiChoice(questionId: string, letter: string): void {
    const current = (answers[questionId] ?? '').split(',').filter(Boolean);
    const next = current.includes(letter) ? current.filter((it) => it !== letter) : [...current, letter];
    updateAnswer(questionId, next.sort().join(','));
  }

  function openDetail(item: StudentAssignment): void {
    setActiveId(item.id);
    setAnswers({});
    setSingleAnswer('');
    setSubmitError(null);
    setLastResult(null);
  }

  return (
    <OverlayPageShell title="课程作业" subtitle="查看助教布置的作业，按时完成并提交作答。" pageClassName="student-assignments-page">
      {!activeId ? (
        <>
          <PageHeaderToolbar>
            <button type="button" className={secondaryButtonClass} onClick={() => assignmentsQuery.refetch()}>
              <Loader2 size={15} className={assignmentsQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </PageHeaderToolbar>

          {assignmentsQuery.isLoading ? (
            <LoadingState label="正在加载作业列表..." />
          ) : assignmentsQuery.isError ? (
            <ErrorState label={(assignmentsQuery.error as Error)?.message || '作业列表加载失败'} />
          ) : (assignmentsQuery.data ?? []).length === 0 ? (
            <EmptyState label="暂无已发布的作业，等待助教布置。" />
          ) : (
            <ul className="space-y-3">
              {(assignmentsQuery.data ?? []).map((item) => (
                <li key={item.id} className="rounded-lg border border-zinc-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <ClipboardList size={15} className="shrink-0 text-zinc-400" />
                      <div>
                        <div className="text-sm font-semibold text-zinc-900">{item.title}</div>
                        <div className="mt-0.5 text-xs text-zinc-400">
                          {item.question_type === 'multi' ? `多题作业 · ${item.question_count} 题` : questionTypeLabel(item.question_type)}
                          {' · '}满分 {item.total_score} · 截止 {formatBeijingDateTimeCompact(item.due_at, '未设置')}
                        </div>
                      </div>
                    </div>
                    {item.submitted ? (
                      <span className="flex shrink-0 items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
                        <CheckCircle2 size={12} /> 已提交{item.score != null ? ` · ${item.score} 分` : ''}
                      </span>
                    ) : (
                      <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">待提交</span>
                    )}
                  </div>
                  {item.description ? <p className="mt-2 text-sm text-zinc-600">{item.description}</p> : null}
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-zinc-400">
                      {item.submitted ? `已提交 ${item.attempt_number} 次 · ${formatBeijingDateTimeCompact(item.submitted_at, '—')}` : '尚未提交'}
                    </span>
                    <button
                      type="button"
                      className={item.submitted ? secondaryButtonClass : primaryButtonClass}
                      onClick={() => openDetail(item)}
                    >
                      {item.submitted ? '重新提交' : '去提交'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div>
          <button type="button" className={secondaryButtonClass} onClick={() => setActiveId(null)}>← 返回作业列表</button>

          {detailQuery.isLoading ? (
            <div className="mt-4"><LoadingState label="正在加载题目..." /></div>
          ) : detailQuery.isError ? (
            <div className="mt-4"><ErrorState label={(detailQuery.error as Error)?.message || '题目加载失败'} /></div>
          ) : (
            <div className="mt-4 space-y-3">
              {isMulti ? (
                // 多题作业：逐题作答，客观题提交后即时判分
                (detail?.questions ?? []).map((question, index) => (
                  <div key={question.id} className="rounded-lg border border-zinc-200 bg-white p-4">
                    <div className="text-sm font-medium text-zinc-900">
                      {index + 1}. {question.prompt} <span className="ml-1 text-xs font-normal text-zinc-400">（{questionTypeLabel(question.question_type)} · {question.score} 分）</span>
                    </div>
                    <div className="mt-3 space-y-2">
                      {question.question_type === 'single_choice' || question.question_type === 'true_false' ? (
                        (question.options ?? []).map((option, optionIndex) => {
                          const letter = String.fromCharCode(65 + optionIndex);
                          return (
                            <label key={`${question.id}-${optionIndex}`} className="flex cursor-pointer items-center gap-2 rounded-md border border-zinc-100 px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50">
                              <input
                                type="radio"
                                name={question.id}
                                value={letter}
                                checked={answers[question.id] === letter}
                                onChange={() => updateAnswer(question.id, letter)}
                              />
                              <span className="font-medium text-zinc-400">{letter}.</span>
                              {option}
                            </label>
                          );
                        })
                      ) : question.question_type === 'multiple_choice' ? (
                        (question.options ?? []).map((option, optionIndex) => {
                          const letter = String.fromCharCode(65 + optionIndex);
                          const selected = (answers[question.id] ?? '').split(',').filter(Boolean).includes(letter);
                          return (
                            <label key={`${question.id}-${optionIndex}`} className="flex cursor-pointer items-center gap-2 rounded-md border border-zinc-100 px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50">
                              <input
                                type="checkbox"
                                checked={selected}
                                onChange={() => toggleMultiChoice(question.id, letter)}
                              />
                              <span className="font-medium text-zinc-400">{letter}.</span>
                              {option}
                            </label>
                          );
                        })
                      ) : question.question_type === 'blank' ? (
                        <input
                          className={inputClass}
                          placeholder="填写答案"
                          value={answers[question.id] ?? ''}
                          onChange={(e) => updateAnswer(question.id, e.target.value)}
                        />
                      ) : (
                        <textarea
                          className={inputClass}
                          rows={4}
                          placeholder={question.question_type === 'code' ? '在此编写代码...' : '在此写下你的作答...'}
                          value={answers[question.id] ?? ''}
                          onChange={(e) => updateAnswer(question.id, e.target.value)}
                        />
                      )}
                    </div>
                  </div>
                ))
              ) : (
                // 单题旧作业：判断/单选或文本框提交
                <div className="rounded-lg border border-zinc-200 bg-white p-4">
                  <div className="text-sm font-medium text-zinc-900">
                    {questionTypeLabel(detail?.question_type ?? '')} <span className="ml-1 text-xs font-normal text-zinc-400">（满分 {detail?.total_score}）</span>
                  </div>
                  {detail?.question_type === 'true_false' ? (
                    <div className="mt-3 space-y-2">
                      {['正确', '错误'].map((label, index) => (
                        <label key={label} className="flex cursor-pointer items-center gap-2 rounded-md border border-zinc-100 px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50">
                          <input type="radio" name="tf-answer" className="accent-zinc-900" checked={singleAnswer === ['T', 'F'][index]} onChange={() => setSingleAnswer(['T', 'F'][index])} />
                          <span className="text-sm text-zinc-800">{label}</span>
                        </label>
                      ))}
                    </div>
                  ) : detail?.question_type === 'single_choice' ? (
                    <div className="mt-3 space-y-2">
                      {(detail.options ?? []).map((option, index) => (
                        <label key={`${detail.id}-${index}`} className="flex cursor-pointer items-start gap-2 rounded-md border border-zinc-100 px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50">
                          <input type="radio" name="choice-answer" className="mt-0.5 accent-zinc-900" checked={singleAnswer === 'ABCDEFGHIJ'[index]} onChange={() => setSingleAnswer('ABCDEFGHIJ'[index])} />
                          <span className="text-sm text-zinc-800">{option}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <textarea className={`${inputClass} mt-3`} rows={10} placeholder="在这里写下你的作答..." value={singleAnswer} onChange={(e) => setSingleAnswer(e.target.value)} />
                  )}
                </div>
              )}
              {submitError ? <p className="text-xs text-red-600">{submitError}</p> : null}
              {lastResult ? (
                <p className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                  {lastResult.message}
                  {lastResult.score != null ? ` 得分 ${lastResult.score} 分。` : ' 得分待批改。'}
                </p>
              ) : null}
              <div className="flex justify-end">
                <button
                  type="button"
                  className={primaryButtonClass}
                  disabled={!allAnswered || submitMutation.isPending}
                  onClick={() => submitMutation.mutate()}
                >
                  {submitMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} 提交作业
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </OverlayPageShell>
  );
}
