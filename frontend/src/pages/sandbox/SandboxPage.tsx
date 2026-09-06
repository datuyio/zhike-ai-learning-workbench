import { useState } from 'react';
import { PageHeader } from '../../components/shared/PageHeader';
import CodeEditor from '../../components/sandbox/CodeEditor';
import { CodeAssistantPanel } from '../../components/sandbox/CodeAssistantPanel';

/**
 * 在线编程实验页。
 * 左侧为代码编辑器与运行控制台，右侧为 AI 代码辅导面板。
 */
export default function SandboxPage(): JSX.Element {
  const [currentCode, setCurrentCode] = useState('');

  return (
    <div className="space-y-6 px-6 pb-8">
      <PageHeader title="在线编程实验" subtitle="编写、运行和测试代码，右侧 AI 助手随时解答问题" />

      <div className="flex gap-6">
        <div className="min-w-0 flex-1">
          <CodeEditor height="520px" onChange={(code) => setCurrentCode(code || '')} />
        </div>

        <div className="h-[560px] w-[420px] shrink-0">
          <CodeAssistantPanel code={currentCode} />
        </div>
      </div>
    </div>
  );
}