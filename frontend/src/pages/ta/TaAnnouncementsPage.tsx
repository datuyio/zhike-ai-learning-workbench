import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Megaphone, Pencil, Pin, PinOff, Plus, Trash2, XCircle } from 'lucide-react';
import {
  taCreateAnnouncement, taDeleteAnnouncement, taListAnnouncements, taListClasses, taPinAnnouncement,
  taUpdateAnnouncement, taWithdrawAnnouncement, type TaAnnouncement,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type AnnouncementForm = { title: string; body: string; announcement_type: string; class_ids: string[] };

/**
 * 公告通知：面向班级发布公告，支持置顶与撤回。
 */
export function TaAnnouncementsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TaAnnouncement | null>(null);
  const [form, setForm] = useState<AnnouncementForm>({ title: '', body: '', announcement_type: 'general', class_ids: [] });
  const [formError, setFormError] = useState<string | null>(null);

  const announcementsQuery = useQuery({ queryKey: ['ta-announcements'], queryFn: () => taListAnnouncements() });
  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['ta-announcements'] });

  const saveMutation = useMutation<unknown, Error, void>({
    mutationFn: () => (editing
      ? taUpdateAnnouncement(editing.id, { title: form.title, body: form.body, announcement_type: form.announcement_type })
      : taCreateAnnouncement({ title: form.title, body: form.body, announcement_type: form.announcement_type, class_ids: form.class_ids })),
    onSuccess: () => { invalidate(); setFormOpen(false); setFormError(null); },
    onError: (error) => setFormError(error.message),
  });

  const deleteMutation = useMutation({ mutationFn: (id: string) => taDeleteAnnouncement(id), onSuccess: () => invalidate() });
  const pinMutation = useMutation({ mutationFn: (id: string) => taPinAnnouncement(id), onSuccess: () => invalidate() });
  const withdrawMutation = useMutation({ mutationFn: (id: string) => taWithdrawAnnouncement(id), onSuccess: () => invalidate() });

  function openCreate(): void {
    setEditing(null);
    setForm({ title: '', body: '', announcement_type: 'general', class_ids: [] });
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(item: TaAnnouncement): void {
    setEditing(item);
    setForm({ title: item.title, body: item.body, announcement_type: item.announcement_type, class_ids: [] });
    setFormError(null);
    setFormOpen(true);
  }

  function toggleClass(classId: string): void {
    setForm((prev) => ({
      ...prev,
      class_ids: prev.class_ids.includes(classId)
        ? prev.class_ids.filter((id) => id !== classId)
        : [...prev.class_ids, classId],
    }));
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="公告通知" subtitle="向所带班级发布学习公告，重要公告可置顶，过期公告可撤回。" />

      <PageHeaderToolbar>
        <button type="button" className={primaryButtonClass} onClick={openCreate}>
          <Plus size={15} /> 发布公告
        </button>
        <button type="button" className={secondaryButtonClass} onClick={() => announcementsQuery.refetch()}>
          <Loader2 size={15} className={announcementsQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
      </PageHeaderToolbar>

      {announcementsQuery.isLoading ? (
        <LoadingState label="正在加载公告列表..." />
      ) : announcementsQuery.isError ? (
        <ErrorState label={(announcementsQuery.error as Error)?.message || '公告列表加载失败'} />
      ) : (announcementsQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有公告，点击「发布公告」开始。" />
      ) : (
        <ul className="space-y-3">
          {(announcementsQuery.data ?? []).map((item) => (
            <li key={item.id} className={`rounded-lg border bg-white p-4 ${item.is_active ? 'border-zinc-200' : 'border-zinc-100 opacity-70'}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Megaphone size={15} className="shrink-0 text-zinc-400" />
                    <span className="truncate text-sm font-semibold text-zinc-900">{item.title}</span>
                    {item.is_pinned ? <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">置顶</span> : null}
                    {!item.is_active ? <span className="shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-500">已撤回</span> : null}
                  </div>
                  <p className="mt-1.5 whitespace-pre-wrap text-sm text-zinc-600">{item.body}</p>
                  <div className="mt-2 text-xs text-zinc-400">{item.announcement_type} · {item.class_name ?? '全体'} · {formatBeijingDateTimeCompact(item.created_at, '—')}</div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {item.is_active ? (
                    <>
                      <button type="button" title={item.is_pinned ? '取消置顶' : '置顶'} className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => pinMutation.mutate(item.id)}>
                        {item.is_pinned ? <PinOff size={15} /> : <Pin size={15} />}
                      </button>
                      <button type="button" title="编辑" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => openEdit(item)}>
                        <Pencil size={15} />
                      </button>
                      <button type="button" title="撤回" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => withdrawMutation.mutate(item.id)}>
                        <XCircle size={15} />
                      </button>
                    </>
                  ) : null}
                  <button type="button" title="删除" className="rounded-md p-1.5 text-zinc-500 hover:bg-red-50 hover:text-red-600" onClick={() => {
                    if (window.confirm(`确定删除公告「${item.title}」吗？`)) deleteMutation.mutate(item.id);
                  }}>
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {formOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">{editing ? '编辑公告' : '发布公告'}</h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs text-zinc-500">
                标题
                <input className={`${inputClass} mt-1`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                内容
                <textarea className={`${inputClass} mt-1`} rows={6} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                类型
                <select className={`${inputClass} mt-1`} value={form.announcement_type} onChange={(e) => setForm({ ...form, announcement_type: e.target.value })}>
                  <option value="general">一般通知</option>
                  <option value="homework">作业通知</option>
                  <option value="exam">考试通知</option>
                </select>
              </label>
              {!editing ? (
                <div className="text-xs text-zinc-500">
                  <span className="mb-1.5 block">目标班级（不选择则发送给全体学生）</span>
                  {classesQuery.isLoading ? (
                    <p className="text-zinc-400">正在加载班级...</p>
                  ) : classesQuery.isError ? (
                    <p className="text-red-600">班级列表加载失败</p>
                  ) : (classesQuery.data ?? []).length === 0 ? (
                    <p className="text-zinc-400">暂无班级，将发送给全体学生</p>
                  ) : (
                    <div className="mt-1 max-h-44 space-y-0.5 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-1.5">
                      {(classesQuery.data ?? []).map((cls) => {
                        const checked = form.class_ids.includes(cls.id);
                        return (
                          <label key={cls.id} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-zinc-100">
                            <input
                              type="checkbox"
                              className="h-3.5 w-3.5 accent-zinc-900"
                              checked={checked}
                              onChange={() => toggleClass(cls.id)}
                            />
                            <span className="flex-1 truncate text-zinc-700">{cls.name}</span>
                            <span className="text-xs text-zinc-400">{cls.student_count} 人</span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : null}
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setFormOpen(false)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!form.title.trim() || !form.body.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                {saveMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} {editing ? '保存' : '发布'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
