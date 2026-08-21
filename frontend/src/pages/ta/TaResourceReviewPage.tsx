import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { taApproveResource, taPendingResources, taRejectResource } from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type PendingResource = { id: string; title: string; resource_type: string; status: string; created_at: string | null; description?: string | null };

/**
 * 资源审核：处理学生端提交的资源审核流（通过 / 驳回）。
 */
export function TaResourceReviewPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState<PendingResource | null>(null);
  const [rejectComment, setRejectComment] = useState('');

  const resourcesQuery = useQuery({ queryKey: ['ta-pending-resources'], queryFn: () => taPendingResources() });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['ta-pending-resources'] });

  const approveMutation = useMutation({
    mutationFn: (resourceId: string) => taApproveResource(resourceId),
    onSuccess: () => invalidate(),
  });

  const rejectMutation = useMutation({
    mutationFn: () => (rejecting ? taRejectResource(rejecting.id, rejectComment) : Promise.resolve({ message: '' })),
    onSuccess: () => { invalidate(); setRejecting(null); setRejectComment(''); },
  });

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="资源审核" subtitle="审核学生端提交的学习资源，通过后进入资源大厅，驳回时给出理由。" />

      <PageHeaderToolbar>
        <button type="button" className={secondaryButtonClass} onClick={() => resourcesQuery.refetch()}>
          <Loader2 size={15} className={resourcesQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
        <span className="text-xs text-zinc-500">待审核 {resourcesQuery.data?.length ?? 0} 条</span>
      </PageHeaderToolbar>

      {resourcesQuery.isLoading ? (
        <LoadingState label="正在加载待审核资源..." />
      ) : resourcesQuery.isError ? (
        <ErrorState label={(resourcesQuery.error as Error)?.message || '待审核资源加载失败'} />
      ) : (resourcesQuery.data ?? []).length === 0 ? (
        <EmptyState label="暂无待审核资源" />
      ) : (
        <ul className="space-y-3">
          {(resourcesQuery.data ?? []).map((resource) => (
            <li key={resource.id} className="flex items-center justify-between gap-4 rounded-lg border border-zinc-200 bg-white p-4">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-zinc-900">{resource.title}</div>
                <div className="mt-0.5 text-xs text-zinc-400">
                  {resource.resource_type} · {formatBeijingDateTimeCompact(resource.created_at, '—')}
                </div>
                {resource.description ? <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{resource.description}</p> : null}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button type="button" className="inline-flex items-center gap-1 rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600" disabled={approveMutation.isPending} onClick={() => approveMutation.mutate(resource.id)}>
                  <CheckCircle2 size={14} /> 通过
                </button>
                <button type="button" className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50" onClick={() => { setRejecting(resource); setRejectComment(''); }}>
                  <XCircle size={14} /> 驳回
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {rejecting ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">驳回资源 · {rejecting.title}</h3>
            <textarea
              className="mt-4 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
              rows={4}
              placeholder="驳回理由（选填）"
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setRejecting(null)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={rejectMutation.isPending} onClick={() => rejectMutation.mutate()}>
                {rejectMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 确认驳回
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
