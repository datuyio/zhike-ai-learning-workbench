import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound, Loader2, LogOut, RefreshCw, Send, Users } from 'lucide-react';
import { studentJoinClass, studentLeaveClass, studentListMyClasses, type StudentClass } from '../../api/ta';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

/**
 * 学生端「我的班级」：凭邀请码加入老师创建的班级，查看班内信息或退出班级。
 */
export function StudentClassesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [inviteCode, setInviteCode] = useState('');
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joinSuccess, setJoinSuccess] = useState<string | null>(null);

  const classesQuery = useQuery({ queryKey: ['student-my-classes'], queryFn: () => studentListMyClasses() });

  const joinMutation = useMutation({
    mutationFn: (code: string) => studentJoinClass(code),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['student-my-classes'] });
      setInviteCode('');
      setJoinError(null);
      setJoinSuccess(result.already_member ? `你已在「${result.class.name}」中。` : `已加入「${result.class.name}」。`);
    },
    onError: (error) => {
      setJoinSuccess(null);
      setJoinError((error as Error).message);
    },
  });

  const leaveMutation = useMutation({
    mutationFn: (classId: string) => studentLeaveClass(classId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['student-my-classes'] });
      setJoinError(null);
    },
    onError: (error) => {
      setJoinSuccess(null);
      setJoinError((error as Error).message);
    },
  });

  function submitJoin(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setJoinSuccess(null);
    const code = inviteCode.trim();
    if (!code) {
      setJoinError('请输入老师提供的班级邀请码。');
      return;
    }
    setJoinError(null);
    joinMutation.mutate(code);
  }

  async function copyInvite(code: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      window.prompt('请手动复制邀请码', code);
    }
  }

  return (
    <OverlayPageShell title="我的班级" subtitle="凭老师提供的邀请码加入班级，查看班级信息、邀请码与入班时间。" pageClassName="student-classes-page">
      <PageHeaderToolbar>
        <button type="button" className={secondaryButtonClass} onClick={() => classesQuery.refetch()}>
          <RefreshCw size={15} className={classesQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
      </PageHeaderToolbar>

      <form onSubmit={(event) => void submitJoin(event)} className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
          <KeyRound size={15} className="text-zinc-400" /> 加入班级
        </div>
        <div className="mt-3 flex gap-2">
          <input
            className={inputClass}
            value={inviteCode}
            placeholder="输入 8 位班级邀请码，例如 HXF7YC4S"
            onChange={(event) => setInviteCode(event.target.value.toUpperCase())}
          />
          <button type="submit" className={primaryButtonClass} disabled={!inviteCode.trim() || joinMutation.isPending}>
            {joinMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} 加入
          </button>
        </div>
        {joinError ? <p className="mt-2 text-xs text-red-600">{joinError}</p> : null}
        {joinSuccess ? <p className="mt-2 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{joinSuccess}</p> : null}
      </form>

      <div className="mt-4">
        {classesQuery.isLoading ? (
          <LoadingState label="正在加载我的班级..." />
        ) : classesQuery.isError ? (
          <ErrorState label={(classesQuery.error as Error)?.message || '班级数据加载失败'} />
        ) : (classesQuery.data ?? []).length === 0 ? (
          <EmptyState label="还没有加入任何班级，向上输入邀请码加入老师创建的班级。" />
        ) : (
          <ul className="space-y-3">
            {(classesQuery.data ?? []).map((item: StudentClass) => (
              <li key={item.id} className="rounded-lg border border-zinc-200 bg-white p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Users size={15} className="shrink-0 text-zinc-400" />
                      <span className="truncate text-sm font-semibold text-zinc-900">{item.name}</span>
                    </div>
                    {item.description ? <div className="mt-0.5 text-xs text-zinc-500">{item.description}</div> : null}
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                      <span>老师：{item.ta_name ?? '—'}</span>
                      <span>班内学生：{item.student_count}{item.max_students != null ? ` / ${item.max_students}` : ''}</span>
                      <span>入班时间：{formatBeijingDateTimeCompact(item.joined_at, '—')}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    disabled={leaveMutation.isPending}
                    onClick={() => {
                      if (window.confirm(`确定退出班级「${item.name}」吗？`)) leaveMutation.mutate(item.id);
                    }}
                  >
                    <span className="inline-flex items-center gap-1">
                      <LogOut size={13} /> 退出班级
                    </span>
                  </button>
                </div>
                <div className="mt-3 flex items-center gap-2 border-t border-zinc-100 pt-3">
                  <span className="text-xs text-zinc-400">班级邀请码</span>
                  <span className="font-mono text-xs tracking-widest text-zinc-700">{item.invite_code}</span>
                  <button type="button" className="inline-flex items-center gap-1 rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-50" onClick={() => void copyInvite(item.invite_code)}>
                    <Copy size={12} /> 复制
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </OverlayPageShell>
  );
}
