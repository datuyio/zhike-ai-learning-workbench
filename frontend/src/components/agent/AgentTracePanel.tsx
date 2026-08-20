import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, XCircle, ChevronDown, ChevronRight } from 'lucide-react';

interface AgentTrace {
  id: string;
  agentName: string;
  status: 'running' | 'success' | 'failed';
  input: string;
  output: string;
  timestamp: string;
  duration: number;
}

interface AgentTracePanelProps {
  sessionId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function AgentTracePanel({ sessionId, isOpen, onClose }: AgentTracePanelProps): JSX.Element | null {
  const [traces, setTraces] = useState<AgentTrace[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!isOpen || !sessionId) return;

    setLoading(true);
    fetch(`/api/v1/agent/trace?session_id=${sessionId}`)
      .then((res) => {
        if (!res.ok) throw new Error('API 请求失败');
        return res.json();
      })
      .then((data) => {
        setTraces(data.traces || []);
        setLoading(false);
      })
      .catch(() => {
        // Mock 数据（后端不可用时使用）
        setTraces([
          {
            id: '1',
            agentName: '意图识别 Agent',
            status: 'success',
            input: '帮我解释一下反向传播算法',
            output: '识别为：知识问答意图',
            timestamp: new Date(Date.now() - 5000).toLocaleString(),
            duration: 120,
          },
          {
            id: '2',
            agentName: '知识检索 Agent',
            status: 'success',
            input: '查询：反向传播算法',
            output: '找到 3 条相关文档',
            timestamp: new Date(Date.now() - 3000).toLocaleString(),
            duration: 340,
          },
          {
            id: '3',
            agentName: '内容生成 Agent',
            status: 'running',
            input: '用通俗语言解释反向传播',
            output: '生成中...',
            timestamp: new Date(Date.now() - 1000).toLocaleString(),
            duration: 0,
          },
        ]);
        setLoading(false);
      });
  }, [isOpen, sessionId]);

  const toggleExpand = (id: string) => {
    const newSet = new Set(expandedItems);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedItems(newSet);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
      case 'running': return <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />;
      case 'failed': return <XCircle className="h-3.5 w-3.5 text-red-500" />;
      default: return <span className="h-3.5 w-3.5 rounded-full bg-slate-300" />;
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'success': return '✅ 成功';
      case 'running': return '⏳ 运行中';
      case 'failed': return '❌ 失败';
      default: return '⏳ 等待';
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'success': return 'bg-green-100 text-green-700';
      case 'running': return 'bg-blue-100 text-blue-700';
      case 'failed': return 'bg-red-100 text-red-700';
      default: return 'bg-slate-100 text-slate-500';
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-[420px] border-l border-slate-200 bg-white shadow-2xl flex flex-col z-50">
      {/* 头部 */}
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 bg-slate-50/80">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100">
            <span className="text-sm">🤖</span>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Agent 工作流</h2>
            <p className="text-xs text-slate-500">多智能体协作追踪</p>
          </div>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-200 transition-colors text-slate-400 hover:text-slate-600">✕</button>
      </div>

      {/* 统计条 */}
      <div className="flex items-center gap-4 border-b border-slate-100 px-4 py-2 text-xs">
        <span className="text-slate-500">共 <strong className="text-slate-700">{traces.length}</strong> 个步骤</span>
        <span className="text-slate-300">|</span>
        <span className="text-green-600">✅ {traces.filter(t => t.status === 'success').length} 成功</span>
        <span className="text-blue-600">⏳ {traces.filter(t => t.status === 'running').length} 运行中</span>
        <span className="text-red-600">❌ {traces.filter(t => t.status === 'failed').length} 失败</span>
      </div>

      {/* 内容 */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex h-32 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载追踪数据...
          </div>
        ) : traces.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center text-slate-400">
            <span className="text-2xl mb-2">🔍</span>
            <p className="text-sm">暂无 Agent 调用记录</p>
          </div>
        ) : (
          <div className="relative pl-6">
            <div className="absolute left-1.5 top-3 h-[calc(100%-24px)] w-0.5 bg-gradient-to-b from-indigo-300 to-slate-200" />
            {traces.map((trace) => {
              const isExpanded = expandedItems.has(trace.id);
              return (
                <div key={trace.id} className="relative mb-5">
                  <div className="absolute -left-[22px] top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-white ring-4 ring-white">
                    {getStatusIcon(trace.status)}
                  </div>
                  <div
                    className={`rounded-lg border ${trace.status === 'running' ? 'border-blue-200 bg-blue-50/30' : 'border-slate-200 bg-white'} p-3 hover:shadow-md transition-shadow cursor-pointer`}
                    onClick={() => toggleExpand(trace.id)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-900">{trace.agentName}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${getStatusClass(trace.status)}`}>
                          {getStatusLabel(trace.status)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        {trace.duration > 0 && <span>{trace.duration}ms</span>}
                        {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      </div>
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">{trace.timestamp}</div>
                    {isExpanded && (
                      <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                        <div>
                          <div className="text-xs font-medium text-slate-400">📥 输入</div>
                          <div className="mt-0.5 rounded bg-slate-50 px-2 py-1 text-xs text-slate-600">{trace.input}</div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-slate-400">📤 输出</div>
                          <div className="mt-0.5 rounded bg-slate-50 px-2 py-1 text-xs text-slate-600">{trace.output}</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-t border-slate-100 px-4 py-2 text-center text-[10px] text-slate-400">点击卡片查看输入输出详情</div>
    </div>
  );
}
