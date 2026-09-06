import { useEffect, useRef, useState } from 'react';
import { Bot, Send, ShieldCheck, Sparkles, CheckCircle, XCircle } from 'lucide-react';
import {
  taAgentMessage,
  taAgentConfirm,
  type TaAgentMessageResponse,
  type TaAgentDataFact,
  type TaAgentPendingConfirmation,
} from '../../api/ta';
import { PageHeader, PageHeaderToolbar } from '../../components/shared/PageHeader';
import { CitationEvidencePanel } from '../../components/citation/CitationEvidencePanel';
import type { Citation } from '../../types';

/** 教师端对话消息：用户提问或 Agent 回答（含引用、数据事实与待确认操作）。 */
type TaChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  dataFacts: TaAgentDataFact[];
  refused: boolean;
  route: string;
  pendingConfirmation: TaAgentPendingConfirmation | null;
  confirmationResolved?: boolean;
};

function DataFactCards({ facts }: { facts: TaAgentDataFact[] }): JSX.Element | null {
  if (facts.length === 0) return null;
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
      {facts.map((fact) => (
        <div key={fact.label} className="rounded-lg border border-zinc-100 bg-white p-3">
          <div className="text-xs text-zinc-400">{fact.label}</div>
          <div className="mt-1 text-lg font-semibold text-zinc-800">{fact.value}</div>
          {fact.detail ? <div className="mt-0.5 text-xs text-zinc-400">{fact.detail}</div> : null}
        </div>
      ))}
    </div>
  );
}

function ConfirmationBar({
  pending,
  onConfirm,
  onCancel,
  resolved,
}: {
  pending: TaAgentPendingConfirmation;
  onConfirm: () => void;
  onCancel: () => void;
  resolved: boolean;
}): JSX.Element {
  if (resolved) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        <CheckCircle className="h-4 w-4" />
        操作已处理
      </div>
    );
  }
  return (
    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
        <ShieldCheck className="h-4 w-4" />
        待确认操作：{pending.summary}
      </div>
      <p className="mt-1 text-xs text-amber-600">确认后将真正执行（例如布置作业到班级、发布公告），请核对内容。</p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={onConfirm}
          className="flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
        >
          <CheckCircle className="h-3.5 w-3.5" />
          确认执行
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
        >
          <XCircle className="h-3.5 w-3.5" />
          取消
        </button>
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
  onConfirm,
  onCancel,
}: {
  message: TaChatMessage;
  onConfirm: (message: TaChatMessage) => void;
  onCancel: (message: TaChatMessage) => void;
}): JSX.Element {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white p-4 text-sm leading-relaxed text-zinc-700">
          {message.refused ? (
            <div className="flex items-start gap-2 text-amber-700">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{message.content}</span>
            </div>
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>
        {message.pendingConfirmation ? (
          <ConfirmationBar
            pending={message.pendingConfirmation}
            onConfirm={() => onConfirm(message)}
            onCancel={() => onCancel(message)}
            resolved={Boolean(message.confirmationResolved)}
          />
        ) : null}
        <DataFactCards facts={message.dataFacts} />
        {message.citations.length > 0 ? (
          <div className="mt-3">
            <CitationEvidencePanel citations={message.citations} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function UserBubble({ message }: { message: TaChatMessage }): JSX.Element {
  return (
    <div className="flex items-start justify-end gap-3">
      <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-zinc-900 px-4 py-3 text-sm leading-relaxed text-white">
        {message.content}
      </div>
    </div>
  );
}

/**
 * 教师端 AI 教学助手页：有身份、能聊天、能布置任务的智能体。
 *
 * 后端通过 function calling 调用工具（查班级/学生/题库/知识库等只读操作直接执行；
 * 布置作业/测验/公告等写操作返回待确认，教师点击确认后真正执行）。
 */
export function TaAiAssistantPage(): JSX.Element {
  const [messages, setMessages] = useState<TaChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const idCounter = useRef(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function handleSend(): Promise<void> {
    const text = input.trim();
    if (!text || loading) return;
    setError(null);
    const userMessage: TaChatMessage = {
      id: `u-${idCounter.current++}`,
      role: 'user',
      content: text,
      citations: [],
      dataFacts: [],
      refused: false,
      route: '',
      pendingConfirmation: null,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    try {
      const response: TaAgentMessageResponse = await taAgentMessage({
        message: text,
        conversation_id: conversationId,
      });
      setConversationId(response.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${idCounter.current++}`,
          role: 'assistant',
          content: response.answer,
          citations: response.citations ?? [],
          dataFacts: response.data_facts ?? [],
          refused: response.refused,
          route: response.route,
          pendingConfirmation: response.pending_confirmation ?? null,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 助教暂时不可用，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(message: TaChatMessage): Promise<void> {
    if (!message.pendingConfirmation) return;
    setError(null);
    try {
      await taAgentConfirm({
        confirmation_id: message.pendingConfirmation.confirmation_id,
        action: 'confirm',
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, confirmationResolved: true, pendingConfirmation: null } : m)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认执行失败，请稍后重试。');
    }
  }

  async function handleCancel(message: TaChatMessage): Promise<void> {
    if (!message.pendingConfirmation) return;
    setError(null);
    try {
      await taAgentConfirm({
        confirmation_id: message.pendingConfirmation.confirmation_id,
        action: 'cancel',
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, confirmationResolved: true, pendingConfirmation: null } : m)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消失败，请稍后重试。');
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col px-6 py-6">
      <PageHeader
        title="AI 教学助手"
        subtitle="我是「智课 AI 教学助手」，可以帮你查班级、看学情、布置作业、创建测验、发布公告、生成教案，还能基于课程知识库答疑（零幻觉）。"
      />
      <PageHeaderToolbar variant="actions">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Sparkles className="h-4 w-4 text-amber-500" />
          有身份 · 能聊天 · 能布置任务
        </div>
      </PageHeaderToolbar>

      <div className="mt-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-50">
        <div className="flex items-center gap-2 border-b border-zinc-200 bg-white px-4 py-2.5 text-xs text-zinc-500">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
          写操作（布置作业/测验/公告）需你确认后才会执行；只读查询与知识库问答直接返回
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-900 text-white">
                <Bot className="h-7 w-7" />
              </div>
              <div className="text-lg font-semibold text-zinc-700">向 AI 教学助手提问</div>
              <p className="max-w-md text-sm text-zinc-400">
                例如：「我有几个班级」「布置一份作业」「查一下题库」「什么是高可用系统」
              </p>
            </div>
          ) : (
            messages.map((message) =>
              message.role === 'user' ? (
                <UserBubble key={message.id} message={message} />
              ) : (
                <AssistantBubble
                  key={message.id}
                  message={message}
                  onConfirm={(m) => void handleConfirm(m)}
                  onCancel={(m) => void handleCancel(m)}
                />
              ),
            )
          )}
          {loading ? (
            <div className="flex items-center gap-2 px-1 text-sm text-zinc-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" />
              <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" style={{ animationDelay: '0.15s' }} />
              <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" style={{ animationDelay: '0.3s' }} />
              正在思考…
            </div>
          ) : null}
          {error ? <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div> : null}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-zinc-200 bg-white p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              rows={2}
              placeholder="输入你的教学任务，Enter 发送，Shift+Enter 换行"
              className="min-h-[44px] flex-1 resize-none rounded-xl border border-zinc-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
            />
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={loading || !input.trim()}
              className="flex h-11 items-center gap-2 rounded-xl bg-zinc-900 px-4 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
