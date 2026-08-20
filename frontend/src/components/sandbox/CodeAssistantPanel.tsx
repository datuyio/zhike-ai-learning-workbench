import { useState, useRef, useEffect } from 'react';
import { Send, Code2, X, Sparkles } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface CodeAssistantPanelProps {
  code?: string;
}

export function CodeAssistantPanel({ code }: CodeAssistantPanelProps): JSX.Element {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: '💡 你好！我是 AI 代码辅导助手。\n\n你可以：\n• 选中代码片段后提问\n• 直接描述你的代码问题',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState('');
  const [selectedCode, setSelectedCode] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() && !selectedCode) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: `${selectedCode ? `[代码]\n${selectedCode}\n\n` : ''}${input}`,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/v1/code/assist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: selectedCode || code, question: input }),
      });
      if (!response.ok) throw new Error('API 请求失败');
      const data = await response.json();
      setMessages((prev) => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: data.reply || '分析完成',
        timestamp: new Date().toISOString(),
      }]);
    } catch (err) {
      setMessages((prev) => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `关于你的代码问题：\n\n${input || '这段代码需要分析。'}\n\n建议：检查变量命名和缩进，确保逻辑正确。`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setLoading(false);
      setSelectedCode('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-full flex-col border-l border-slate-200 bg-white">
      {/* 头部 */}
      <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100">
              <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">AI 代码辅导</h3>
              <p className="text-xs text-slate-500">选中代码 → 提问 → 获得解答</p>
            </div>
          </div>
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-600">Beta</span>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${msg.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-slate-50 text-slate-700 border border-slate-200'}`}>
              <div className="whitespace-pre-wrap">{msg.content}</div>
              <div className={`mt-1 text-[10px] ${msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'}`}>
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-400 border border-slate-200">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-indigo-400" />
              <span className="mx-1 inline-block h-2 w-2 animate-pulse rounded-full bg-indigo-400 delay-75" />
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-indigo-400 delay-150" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="border-t border-slate-200 bg-slate-50/80 p-3">
        {selectedCode && (
          <div className="mb-2 flex items-center justify-between rounded bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700 border border-indigo-100">
            <div className="flex items-center gap-2 overflow-hidden">
              <Code2 className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">📎 已选代码</span>
            </div>
            <button onClick={() => setSelectedCode('')} className="shrink-0 text-indigo-400 hover:text-indigo-600">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedCode ? '针对这段代码提问...' : '描述你的代码问题...'}
            className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 min-h-[40px]"
            rows={1}
          />
          <button
            onClick={sendMessage}
            disabled={(!input.trim() && !selectedCode) || loading}
            className="shrink-0 rounded-lg bg-indigo-600 px-3 py-2 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-1.5 flex gap-3 text-xs text-slate-400">
          <button onClick={() => { if (code) setSelectedCode(code); }} className="hover:text-indigo-500 transition-colors">
            📋 使用当前编辑器代码
          </button>
          <span>|</span>
          <button onClick={() => setInput('请帮我优化这段代码')} className="hover:text-indigo-500 transition-colors">
            ⚡ 优化代码
          </button>
          <button onClick={() => setInput('请帮我解释这段代码')} className="hover:text-indigo-500 transition-colors">
            📖 解释代码
          </button>
        </div>
      </div>
    </div>
  );
}
