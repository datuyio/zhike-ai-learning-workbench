import { useEffect, useState } from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

const PageHeader = ({ title, subtitle }: { title: string; subtitle?: string }) => (
  <div className="mb-6">
    <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
    {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
  </div>
);

const Card = ({ title, children }: { title?: string; children: React.ReactNode }) => (
  <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
    {title && <h3 className="mb-3 text-sm font-medium text-slate-700">{title}</h3>}
    {children}
  </div>
);

// Mock 数据（API 不可用时使用）
const mockData = {
  overallScore: 78,
  dimensions: [
    { subject: 'Python 基础', score: 85, fullMark: 100 },
    { subject: '数据结构', score: 72, fullMark: 100 },
    { subject: '机器学习', score: 68, fullMark: 100 },
    { subject: '深度学习', score: 55, fullMark: 100 },
    { subject: '算法思维', score: 90, fullMark: 100 },
    { subject: '项目实践', score: 70, fullMark: 100 },
  ],
  trends: [
    { date: '07/01', score: 45 },
    { date: '07/08', score: 52 },
    { date: '07/15', score: 58 },
    { date: '07/22', score: 63 },
    { date: '07/29', score: 70 },
    { date: '08/05', score: 78 },
  ],
  summary: '整体学习效果良好，Python 基础和算法思维表现突出，深度学习和机器学习仍有提升空间。建议加强反向传播和模型调参的练习。',
};

export function LearningAssessmentReportPage(): JSX.Element {
  const [data, setData] = useState<typeof mockData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 调用 API
    fetch('/api/v1/assessment/report')
      .then((res) => {
        if (!res.ok) throw new Error('API 请求失败');
        return res.json();
      })
      .then((raw) => {
        // 将后端 snake_case 响应映射为页面渲染所需的字段结构
        const dimensions = Array.isArray(raw.dimensions)
          ? raw.dimensions.map((item: { name?: string; key?: string; score?: number }) => ({
              subject: item.name ?? item.key ?? '未命名维度',
              score: item.score ?? 0,
              fullMark: 100,
            }))
          : [];
        const trends = Array.isArray(raw.progress_trend)
          ? raw.progress_trend.map((item: { label?: string; score?: number }) => ({
              date: item.label ?? '',
              score: item.score ?? 0,
            }))
          : [];
        const summary =
          Array.isArray(raw.recommendations) && raw.recommendations.length > 0
            ? raw.recommendations.join('；')
            : raw.overall_level ?? '暂无总结';
        setData({
          overallScore: raw.overall_score ?? 0,
          dimensions,
          trends,
          summary,
        });
        setLoading(false);
      })
      .catch((err) => {
        console.warn('API 调用失败，使用 Mock 数据:', err);
        setData(mockData);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-3 border-blue-500 border-t-transparent"></div>
          <p className="mt-2 text-slate-500">加载评估报告中...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="text-center text-red-500">加载失败，请稍后重试</div>;
  }

  return (
    <div className="space-y-6 px-6 pb-8">
      <PageHeader title="学习效果评估报告" subtitle="综合评估你的学习成果" />

      {/* 总体评分卡片 */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <div className="text-center">
            <p className="text-sm text-slate-500">总体评分</p>
            <p className={`text-5xl font-bold ${data.overallScore >= 80 ? 'text-green-600' : data.overallScore >= 60 ? 'text-yellow-600' : 'text-red-600'}`}>
              {data.overallScore}
            </p>
            <p className="text-sm text-slate-500">满分 100 分</p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-sm text-slate-500">评估维度</p>
            <p className="text-3xl font-bold text-slate-900">{data.dimensions.length}</p>
            <p className="text-sm text-slate-500">个维度综合评估</p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-sm text-slate-500">趋势</p>
            <p className="text-3xl font-bold text-green-600">📈 进步中</p>
            <p className="text-sm text-slate-500">
              较首月提升 {data.trends[data.trends.length - 1]?.score - data.trends[0]?.score} 分
            </p>
          </div>
        </Card>
      </div>

      {/* 雷达图 + 趋势图 */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="各维度能力评估">
          <ResponsiveContainer width="100%" height={320}>
            <RadarChart data={data.dimensions}>
              <PolarGrid stroke="#e2e8f0" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: '#475569' }} />
              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Radar name="得分" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="学习趋势">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={data.trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#475569' }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Tooltip />
              <Line type="monotone" dataKey="score" stroke="#3b82f6" strokeWidth={2.5} dot={{ fill: '#3b82f6', r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="📋 评估总结">
        <div className="space-y-4">
          <div className="rounded-lg bg-slate-50 p-4 text-sm leading-7 text-slate-700">
            <p>{data.summary}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-green-50 p-3 border border-green-100">
              <p className="font-medium text-green-700">✅ 优势领域</p>
              <p className="text-sm text-green-600">
                {data.dimensions.filter(d => d.score >= 80).map(d => d.subject).join('、') || '暂无'}
              </p>
            </div>
            <div className="rounded-lg bg-yellow-50 p-3 border border-yellow-100">
              <p className="font-medium text-yellow-700">⚠️ 待提升</p>
              <p className="text-sm text-yellow-600">
                {data.dimensions.filter(d => d.score < 60).map(d => d.subject).join('、') || '继续保持！'}
              </p>
            </div>
            <div className="rounded-lg bg-blue-50 p-3 border border-blue-100">
              <p className="font-medium text-blue-700">🎯 建议</p>
              <p className="text-sm text-blue-600">每周 2 次模型调参练习</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
