import { useRef, type ChangeEvent, type DragEvent } from 'react';
import { FileText, Loader2, Upload, X } from 'lucide-react';
import {
  RESOURCE_UPLOAD_ACCEPT,
  RESOURCE_UPLOAD_MAX_BYTES,
  formatResourceUploadSize,
  resourceUploadDifficultyOptions,
  resourceUploadTypeOptions,
  type ResourceUploadDraft,
} from './resourceHallConfig';

export function ResourceUploadDialog({
  uploadDraft,
  uploadFile,
  uploadDragActive,
  hasCourse,
  currentCourseTitle,
  courseId,
  isPending,
  onClose,
  onSubmit,
  onDragActiveChange,
  onDrop,
  onInputChange,
  onFileRemove,
  onDraftChange,
}: {
  uploadDraft: ResourceUploadDraft;
  uploadFile: File | null;
  uploadDragActive: boolean;
  hasCourse: boolean;
  currentCourseTitle?: string | null;
  courseId?: string | null;
  isPending: boolean;
  onClose: () => void;
  onSubmit: () => void;
  onDragActiveChange: (active: boolean) => void;
  onDrop: (event: DragEvent<HTMLDivElement>) => void;
  onInputChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onFileRemove: () => void;
  onDraftChange: (patch: Partial<ResourceUploadDraft>) => void;
}): JSX.Element {
  const uploadInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/35 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-black text-slate-950">上传资源</h2>
            <p className="mt-1 text-sm font-medium leading-6 text-slate-500">
              支持 Markdown / TXT，单个文件不超过 {formatResourceUploadSize(RESOURCE_UPLOAD_MAX_BYTES)}。上传后会成为可编辑的个人资源版本。
            </p>
          </div>
          <button
            type="button"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
            title="关闭"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <input
            ref={uploadInputRef}
            className="hidden"
            type="file"
            accept={RESOURCE_UPLOAD_ACCEPT}
            onChange={onInputChange}
          />
          <div
            className={`rounded-lg border border-dashed p-5 text-center transition ${
              uploadDragActive ? 'border-emerald-300 bg-emerald-50' : 'border-slate-300 bg-slate-50'
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              onDragActiveChange(true);
            }}
            onDragLeave={() => onDragActiveChange(false)}
            onDrop={onDrop}
          >
            <Upload className="mx-auto text-emerald-600" size={30} />
            <div className="mt-3 text-sm font-black text-slate-900">
              {uploadFile ? uploadFile.name : '拖拽 Markdown / TXT 到这里'}
            </div>
            <p className="mt-1 text-xs font-medium text-slate-500">
              {uploadFile ? `${formatResourceUploadSize(uploadFile.size)} · 将作为首个资源版本` : '也可以不选文件，直接在下方粘贴正文。'}
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              <button
                type="button"
                className="btn-secondary h-9 px-4"
                disabled={isPending}
                onClick={() => uploadInputRef.current?.click()}
              >
                {uploadFile ? '重新选择' : '选择文件'}
              </button>
              {uploadFile ? (
                <button
                  type="button"
                  className="inline-flex h-9 items-center rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 transition hover:bg-slate-50"
                  disabled={isPending}
                  onClick={onFileRemove}
                >
                  移除文件
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="grid gap-2">
              <span className="text-xs font-black text-slate-600">资源标题</span>
              <input
                className="input h-10"
                value={uploadDraft.title}
                placeholder="例如：反向传播推导速记"
                onChange={(event) => onDraftChange({ title: event.target.value })}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-black text-slate-600">资源类型</span>
              <select
                className="input h-10"
                value={uploadDraft.resourceType}
                onChange={(event) => onDraftChange({ resourceType: event.target.value })}
              >
                {resourceUploadTypeOptions.map((item) => (
                  <option key={item.value} value={item.value}>{item.label} · {item.hint}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-black text-slate-600">摘要</span>
              <input
                className="input h-10"
                value={uploadDraft.summary}
                placeholder="不填则从正文自动截取"
                onChange={(event) => onDraftChange({ summary: event.target.value })}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-black text-slate-600">难度</span>
              <select
                className="input h-10"
                value={uploadDraft.difficulty}
                onChange={(event) => onDraftChange({ difficulty: event.target.value })}
              >
                {resourceUploadDifficultyOptions.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
          </div>

          <label className="mt-4 grid gap-2">
            <span className="text-xs font-black text-slate-600">资源正文</span>
            <textarea
              className="input min-h-40 w-full resize-y text-sm leading-6"
              value={uploadDraft.content}
              placeholder="可粘贴 Markdown、题目解析、实验步骤或课堂笔记。若同时上传文件，这里会作为补充说明追加到版本末尾。"
              onChange={(event) => onDraftChange({ content: event.target.value })}
            />
          </label>

          <div className="mt-4 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <label className={`flex items-start gap-3 ${hasCourse ? 'cursor-pointer' : 'cursor-not-allowed opacity-55'}`}>
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-slate-300 text-emerald-600"
                checked={uploadDraft.bindToCurrentCourse}
                disabled={!hasCourse || isPending}
                onChange={(event) => onDraftChange({ bindToCurrentCourse: event.target.checked })}
              />
              <span>
                <span className="block text-sm font-black text-slate-800">绑定到当前课程</span>
                <span className="mt-1 block text-xs font-medium leading-5 text-slate-500">
                  {hasCourse ? `目标课程：${currentCourseTitle || courseId}` : '当前未选择课程，上传后会作为通用个人资源。'}
                </span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-slate-300 text-emerald-600"
                checked={uploadDraft.submitForReview}
                disabled={isPending}
                onChange={(event) => onDraftChange({ submitForReview: event.target.checked })}
              />
              <span>
                <span className="block text-sm font-black text-slate-800">上传后直接提交资源大厅审核</span>
                <span className="mt-1 block text-xs font-medium leading-5 text-slate-500">不勾选时先保存为个人草稿，可在详情中编辑后再提交。</span>
              </span>
            </label>
          </div>
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white px-5 py-4">
          <div className="inline-flex items-center gap-2 text-xs font-bold text-slate-500">
            <FileText size={15} />
            PDF 课程资料请在知识大本营入库，资源大厅只保存可编辑学习资源。
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" disabled={isPending} onClick={onClose}>取消</button>
            <button
              type="button"
              className="btn-primary gap-2"
              disabled={isPending}
              onClick={onSubmit}
            >
              {isPending ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {isPending ? '上传中' : '提交上传'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
