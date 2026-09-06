import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckSquare, GraduationCap, Users } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { taDashboard, type TaDashboardStats } from '../../api/ta';
import { PageHeader } from '../../components/shared/PageHeader';
import { ErrorState, LoadingState } from '../../components/shared/StateBlock';

const SEVERITY_LABEL: Record<string, string> = { high: '高', medium: '中', low: '低' };
const SEVERITY_STYLE: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-zinc-100 text-zinc-600',
};

/**
 * 助教端工作台：班级概览、近 7 天活跃趋势、待办任务与未处理预警。
 */
export function TaDashboardPage(): JSX.Element {
  const query = useQuery({
    queryKey: ['ta-dashboard'],
    queryFn: () => taDashboard(),
  });

  const stats: TaDashboardStats | undefined = query.data;
  const cards = [
    { label: '班级数量', value: stats?.class_count ?? 0, icon: GraduationCap, tone: 'bg-zinc-900' },
    { label: '学生总数', value: stats?.student_count ?? 0, icon: Users, tone: 'bg-blue-700' },
    { label: '待批改', value: stats?.pending_grading ?? 0, icon: CheckSquare, tone: 'bg-amber-600' },
    { label: '活跃预警', value: stats?.active_alerts ?? 0, icon: AlertTriangle, tone: 'bg-red-600' },
  ];

  return (
    <div className="ta-dashboard mx-auto w-full max-w-6xl">
      <PageHeader
        title="助教工作台"
        subtitle="概览班级情况、待办批改任务与学情动态，快速进入各工作模块。"
      />

      {query.isLoading ? (
        <LoadingState label="正在加载工作台数据..." />
      ) : query.isError ? (
        <ErrorState label={(query.error as Error)?.message || '工作台数据加载失败'} />
      ) : (
        <>
          <div className="ta-dashboard__metrics grid grid-cols-2 gap-4 lg:grid-cols-4">
            {cards.map((card) => (
              <div key={card.label} className="ta-dashboard__metric-card rounded-lg border border-zinc-200 bg-white p-5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">{card.label}</span>
                  <span className={`ta-dashboard__metric-icon flex h-8 w-8 items-center justify-center rounded-md text-white ${card.tone}`}>
                    <card.icon size={16} />
                  </span>
                </div>
                <div className="mt-2 text-2xl font-semibold text-zinc-900">{card.value}</div>
              </div>
            ))}
          </div>

          <div className="ta-dashboard__main-grid mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div className="ta-dashboard__panel ta-dashboard__panel--chart rounded-lg border border-zinc-200 bg-white p-5 xl:col-span-2">
              <h2 className="text-sm font-medium text-zinc-700">近 7 天活跃学生</h2>
              <div className="mt-3 h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={stats?.weekly_active_trend ?? []} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
                    <defs>
                      <linearGradient id="taActiveFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} tickFormatter={(v: string) => v.slice(5)} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#71717a' }} />
                    <Tooltip labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="active_students" name="活跃学生" stroke="#3b82f6" strokeWidth={2} fill="url(#taActiveFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="ta-dashboard__panel ta-dashboard__panel--tasks rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-sm font-medium text-zinc-700">待办任务</h2>
              {(stats?.recent_tasks ?? []).length === 0 ? (
                <p className="ta-dashboard__empty mt-4 text-sm text-zinc-400">暂无待办任务</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {(stats?.recent_tasks ?? []).slice(0, 6).map((task) => (
                    <li key={`${task.type}-${task.id}`}>
                      <Link to={task.href} className="ta-dashboard__task-link block rounded-md border border-zinc-100 px-3 py-2 transition-colors hover:border-zinc-300">
                        <div className="text-sm text-zinc-800">{task.title}</div>
                        <div className="mt-0.5 text-xs text-zinc-400">{task.meta}</div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="ta-dashboard__panel ta-dashboard__panel--alerts mt-4 rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-sm font-medium text-zinc-700">未处理预警</h2>
            {(stats?.recent_alerts ?? []).length === 0 ? (
              <p className="ta-dashboard__empty mt-4 text-sm text-zinc-400">暂无活跃预警，班级状态良好</p>
            ) : (
              <ul className="mt-3 divide-y divide-zinc-100">
                {(stats?.recent_alerts ?? []).map((alert) => (
                  <li key={alert.id} className="ta-dashboard__alert-row flex items-center justify-between gap-4 py-2.5">
                    <span className="flex items-center gap-2 text-sm text-zinc-800">
                      <span className={`rounded px-1.5 py-0.5 text-xs ${SEVERITY_STYLE[alert.severity] ?? SEVERITY_STYLE.low}`}>
                        {SEVERITY_LABEL[alert.severity] ?? alert.severity}
                      </span>
                      {alert.title}
                    </span>
                    <Link to="/ta/diagnosis" className="ta-dashboard__alert-action shrink-0 text-xs text-blue-600 hover:underline">去处理</Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
