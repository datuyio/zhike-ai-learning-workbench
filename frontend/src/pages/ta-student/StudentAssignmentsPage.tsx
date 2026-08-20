import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardList, Loader2, Send } from 'lucide-react';
import { studentListAssignments, studentSubmitAssignment } from '../../api/ta';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

type StudentAssignment = {
  id: string;
  title: string;
  description: string | null;
  total_score: number;
  due_at: string | null;
  late_policy: string;
  status: string;
  created_at: string | null;
  submitted: boolean;
  attempt_number: number;
  submitted_at: string | null;
};

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

/**
 * 学生端课程作业：查看已发布作业、在线提交作答与重交。
 */
export function StudentAssignmentsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [active, setActive] = useState<StudentAssignment | null>(null);
  const [answer, setAnswer] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);

  const assignmentsQuery = useQuery({
    queryKey: ['student-assignments'],
    queryFn: () => studentListAssignments(),
  });

  const submitMutation = useMutation({
    mutationFn: () => (active ? studentSubmitAssignment(active.id, answer) : Promise.resolve(null)),
    onSuccess: (result) => {
      if (!result) return;
      void queryClient.invalidateQueries({ queryKey: ['student-assignments'] });
      setActive(null);
      setAnswer('');
      setSubmitError(null);
    },
    onError: (error) => setSubmitError((error as Error).message),
  });

  return (
    <OverlayPageShell title="课程作业" subtitle="查看助教布置的作业，按时完成并提交作答。">
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
                      满分 {item.total_score} · 截止 {formatBeijingDateTimeCompact(item.due_at, '未设置')}
                    </div>
                  </div>
                </div>
                {item.submitted ? (
                  <span className="shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">已提交</span>
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
                  onClick={() => { setActive(item); setAnswer(''); setSubmitError(null); }}
                >
                  {item.submitted ? '重新提交' : '去提交'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {active ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">{active.title}</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setActive(null)}>✕</button>
            </div>
            <div className="mt-4 flex-1 overflow-auto">
              <textarea className={inputClass} rows={10} placeholder="在这里写下你的作答..." value={answer} onChange={(e) => setAnswer(e.target.value)} />
              {submitError ? <p className="mt-2 text-xs text-red-600">{submitError}</p> : null}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setActive(null)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!answer.trim() || submitMutation.isPending} onClick={() => submitMutation.mutate()}>
                {submitMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} 提交作业
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </OverlayPageShell>
  );
}
