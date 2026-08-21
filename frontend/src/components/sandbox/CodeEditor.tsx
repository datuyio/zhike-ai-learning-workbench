import React, { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { api } from '../../api/endpoints'

interface CodeEditorProps {
  initialCode?: string
  language?: 'python' | 'javascript'
  height?: string
  onChange?: (code: string) => void
}

const defaultPythonCode = `# 在此编写 Python 代码
print("Hello, World!")

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(f"fibonacci(10) = {fibonacci(10)}")
`

const defaultJavaScriptCode = `console.log('Hello from sandbox');

function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

console.log(\`fibonacci(10) = \${fibonacci(10)}\`);
`

/**
 * CodeEditor
 * - 支持 Python（通过后端 API）和 JavaScript（前端 iframe 沙箱）
 */
export default function CodeEditor({
  initialCode,
  language = 'python',
  height = '300px',
  onChange,
}: CodeEditorProps): JSX.Element {
  const [currentLanguage, setCurrentLanguage] = useState<'python' | 'javascript'>(language)
  const [code, setCode] = useState(initialCode ?? (language === 'python' ? defaultPythonCode : defaultJavaScriptCode))
  const [logs, setLogs] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [executionTime, setExecutionTime] = useState<number | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)

  useEffect(() => {
    if (currentLanguage !== 'javascript') return

    // 监听来自 iframe 的消息，展示控制台输出
    function onMessage(e: MessageEvent) {
      if (!e.data) return
      if (iframeRef.current && e.source !== iframeRef.current.contentWindow) return
      const { type, payload } = e.data
      if (type === 'sandbox:console') {
        setLogs((s) => [...s, String(payload)])
      }
      if (type === 'sandbox:error') {
        setLogs((s) => [...s, `Error: ${String(payload)}`])
      }
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [currentLanguage])

  const runJavaScript = () => {
    setLogs([])
    setExecutionTime(null)
    const html = buildSandboxHtml(code)
    if (iframeRef.current) {
      iframeRef.current.srcdoc = html
    }
  }

  const runPython = async () => {
    setLoading(true)
    setLogs([])
    setExecutionTime(null)
    const startTime = performance.now()

    try {
      const data = await api.executeSandbox({ code, language: 'python' })
      const endTime = performance.now()
      setExecutionTime(Math.round(endTime - startTime))

      if (data.output) {
        setLogs((s) => [...s, String(data.output)])
      }
      if (data.error) {
        setLogs((s) => [...s, `Error: ${String(data.error)}`])
      }
    } catch (err) {
      console.warn('Python 代码执行失败:', err)
      setLogs([err instanceof Error ? err.message : 'Python 代码执行失败，请稍后重试'])
    } finally {
      setLoading(false)
    }
  }

  const run = () => {
    if (currentLanguage === 'python') {
      runPython()
      return
    }
    runJavaScript()
  }

  const handleLanguageChange = (newLang: 'python' | 'javascript') => {
    setCurrentLanguage(newLang)
    setLogs([])
    setExecutionTime(null)
    setCode(newLang === 'python' ? defaultPythonCode : defaultJavaScriptCode)
    onChange && onChange(newLang === 'python' ? defaultPythonCode : defaultJavaScriptCode)
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: 8, padding: 8, alignItems: 'center', borderBottom: '1px solid #eee', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          语言：
          <select
            value={currentLanguage}
            onChange={(e) => handleLanguageChange(e.target.value as 'python' | 'javascript')}
            style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #d1d5db', background: 'white', fontSize: 13 }}
          >
            <option value="python">🐍 Python</option>
            <option value="javascript">🟨 JavaScript</option>
          </select>
        </label>
        <button
          onClick={run}
          disabled={loading}
          style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: loading ? '#94a3b8' : '#3b82f6', color: 'white', fontSize: 13, cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          {loading ? '⏳ 运行中...' : '▶ 运行'}
        </button>
        <button
          onClick={() => setLogs([])}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #d1d5db', background: 'white', fontSize: 13, cursor: 'pointer' }}
        >
          清空输出
        </button>
        <div style={{ marginLeft: 'auto', color: '#6b7280', fontSize: 13 }}>
          当前模式：{currentLanguage === 'python' ? 'Python（后端）' : 'JavaScript（前端沙箱）'}
        </div>
        {executionTime !== null && (
          <div style={{ color: '#6b7280', fontSize: 13 }}>执行时间：{executionTime}ms</div>
        )}
      </div>

      <div style={{ height }}>
        <Editor
          height={height}
          language={currentLanguage === 'python' ? 'python' : 'javascript'}
          value={code}
          onChange={(v) => {
            setCode(v ?? '')
            onChange && onChange(v ?? '')
          }}
          options={{ minimap: { enabled: false }, fontSize: 13, lineNumbers: 'on', automaticLayout: true }}
        />
      </div>

      <div style={{ height: 200, display: 'flex', borderTop: '1px solid #eee' }}>
        <div style={{ flex: 1, padding: 8, background: '#0f172a', color: '#e6eef8', fontFamily: 'monospace', fontSize: 13, overflow: 'auto' }}>
          {logs.length === 0 ? (
            <div style={{ opacity: 0.6 }}>还没有输出，点击运行查看结果</div>
          ) : (
            logs.map((l, i) => <div key={i}>{l}</div>)
          )}
        </div>

        <iframe
          ref={iframeRef}
          title="code-sandbox"
          sandbox="allow-scripts"
          style={{ width: 0, height: 0, border: 'none' }}
        />
      </div>
    </div>
  )
}

function buildSandboxHtml(code: string) {
  const safeCode = JSON.stringify(code)
  return `<!doctype html>
  <html>
  <head>
    <meta charset="utf-8" />
  </head>
  <body>
    <script>
      (function(){
        function send(type, payload){
          try{ parent.postMessage({ type: 'sandbox:' + type, payload: String(payload) }, '*') }catch(e){}
        }
        const origLog = console.log.bind(console);
        const origError = console.error.bind(console);
        console.log = function(){
          try{ send('console', Array.from(arguments).map(a=>String(a)).join(' ')) }catch(e){}
          origLog.apply(null, arguments);
        };
        console.error = function(){
          try{ send('error', Array.from(arguments).map(a=>String(a)).join(' ')) }catch(e){}
          origError.apply(null, arguments);
        };
        window.onerror = function(msg, src, line, col, err){
          send('error', msg + ' (' + src + ':' + line + ':' + col + ')');
        };
      })();
    </script>
    <script>
      try {
        const __code = JSON.parse(${safeCode});
        (0, eval)(__code);
      } catch (e) {
        try{ parent.postMessage({ type: 'sandbox:error', payload: String(e) }, '*') }catch(ex){}
      }
    </script>
  </body>
  </html>`
}
