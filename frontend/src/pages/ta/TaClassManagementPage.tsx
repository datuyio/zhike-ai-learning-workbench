import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Download, Loader2, Pencil, Plus, RefreshCw, Trash2, Users } from 'lucide-react';
import {
  taAddStudent, taCreateClass, taDeleteClass, taExportClassGradesCsv, taListClasses,
  taListClassStudents, taRegenerateClassCode, taRemoveStudent, taUpdateClass, type TaClass, type TaStudent,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';
import { formatBeijingDateTimeCompact } from '../../utils/formatDateTime';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type ClassForm = { name: string; description: string; max_students: string };

/**
 * 班级管理：班级增删改、学生名单维护与成绩导出。
 */
export function TaClassManagementPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TaClass | null>(null);
  const [form, setForm] = useState<ClassForm>({ name: '', description: '', max_students: '' });
  const [studentDrawer, setStudentDrawer] = useState<TaClass | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [createdInvite, setCreatedInvite] = useState<{ name: string; code: string } | null>(null);

  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });

  const saveMutation = useMutation({
    mutationFn: async (): Promise<{ id: string; invite_code?: string }> => {
      if (editing) {
        return taUpdateClass(editing.id, {
          name: form.name,
          description: form.description || null,
          max_students: form.max_students ? Number(form.max_students) : null,
        });
      }
      return taCreateClass({
        name: form.name,
        description: form.description || null,
        max_students: form.max_students ? Number(form.max_students) : null,
      });
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['ta-classes'] });
      if (!editing && result.invite_code) {
        setCreatedInvite({ name: form.name.trim(), code: result.invite_code });
      }
      setFormOpen(false);
      setFormError(null);
    },
    onError: (error) => setFormError((error as Error).message),
  });

  const deleteMutation = useMutation({
    mutationFn: (classId: string) => taDeleteClass(classId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['ta-classes'] }),
  });

  const regenerateMutation = useMutation({
    mutationFn: (classId: string) => taRegenerateClassCode(classId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['ta-classes'] });
      const cachedClasses = queryClient.getQueryData<TaClass[]>(['ta-classes']) ?? [];
      const found = cachedClasses.find((item) => item.id === result.id);
      setCreatedInvite({ name: found?.name ?? '班级', code: result.invite_code });
    },
  });

  function openCreate(): void {
    setEditing(null);
    setForm({ name: '', description: '', max_students: '' });
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(item: TaClass): void {
    setEditing(item);
    setForm({
      name: item.name,
      description: item.description ?? '',
      max_students: item.max_students != null ? String(item.max_students) : '',
    });
    setFormError(null);
    setFormOpen(true);
  }

  async function exportGrades(item: TaClass): Promise<void> {
    try {
      const blob = await taExportClassGradesCsv(item.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${item.name}-成绩.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // 导出失败静默交由全局错误提示处理
    }
  }

  async function copyInvite(code: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // 剪贴板不可用时提示用户手动复制
      window.prompt('请手动复制邀请码', code);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="班级管理" subtitle="维护助教所带班级、学生名单，并导出班级成绩清单。" />

      <PageHeaderToolbar>
        <button type="button" className={primaryButtonClass} onClick={openCreate}>
          <Plus size={15} /> 新建班级
        </button>
        <button type="button" className={secondaryButtonClass} onClick={() => classesQuery.refetch()}>
          <Loader2 size={15} className={classesQuery.isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
      </PageHeaderToolbar>

      {createdInvite ? (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <span>
            「{createdInvite.name}」邀请码已生成：<strong className="font-mono tracking-widest">{createdInvite.code}</strong>
            ，学生凭此码即可加入班级。
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-white px-2.5 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100" onClick={() => void copyInvite(createdInvite.code)}>
              <Copy size={13} /> 复制
            </button>
            <button type="button" className="rounded-md px-2 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100" onClick={() => setCreatedInvite(null)}>✕</button>
          </div>
        </div>
      ) : null}

      {classesQuery.isLoading ? (
        <LoadingState label="正在加载班级数据..." />
      ) : classesQuery.isError ? (
        <ErrorState label={(classesQuery.error as Error)?.message || '班级数据加载失败'} />
      ) : (classesQuery.data ?? []).length === 0 ? (
        <EmptyState label="还没有班级，点击「新建班级」开始。" />
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">班级名称</th>
                <th className="px-4 py-3 font-medium">邀请码</th>
                <th className="px-4 py-3 font-medium">学生数</th>
                <th className="px-4 py-3 font-medium">容量上限</th>
                <th className="px-4 py-3 font-medium">创建时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {(classesQuery.data ?? []).map((item) => (
                <tr key={item.id} className="transition-colors hover:bg-zinc-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-zinc-900">{item.name}</div>
                    {item.description ? <div className="text-xs text-zinc-400">{item.description}</div> : null}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs tracking-widest text-zinc-700">{item.invite_code}</span>
                      <button type="button" title="复制邀请码" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600" onClick={() => void copyInvite(item.invite_code)}>
                        <Copy size={13} />
                      </button>
                      <button
                        type="button"
                        title="重置邀请码"
                        className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
                        disabled={regenerateMutation.isPending}
                        onClick={() => {
                          if (window.confirm(`确定重置「${item.name}」的邀请码吗？旧码将立即失效。`)) regenerateMutation.mutate(item.id);
                        }}
                      >
                        {regenerateMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-600">{item.student_count}</td>
                  <td className="px-4 py-3 text-zinc-600">{item.max_students ?? '不限'}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatBeijingDateTimeCompact(item.created_at, '—')}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button type="button" title="学生名单" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => setStudentDrawer(item)}>
                        <Users size={15} />
                      </button>
                      <button type="button" title="导出成绩" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => void exportGrades(item)}>
                        <Download size={15} />
                      </button>
                      <button type="button" title="编辑" className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100" onClick={() => openEdit(item)}>
                        <Pencil size={15} />
                      </button>
                      <button
                        type="button"
                        title="删除"
                        className="rounded-md p-1.5 text-zinc-500 hover:bg-red-50 hover:text-red-600"
                        onClick={() => {
                          if (window.confirm(`确定删除班级「${item.name}」吗？`)) deleteMutation.mutate(item.id);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
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
          <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-base font-semibold text-zinc-900">{editing ? '编辑班级' : '新建班级'}</h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs text-zinc-500">
                班级名称
                <input className={`${inputClass} mt-1`} value={form.name} placeholder="例如：深度学习 01 班" onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                班级描述
                <input className={`${inputClass} mt-1`} value={form.description} placeholder="选填" onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </label>
              <label className="block text-xs text-zinc-500">
                容量上限
                <input className={`${inputClass} mt-1`} type="number" min={1} value={form.max_students} placeholder="选填" onChange={(e) => setForm({ ...form, max_students: e.target.value })} />
              </label>
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className={secondaryButtonClass} onClick={() => setFormOpen(false)}>取消</button>
              <button type="button" className={primaryButtonClass} disabled={!form.name.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                {saveMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : null} 保存
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {studentDrawer ? (
        <StudentDrawer classItem={studentDrawer} onClose={() => setStudentDrawer(null)} />
      ) : null}
    </div>
  );
}

function StudentDrawer({ classItem, onClose }: { classItem: TaClass; onClose: () => void }): JSX.Element {
  const queryClient = useQueryClient();
  const [studentId, setStudentId] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  const studentsQuery = useQuery({
    queryKey: ['ta-class-students', classItem.id],
    queryFn: () => taListClassStudents(classItem.id),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['ta-class-students', classItem.id] });
    void queryClient.invalidateQueries({ queryKey: ['ta-classes'] });
  };

  const addMutation = useMutation({
    mutationFn: () => taAddStudent(classItem.id, studentId.trim()),
    onSuccess: () => { setStudentId(''); setActionError(null); invalidate(); },
    onError: (error) => setActionError((error as Error).message),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => taRemoveStudent(classItem.id, id),
    onSuccess: () => { setActionError(null); invalidate(); },
    onError: (error) => setActionError((error as Error).message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-zinc-900">学生名单 · {classItem.name}</h3>
          <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600" onClick={onClose}>✕</button>
        </div>

        <div className="mt-4 flex gap-2">
          <input className={inputClass} value={studentId} placeholder="输入学生 ID（UUID）" onChange={(e) => setStudentId(e.target.value)} />
          <button type="button" className={primaryButtonClass} disabled={!studentId.trim() || addMutation.isPending} onClick={() => addMutation.mutate()}>
            添加
          </button>
        </div>
        {actionError ? <p className="mt-2 text-xs text-red-600">{actionError}</p> : null}

        <div className="mt-4 flex-1 overflow-auto">
          {studentsQuery.isLoading ? (
            <LoadingState label="正在加载学生名单..." />
          ) : studentsQuery.isError ? (
            <ErrorState label={(studentsQuery.error as Error)?.message || '学生名单加载失败'} />
          ) : (studentsQuery.data ?? []).length === 0 ? (
            <EmptyState label="班级暂无学生" />
          ) : (
            <ul className="divide-y divide-zinc-100">
              {(studentsQuery.data ?? []).map((student: TaStudent) => (
                <li key={student.id} className="flex items-center justify-between py-2.5">
                  <div>
                    <div className="text-sm font-medium text-zinc-800">{student.name}</div>
                    <div className="text-xs text-zinc-400">{student.email ?? student.id}</div>
                  </div>
                  <button
                    type="button"
                    className="rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    onClick={() => {
                      if (window.confirm(`确定将「${student.name}」移出班级吗？`)) removeMutation.mutate(student.id);
                    }}
                  >
                    移出班级
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
