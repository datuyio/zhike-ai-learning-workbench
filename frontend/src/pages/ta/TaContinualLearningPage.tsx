import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, BrainCircuit, History, RefreshCw, Sparkles, Star, Target, TrendingUp,
} from 'lucide-react';
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  taContinualErrorPatterns, taContinualEvolution, taContinualFeedbackSummary,
  taContinualForgettingRisk, taContinualProfileTrends, taContinualRefresh, taListClasses,
  type ContinualRiskStudent,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';

const selectClass = 'rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const cardClass = 'rounded-lg border border-zinc-200 bg-white p-5';
const cardTitleClass = 'flex items-center gap-2 text-sm font-semibold text-zinc-800';

const LEVEL_META: Record<string, { label: string; badge: string; dot: string }> = {
  high: { label: '高风险', badge: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-500' },
  medium: { label: '中风险', badge: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-500' },
  low: { label: '稳定', badge: 'bg-emerald-50 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500' },
};

const EVOLUTION_META: Record<string, { label: string; color: string }> = {
  risk_recalibrated: { label: '风险模型重算', color: 'bg-violet-500' },
  error_patterns_updated: { label: '易错点更新', color: 'bg-amber-500' },
  feedback_calibration: { label: '反馈校准', color: 'bg-sky-500' },
  negative_feedback: { label: '低分反馈', color: 'bg-red-500' },
};

const TREND_COLORS = ['#18181b', '#7c3aed', '#0284c7', '#d97706', '#059669'];

function RiskBadge({ level }: { level: string }): JSX.Element {
  const meta = LEVEL_META[level] ?? LEVEL_META.low;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${meta.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

function Stars({ rating }: { rating: number }): JSX.Element {
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} size={13} className={i <= rating ? 'fill-amber-400 text-amber-400' : 'text-zinc-300'} />
      ))}
    </span>
  );
}

/**
 * 持续学习中心：遗忘风险预测、错误模式识别、AI 反馈闭环、画像趋势与进化日志。
 * 承载"持续学习与遗忘风险预测"独创亮点的教师端可视化闭环。
 */
