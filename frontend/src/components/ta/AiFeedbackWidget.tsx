import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Star } from 'lucide-react';
import { taContinualSubmitFeedback } from '../../api/ta';

type AiFeedbackWidgetProps = {
  /** 被评价的 AI 输出类型：lesson_plan/grading/advice/resource */
  targetType: string;
  /** 被评价对象标识，可选 */
  targetId?: string;
  /** 关联课程 ID，可选 */
  courseId?: string;
  /** 紧凑模式：仅展示星标行 */
  compact?: boolean;
};

/**
 * AI 反馈闭环评分组件：教师对 AI 输出打 1-5 星并附文字反馈。
 * 反馈提交后进入持续学习闭环，驱动模型校准与进化日志记录。
 */
export function AiFeedbackWidget({ targetType, targetId, courseId, compact = false }: AiFeedbackWidgetProps): JSX.Element {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState('');
  const [commentOpen, setCommentOpen] = useState(false);
  const [done, setDone] = useState(false);

  const submitMutation = useMutation({
    mutationFn: () => taContinualSubmitFeedback({
      target_type: targetType,
      rating,
      comment: comment.trim() || undefined,
      target_id: targetId,
      course_id: courseId,
    }),
    onSuccess: () => {
      setDone(true);
      setCommentOpen(false);
    },
  });

  if (done) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-emerald-600">
        <Star size={13} className="fill-emerald-500 text-emerald-500" />
        反馈已记录，AI 将持续学习改进
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-zinc-400">为本次 AI 输出评分：</span>
      <div className="flex items-center gap-0.5" onMouseLeave={() => setHover(0)}>
        {[1, 2, 3, 4, 5].map((i) => (
          <button
            key={i}
            type="button"
            title={`${i} 星`}
            className="p-0.5"
            onMouseEnter={() => setHover(i)}
            onClick={() => { setRating(i); setDone(false); }}
          >
            <Star size={16} className={(hover || rating) >= i ? 'fill-amber-400 text-amber-400' : 'text-zinc-300'} />
          </button>
        ))}
      </div>
      {rating > 0 && !compact && (
        <>
          <button
            type="button"
            className="text-xs text-zinc-500 underline-offset-2 hover:underline"
            onClick={() => setCommentOpen((v) => !v)}
          >
            {commentOpen ? '收起意见' : '补充意见'}
          </button>
          <button
            type="button"
            className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
            disabled={submitMutation.isPending}
            onClick={() => submitMutation.mutate()}
          >
            {submitMutation.isPending ? '提交中...' : '提交反馈'}
          </button>
        </>
      )}
      {rating > 0 && compact && (
        <button
          type="button"
          className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50"
          disabled={submitMutation.isPending}
          onClick={() => submitMutation.mutate()}
        >
          {submitMutation.isPending ? '提交中...' : '提交'}
        </button>
      )}
      {commentOpen && (
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="例如：教学过程不够具体，希望增加互动环节"
          maxLength={500}
          className="w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs outline-none focus:border-zinc-500"
        />
      )}
      {submitMutation.isError && <span className="text-xs text-red-600">提交失败，请重试</span>}
    </div>
  );
}
