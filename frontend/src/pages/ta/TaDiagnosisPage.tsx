import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, BookOpenCheck, Lightbulb, TrendingUp } from 'lucide-react';
import {
  CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  taDiagnosisClass, taDiagnosisClassAdvice, taDiagnosisClassActivityTrend, taDiagnosisClassWeakPoints,
  taDiagnosisCompare, taDiagnosisStudentRadar, taDiagnosisStudentTrend, taListClasses,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { EmptyState, ErrorState, LoadingState } from '../../components/shared/StateBlock';

const inputClass = 'w-full rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none transition-colors focus:border-zinc-500';
const primaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50';
const secondaryButtonClass = 'inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50';

type RadarDimension = { key: string; label: string; score: number; source: string };
type TrendPoint = { date: string; score: number | null; event_count: number };
type CompareRow = { class_id: string; name: string; avg_score: number; avg_mastery: number; weak_points: number; active_students: number; student_count: number };
type StudentItem = { student_id: string; name: string; avg_mastery: number };
type WeakPoint = { concept_id: string; concept: string; weak_rate: number; student_count: number; severity: string; suggested_practice: number };
type ClassAdvice = {
  class_id: string;
  metrics: Record<string, number>;
  priority_concepts: Array<{ concept_id: string; concept: string; avg_mastery: number }>;
  summary: string;
  suggestions: string[];
  source: string;
};

/**
 * 学情诊断：班级对比、个体雷达与趋势、薄弱知识点与教学建议。
 */
export function TaDiagnosisPage(): JSX.Element {
  const [classId, setClassId] = useState('');
  const [studentId, setStudentId] = useState('');
  const [adviceOpen, setAdviceOpen] = useState(false);

  const classesQuery = useQuery({ queryKey: ['ta-classes'], queryFn: () => taListClasses() });

  const resolvedClassId = classId || classesQuery.data?.[0]?.id || '';
  const classQuery = useQuery({
    queryKey: ['ta-diagnosis-class', resolvedClassId],
    queryFn: () => taDiagnosisClass(resolvedClassId),
    enabled: Boolean(resolvedClassId),
  });
  const compareQuery = useQuery({ queryKey: ['ta-diagnosis-compare'], queryFn: () => taDiagnosisCompare() });
  const weakPointsQuery = useQuery({
    queryKey: ['ta-diagnosis-weak', resolvedClassId],
    queryFn: () => taDiagnosisClassWeakPoints(resolvedClassId),
    enabled: Boolean(resolvedClassId),
  });
  const activityQuery = useQuery({
    queryKey: ['ta-diagnosis-activity', resolvedClassId],
    queryFn: () => taDiagnosisClassActivityTrend(resolvedClassId),
    enabled: Boolean(resolvedClassId),
  });
  const adviceQuery = useQuery({
    queryKey: ['ta-diagnosis-advice', resolvedClassId],
    queryFn: () => taDiagnosisClassAdvice(resolvedClassId),
    enabled: adviceOpen && Boolean(resolvedClassId),
  });

  const students: StudentItem[] = (classQuery.data?.students as StudentItem[] | undefined) ?? [];
  const resolvedStudentId = studentId || students[0]?.student_id || '';
  const radarQuery = useQuery({
    queryKey: ['ta-diagnosis-radar', resolvedStudentId],
    queryFn: () => taDiagnosisStudentRadar(resolvedStudentId),
    enabled: Boolean(resolvedStudentId),
  });
  const trendQuery = useQuery({
    queryKey: ['ta-diagnosis-trend', resolvedStudentId],
    queryFn: () => taDiagnosisStudentTrend(resolvedStudentId),
    enabled: Boolean(resolvedStudentId),
  });

  const radarData: RadarDimension[] = (radarQuery.data?.dimensions as RadarDimension[] | undefined) ?? [];
  const trendData: TrendPoint[] = (trendQuery.data?.trend as TrendPoint[] | undefined) ?? [];
  const compareRows: CompareRow[] = (compareQuery.data as CompareRow[] | undefined) ?? [];
  const weakPoints: WeakPoint[] = (weakPointsQuery.data as WeakPoint[] | undefined) ?? [];
  const activityData = useMemo(() => {
    const rows = (activityQuery.data?.trend as Array<{ date: string; event_count: number }> | undefined) ?? [];
    return rows.slice(-14);
  }, [activityQuery.data]);

  const selectedStudent = students.find((item) => item.student_id === resolvedStudentId);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="学情诊断" subtitle="对比班级学习状况，透视个体学习轨迹，定位薄弱知识点并生成教学建议。" />

      <PageHeaderToolbar>
        <div className="flex items-center gap-2">
          <select className={inputClass} value={resolvedClassId} onChange={(e) => { setClassId(e.target.value); setStudentId(''); setAdviceOpen(false); }}>
            {(classesQuery.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <button type="button" className={primaryButtonClass} onClick={() => setAdviceOpen(true)}>
            <Lightbulb size={15} /> 生成教学建议
          </button>
        </div>
      </PageHeaderToolbar>

      {classesQuery.isLoading ? (
        <LoadingState label="正在加载班级数据..." />
      ) : classesQuery.isError ? (
        <ErrorState label={(classesQuery.error as Error)?.message || '班级数据加载失败'} />
      ) : (classesQuery.data ?? []).length === 0 ? (
        <EmptyState label="暂无班级，请先到班级管理创建班级。" />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-1.5 text-sm font-medium text-zinc-700"><TrendingUp size={15} /> 班级对比</h2>
              {compareQuery.isLoading ? (
                <LoadingState label="正在加载对比数据..." />
              ) : (
                <table className="mt-3 w-full text-left text-sm">
                  <thead className="border-b border-zinc-200 text-xs text-zinc-500">
                    <tr>
                      <th className="py-2 font-medium">班级</th>
                      <th className="py-2 font-medium">平均分</th>
                      <th className="py-2 font-medium">平均掌握度</th>
                      <th className="py-2 font-medium">薄弱点</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {compareRows.map((row) => (
                      <tr key={row.class_id}>
                        <td className="py-2.5 font-medium text-zinc-800">{row.name}</td>
                        <td className="py-2.5 text-zinc-600">{row.avg_score}</td>
                        <td className="py-2.5 text-zinc-600">{row.avg_mastery}</td>
                        <td className="py-2.5 text-zinc-600">{row.weak_points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="flex items-center gap-1.5 text-sm font-medium text-zinc-700"><AlertTriangle size={15} /> 薄弱知识点</h2>
              {weakPoints.length === 0 ? (
                <p className="mt-4 text-sm text-zinc-400">暂无薄弱知识点</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {weakPoints.slice(0, 6).map((point) => (
                    <li key={point.concept_id} className="flex items-center justify-between rounded-md border border-zinc-100 px-3 py-2">
                      <span className="text-sm text-zinc-800">{point.concept}</span>
                      <span className="text-xs text-zinc-500">薄弱率 {Math.round(point.weak_rate * 100)}% · {point.severity}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-sm font-medium text-zinc-700">学生列表</h2>
              <select className={`${inputClass} mt-3`} value={resolvedStudentId} onChange={(e) => setStudentId(e.target.value)}>
                {students.map((item) => <option key={item.student_id} value={item.student_id}>{item.name}（掌握度 {item.avg_mastery}）</option>)}
              </select>
              {selectedStudent ? (
                <div className="mt-3 rounded-md border border-zinc-100 bg-zinc-50 p-3 text-sm text-zinc-600">
                  <div>学生：{selectedStudent.name}</div>
                  <div>平均掌握度：{selectedStudent.avg_mastery}</div>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-sm font-medium text-zinc-700">个体雷达（近 14 天）</h2>
              {radarData.length === 0 ? (
                <p className="mt-4 text-sm text-zinc-400">暂无雷达数据</p>
              ) : (
                <div className="mt-2 h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} outerRadius="72%">
                      <PolarGrid stroke="#e4e4e7" />
                      <PolarAngleAxis dataKey="label" tick={{ fontSize: 11, fill: '#71717a' }} />
                      <Radar dataKey="score" name="得分" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                      <Tooltip contentStyle={{ fontSize: 12 }} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white p-5">
              <h2 className="text-sm font-medium text-zinc-700">学习趋势（近 30 天）</h2>
              <div className="mt-2 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#71717a' }} tickFormatter={(v: string) => v.slice(5)} />
                    <YAxis tick={{ fontSize: 11, fill: '#71717a' }} />
                    <Tooltip labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="score" name="得分" stroke="#3b82f6" strokeWidth={2} connectNulls dot={false} />
                    <Line type="monotone" dataKey="event_count" name="学习事件" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="flex items-center gap-1.5 text-sm font-medium text-zinc-700"><BookOpenCheck size={15} /> 班级活跃趋势</h2>
            <div className="mt-2 h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={activityData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#71717a' }} tickFormatter={(v: string) => v.slice(5)} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#71717a' }} />
                  <Tooltip labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="event_count" name="学习事件数" stroke="#16a34a" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {adviceOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-zinc-900">教学建议</h3>
              <button type="button" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-100" onClick={() => setAdviceOpen(false)}>✕</button>
            </div>
            <div className="mt-4 flex-1 overflow-auto">
              {adviceQuery.isLoading ? (
                <LoadingState label="正在生成教学建议..." />
              ) : adviceQuery.isError ? (
                <ErrorState label={(adviceQuery.error as Error)?.message || '教学建议生成失败'} />
              ) : (
                <AdviceContent advice={adviceQuery.data as ClassAdvice | undefined} />
              )}
            </div>
            <div className="mt-4 flex justify-end">
              <button type="button" className={secondaryButtonClass} onClick={() => setAdviceOpen(false)}>关闭</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 教学建议内容区：将后端返回的结构化诊断数据渲染为可读的总结、重点知识点与建议列表。
 */
function AdviceContent({ advice }: { advice: ClassAdvice | undefined }): JSX.Element {
  if (!advice) {
    return <p className="text-sm text-zinc-400">暂无建议内容</p>;
  }

  return (
    <div className="space-y-5 text-sm">
      <section>
        <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-zinc-500">
          <Lightbulb size={14} /> 学情总结
        </h4>
        <p className="leading-relaxed text-zinc-700">{advice.summary}</p>
      </section>

      {advice.priority_concepts.length > 0 ? (
        <section>
          <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-zinc-500">
            <AlertTriangle size={14} /> 重点关注知识点
          </h4>
          <ul className="space-y-1.5">
            {advice.priority_concepts.map((item) => (
              <li key={item.concept_id} className="flex items-center justify-between rounded-md border border-zinc-100 px-3 py-2">
                <span className="text-zinc-800">{item.concept}</span>
                <span className="text-xs text-zinc-500">平均掌握度 {item.avg_mastery}%</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-zinc-500">
          <BookOpenCheck size={14} /> 教学建议
        </h4>
        {advice.suggestions.length > 0 ? (
          <ol className="list-decimal space-y-1.5 pl-5">
            {advice.suggestions.map((item, index) => (
              <li key={index} className="leading-relaxed text-zinc-700">{item}</li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-zinc-400">暂无建议</p>
        )}
      </section>
    </div>
  );
}