export function TaContinualLearningPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [classId, setClassId] = useState('');
  const [studentId, setStudentId] = useState('');

  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });
  const resolvedClassId = classId || classesQuery.data?.[0]?.id || '';

  const riskQuery = useQuery({
    queryKey: ['continual-risk', resolvedClassId],
    queryFn: () => taContinualForgettingRisk(resolvedClassId),
    enabled: Boolean(resolvedClassId),
  });
  const patternsQuery = useQuery({
    queryKey: ['continual-patterns', resolvedClassId],
    queryFn: () => taContinualErrorPatterns(resolvedClassId),
    enabled: Boolean(resolvedClassId),
  });
  const summaryQuery = useQuery({ queryKey: ['continual-feedback-summary'], queryFn: () => taContinualFeedbackSummary() });
  const evolutionQuery = useQuery({ queryKey: ['continual-evolution'], queryFn: () => taContinualEvolution() });

  const students: ContinualRiskStudent[] = riskQuery.data?.students ?? [];
  const resolvedStudentId = studentId || students[0]?.student_id || '';
  const trendsQuery = useQuery({
    queryKey: ['continual-profile-trends', resolvedStudentId],
    queryFn: () => taContinualProfileTrends(resolvedStudentId),
    enabled: Boolean(resolvedStudentId),
  });

  const refreshMutation = useMutation({
    mutationFn: () => taContinualRefresh(resolvedClassId),
    onSuccess: () => {
      // 进化完成后同步刷新风险、易错点与进化日志三个视图
      queryClient.invalidateQueries({ queryKey: ['continual-risk'] });
      queryClient.invalidateQueries({ queryKey: ['continual-patterns'] });
      queryClient.invalidateQueries({ queryKey: ['continual-evolution'] });
    },
  });

  // 画像趋势：把各维度按日期合并为宽表，供多线折线图渲染
  const trendChartData = useMemo(() => {
    const dims = trendsQuery.data?.dimensions ?? [];
    const byDate = new Map<string, Record<string, number | string>>();
    for (const dim of dims) {
      for (const point of dim.series) {
        const row = byDate.get(point.date) ?? { date: point.date };
        row[dim.label] = point.score;
        byDate.set(point.date, row);
      }
    }
    return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [trendsQuery.data]);
  const trendDimensions = (trendsQuery.data?.dimensions ?? []).slice(0, 5);

  const risk = riskQuery.data;
  const patterns = patternsQuery.data?.patterns ?? [];
  const summary = summaryQuery.data;
  const events = evolutionQuery.data?.events ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="持续学习中心"
        subtitle="持续学习与遗忘风险预测：数据 → 预测 → 干预 → 反馈 → 进化的闭环，系统随教学使用不断自我优化。"
      />
      <PageHeaderToolbar>
        <div className="flex flex-wrap items-center gap-3">
          <select value={resolvedClassId} onChange={(e) => setClassId(e.target.value)} className={selectClass}>
            {(classesQuery.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            type="button"
            className={primaryButtonClass}
            disabled={!resolvedClassId || refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
          >
            <RefreshCw size={15} className={refreshMutation.isPending ? 'animate-spin' : ''} />
            触发一轮进化
          </button>
          {refreshMutation.isSuccess && <span className="text-xs text-emerald-600">{refreshMutation.data.message}</span>}
        </div>
      </PageHeaderToolbar>

      {/* 遗忘风险预测 + 错误模式识别 */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className={`${cardClass} xl:col-span-2`}>
          <div className={cardTitleClass}>
            <AlertTriangle size={16} className="text-red-500" />
            遗忘风险预测
            <span className="text-xs font-normal text-zinc-400">基于学习事件频率与掌握度变化趋势，自动识别需要复习的学生</span>
          </div>
          {riskQuery.isLoading ? (
            <LoadingState />
          ) : riskQuery.isError ? (
            <ErrorState label="遗忘风险加载失败" />
          ) : !risk || risk.students.length === 0 ? (
            <EmptyState label="暂无学生掌握度数据，先完成测评或学习后再试" />
          ) : (
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-4 text-xs text-zinc-500">
                <span>学生 {risk.total_count} 人</span>
                <span className="text-red-600">高风险 {risk.high_count} 人</span>
                <span className="text-amber-600">中风险 {risk.medium_count} 人</span>
              </div>
              <ul className="space-y-3">
                {risk.students.slice(0, 8).map((s) => (
                  <li key={s.student_id} className="rounded-md border border-zinc-100 bg-zinc-50/60 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-zinc-800">{s.student_name}</span>
                        <RiskBadge level={s.level} />
                      </div>
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <span>综合风险</span>
                        <span className="text-sm font-semibold text-zinc-900">{s.risk_score}</span>
                        <span>近 14 天事件 {s.recent_event_count} 次</span>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {s.top_risk_concepts.map((c) => (
                        <span key={c.concept_id} className="inline-flex items-center gap-1 rounded border border-zinc-200 bg-white px-2 py-0.5 text-xs text-zinc-600">
                          {c.concept}
                          <span className="text-zinc-400">保持率 {c.retention}%</span>
                          <span className={`font-medium ${c.level === 'high' ? 'text-red-600' : c.level === 'medium' ? 'text-amber-600' : 'text-emerald-600'}`}>
                            风险 {c.risk}
                          </span>
                        </span>
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-zinc-500">{s.suggestion}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className={cardClass}>
          <div className={cardTitleClass}>
            <Target size={16} className="text-amber-500" />
            错误模式识别
            <span className="text-xs font-normal text-zinc-400">历史易错点 TOP3</span>
          </div>
          {patternsQuery.isLoading ? (
            <LoadingState />
          ) : patterns.length === 0 ? (
            <EmptyState label="暂无易错点数据" />
          ) : (
            <ol className="mt-4 space-y-3">
              {patterns.map((p, idx) => (
                <li key={p.concept_id} className="rounded-md border border-zinc-100 bg-zinc-50/60 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-zinc-800">TOP{idx + 1} · {p.concept}</span>
                    <span className="text-xs text-zinc-500">强度 {p.score}</span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">
                    历史出错 {p.wrong_count} 次 · 薄弱学生 {p.weak_student_count} 人
                  </p>
                  {p.samples.length > 0 && (
                    <p className="mt-1 truncate text-xs text-zinc-400">典型错题：{p.samples.join('、')}</p>
                  )}
                  <p className="mt-2 text-xs text-violet-700">{p.tip}</p>
                </li>
              ))}
            </ol>
          )}
          <p className="mt-3 text-xs text-zinc-400">TOP 易错点已自动注入智能备课的教案生成链路。</p>
        </section>
      </div>

      {/* AI 反馈闭环 + 画像趋势 */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className={cardClass}>
          <div className={cardTitleClass}>
            <Sparkles size={16} className="text-violet-500" />
            AI 反馈闭环
            <span className="text-xs font-normal text-zinc-400">教师 1-5 星评分持续优化模型表现</span>
          </div>
          {summaryQuery.isLoading ? (
            <LoadingState />
          ) : !summary || summary.total === 0 ? (
            <EmptyState label="暂无教师反馈，去智能备课页为 AI 教案评分即可开启闭环" />
          ) : (
            <div className="mt-4 space-y-4">
              <div className="flex items-center gap-6">
                <div>
                  <div className="text-2xl font-semibold text-zinc-900">{summary.avg_rating}</div>
                  <div className="text-xs text-zinc-400">平均评分（{summary.total} 条反馈）</div>
                </div>
                <div className="flex-1">
                  <div className="h-28">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={summary.rating_trend.filter((t) => t.avg_rating !== null)}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                        <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                        <YAxis domain={[0, 5]} tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Line type="monotone" dataKey="avg_rating" name="平均评分" stroke="#7c3aed" strokeWidth={2} dot={{ r: 2 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="text-center text-xs text-zinc-400">评分周趋势（持续改进轨迹）</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {summary.by_target_type.map((t) => (
                  <span key={t.target_type} className="inline-flex items-center gap-1 rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs text-zinc-600">
                    {t.label} 平均 {t.avg_rating} 星（{t.count} 条）
                  </span>
                ))}
              </div>
              <ul className="space-y-2">
                {summary.recent.slice(0, 5).map((f) => (
                  <li key={f.id} className="flex items-start justify-between gap-3 rounded-md border border-zinc-100 bg-zinc-50/60 px-3 py-2">
                    <div>
                      <span className="text-xs font-medium text-zinc-700">{f.label}</span>
                      {f.comment && <p className="mt-0.5 text-xs text-zinc-500">{f.comment}</p>}
                    </div>
                    <Stars rating={f.rating} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className={cardClass}>
          <div className={cardTitleClass}>
            <TrendingUp size={16} className="text-sky-500" />
            画像趋势分析
            <span className="text-xs font-normal text-zinc-400">跨时间维度追踪学情画像变化</span>
          </div>
          <div className="mt-3">
            <select value={resolvedStudentId} onChange={(e) => setStudentId(e.target.value)} className={selectClass}>
              {students.map((s) => (
                <option key={s.student_id} value={s.student_id}>{s.student_name}</option>
              ))}
            </select>
          </div>
          {trendsQuery.isLoading ? (
            <LoadingState />
          ) : trendDimensions.length === 0 ? (
            <EmptyState label="该学生暂无画像证据链，趋势将随学习行为自动积累" />
          ) : (
            <div className="mt-4">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {trendDimensions.map((d, i) => (
                      <Line key={d.key} type="stepAfter" dataKey={d.label} stroke={TREND_COLORS[i % TREND_COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {trendDimensions.map((d) => (
                  <span key={d.key} className="rounded border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-600">
                    {d.label} 当前 {d.current}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* 进化日志 */}
      <section className={cardClass}>
        <div className={cardTitleClass}>
          <History size={16} className="text-zinc-500" />
          进化日志
          <span className="text-xs font-normal text-zinc-400">记录系统学习行为的演变历史，形成可视化进化轨迹</span>
        </div>
        {evolutionQuery.isLoading ? (
          <LoadingState />
        ) : events.length === 0 ? (
          <EmptyState label="暂无进化事件，点击「触发一轮进化」开始记录系统成长轨迹" />
        ) : (
          <ol className="mt-4 space-y-0">
            {events.map((e, idx) => {
              const meta = EVOLUTION_META[e.event_type] ?? { label: e.event_type, color: 'bg-zinc-400' };
              return (
                <li key={e.id} className="relative flex gap-3 pb-5">
                  {idx < events.length - 1 && <span className="absolute left-[5px] top-4 h-full w-px bg-zinc-200" />}
                  <span className={`mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full ${meta.color}`} />
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-zinc-800">{e.title}</span>
                      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500">{meta.label}</span>
                      <span className="text-[11px] text-zinc-400">{e.created_at ? new Date(e.created_at).toLocaleString('zh-CN') : ''}</span>
                    </div>
                    {e.detail && <p className="mt-1 text-xs text-zinc-500">{e.detail}</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <p className="flex items-center gap-1.5 text-xs text-zinc-400">
        <BrainCircuit size={14} />
        持续学习机制：遗忘风险预测驱动主动干预，教师反馈驱动模型校准，进化日志沉淀系统成长轨迹。
      </p>
    </div>
  );
}
