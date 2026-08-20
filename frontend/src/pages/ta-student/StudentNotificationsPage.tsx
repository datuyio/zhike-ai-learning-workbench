import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BellRing, Loader2 } from 'lucide-react';
import { studentListNotifications, studentReadNotification } from '../../api/ta';
import { OverlayPageShell } from '../../components/shared/OverlayPageShell';
import { PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

/**
 * 学生端消息通知：助教预警提醒、作业与测验通知收件箱。
 */
export function StudentNotificationsPage(): JSX.Element {
  const queryClient = useQueryClient();

  const notificationsQuery = useQuery({
    queryKey: ['student-notifications'],
    queryFn: () => studentListNotifications(),
  });

  const readMutation = useMutation({
    mutationFn: (notificationId: string) => studentReadNotification(notificationId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['student-notifications'] }),
  });

  const items = notificationsQuery.data?.items ?? [];
  const unreadCount = notificationsQuery.data?.unread_count ?? 0;

  return (
    <OverlayPageShell title="消息通知" subtitle="接收助教的学习提醒、作业与测验通知，及时掌握最新安排。">
      <PageHeaderToolbar>
        <button type="button" className={secondaryButtonClass} onClick={() => notificationsQuery.refetch()}>
          <Loader2 size={15} className={notificationsQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
        <span className="text-xs text-zinc-500">未读 {unreadCount} 条</span>
      </PageHeaderToolbar>

      {notificationsQuery.isLoading ? (
        <LoadingState label="正在加载通知..." />
      ) : notificationsQuery.isError ? (
        <ErrorState label={(notificationsQuery.error as Error)?.message || '通知加载失败'} />
      ) : items.length === 0 ? (
        <EmptyState label="暂无通知" />
      ) : (
        <ul className="space-y-2">
          {items.map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                className={`flex w-full items-start gap-3 rounded-lg border p-4 text-left transition-colors ${notification.is_read ? 'border-zinc-100 bg-white' : 'border-blue-100 bg-blue-50/50'}`}
                onClick={() => {
                  if (!notification.is_read) readMutation.mutate(notification.id);
                }}
              >
                <BellRing size={15} className={`mt-0.5 shrink-0 ${notification.is_read ? 'text-zinc-300' : 'text-blue-500'}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-zinc-900">{notification.title}</span>
                    {!notification.is_read ? <span className="shrink-0 h-1.5 w-1.5 rounded-full bg-blue-500" /> : null}
                  </div>
                  <p className="mt-1 text-sm text-zinc-600">{notification.body}</p>
                  <div className="mt-1.5 text-xs text-zinc-400">{formatBeijingDateTimeCompact(notification.created_at, '—')}</div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </OverlayPageShell>
  );
}
