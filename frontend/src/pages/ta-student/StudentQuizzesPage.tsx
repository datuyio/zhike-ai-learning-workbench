import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, HelpCircle, Loader2, Send } from 'lucide-react';
import { studentGetQuizQuestions, studentListQuizzes, studentSubmitQuiz } from '../../api/ta';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';

type StudentQuiz = { id: string; title: string; description: string | null; created_at: string | null; submitted: boolean; score: number | null };
type QuizQuestion = { id: string; prompt: string; question_type: string; options: string[] | null; score: number };
type QuizDetail = { id: string; title: string; description: string | null; questions: QuizQuestion[] };

const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

/**
 * 学生端随堂测验：在线作答客观题并即时查看得分。
 */
export function StudentQuizzesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastScore, setLastScore] = useState<number | null>(null);

  const quizzesQuery = useQuery({ queryKey: ['student-quizzes'], queryFn: () => studentListQuizzes() });
  const detailQuery = useQuery({
    queryKey: ['student-quiz-detail', activeId],
    queryFn: () => studentGetQuizQuestions(activeId ?? ''),
    enabled: Boolean(activeId),
  });

  const submitMutation = useMutation({
    mutationFn: () => studentSubmitQuiz(activeId ?? '', answers),
    onSuccess: (result) => {
      setLastScore(result.score ?? null);
      void queryClient.invalidateQueries({ queryKey: ['student-quizzes'] });
      setSubmitError(null);
    },
    onError: (error) => setSubmitError((error as Error).message),
  });

  const detail: QuizDetail | undefined = detailQuery.data;

  return (
    <OverlayPageShell title="随堂测验" subtitle="完成助教发布的随堂测验，客观题提交后即时判分。" pageClassName="student-quizzes-page">
      {!activeId ? (
        <>
          <PageHeaderToolbar>
            <button type="button" className={secondaryButtonClass} onClick={() => quizzesQuery.refetch()}>
              <Loader2 size={15} className={quizzesQuery.isFetching ? 'animate-spin' : ''} /> 刷新
            </button>
          </PageHeaderToolbar>

          {quizzesQuery.isLoading ? (
            <LoadingState label="正在加载测验列表..." />
          ) : quizzesQuery.isError ? (
            <ErrorState label={(quizzesQuery.error as Error)?.message || '测验列表加载失败'} />
          ) : (quizzesQuery.data ?? []).length === 0 ? (
            <EmptyState label="暂无已发布的随堂测验，等待助教发布。" />
          ) : (
            <ul className="space-y-3">
              {(quizzesQuery.data ?? []).map((quiz: StudentQuiz) => (
                <li key={quiz.id} className="flex items-center justify-between gap-4 rounded-lg border border-zinc-200 bg-white p-4">
                  <div className="flex items-center gap-2">
                    <HelpCircle size={15} className="shrink-0 text-zinc-400" />
                    <div>
                      <div className="text-sm font-semibold text-zinc-900">{quiz.title}</div>
                      {quiz.description ? <div className="mt-0.5 text-xs text-zinc-500">{quiz.description}</div> : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    {quiz.submitted ? (
                      <span className="flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
                        <CheckCircle2 size={12} /> 已提交 · {quiz.score ?? '—'} 分
                      </span>
                    ) : (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">待作答</span>
                    )}
                    <button
                      type="button"
                      className={quiz.submitted ? secondaryButtonClass : primaryButtonClass}
                      onClick={() => { setActiveId(quiz.id); setAnswers({}); setSubmitError(null); setLastScore(null); }}
                    >
                      {quiz.submitted ? '重新作答' : '开始作答'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div>
          <button type="button" className={secondaryButtonClass} onClick={() => setActiveId(null)}>← 返回测验列表</button>

          {detailQuery.isLoading ? (
            <div className="mt-4"><LoadingState label="正在加载题目..." /></div>
          ) : detailQuery.isError ? (
            <div className="mt-4"><ErrorState label={(detailQuery.error as Error)?.message || '题目加载失败'} /></div>
          ) : (
            <div className="mt-4 space-y-3">
              {detail?.questions.map((question, index) => (
                <div key={question.id} className="rounded-lg border border-zinc-200 bg-white p-4">
                  <div className="text-sm font-medium text-zinc-900">
                    {index + 1}. {question.prompt} <span className="ml-1 text-xs font-normal text-zinc-400">（{question.score} 分）</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {(question.options ?? []).map((option, optionIndex) => {
                      const letter = String.fromCharCode(65 + optionIndex);
                      return (
                        <label key={`${question.id}-${optionIndex}`} className="flex cursor-pointer items-center gap-2 rounded-md border border-zinc-100 px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-50">
                          <input
                            type="radio"
                            name={question.id}
                            value={letter}
                            checked={answers[question.id] === letter}
                            onChange={() => setAnswers({ ...answers, [question.id]: letter })}
                          />
                          <span className="font-medium text-zinc-400">{letter}.</span>
                          {option}
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
              {submitError ? <p className="text-xs text-red-600">{submitError}</p> : null}
              {lastScore != null ? <p className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">已提交，得分 {lastScore} 分。</p> : null}
              <div className="flex justify-end">
                <button
                  type="button"
                  className={primaryButtonClass}
                  disabled={submitMutation.isPending || Object.keys(answers).length !== (detail?.questions.length ?? 0)}
                  onClick={() => submitMutation.mutate()}
                >
                  {submitMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} 提交测验
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </OverlayPageShell>
  );
}
