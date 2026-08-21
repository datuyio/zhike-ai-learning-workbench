// 沙箱执行 worker
// 在独立线程中加载并运行 Pyodide，使主线程（HTTP 服务）不被同步执行的 Python 代码阻塞，
// 从而让超时中断机制能够真正生效。
//
// 与主线程的通信约定（parentPort 消息）：
//   入：{ cmd: "setInterruptBuffer", buffer }  设置中断缓冲区并完成 Pyodide 首次加载，加载完回 ready
//       { cmd: "run", code }                    执行一段 Python 代码
//   出：{ type: "ready" }                       Pyodide 就绪
//       { type: "result", output, error, execution_time_ms }  执行结果
//
// 中断原理：主线程持 SharedArrayBuffer 引用，超时后写入 SIGINT(2)；
// Pyodide 在字节码执行间隙轮询该缓冲区，发现非零即抛 KeyboardInterrupt。
// 必须用同步 runPython（而非 runPythonAsync），否则中断异常会冒到 asyncio 事件循环外层，
// 无法被 try/catch 正常捕获。

import { parentPort } from "node:worker_threads";
import { pathToFileURL } from "node:url";
import path from "node:path";

// 依赖目录由主线程通过 workerData 传入，保持与主线程一致的解析逻辑
import { workerData } from "node:worker_threads";
const NODE_MODULES_DIR = workerData.nodeModulesDir;

let pyodide = null;
let interruptBuffer = null;

/**
 * 按绝对路径动态 import 加载依赖包。
 * 与主线程 loadModule 同策略：解析 package.json 入口后指向具体文件 import。
 */
async function loadModule(pkgName) {
  const pkgDir = path.join(NODE_MODULES_DIR, pkgName);
  const { existsSync, readFileSync } = await import("node:fs");
  if (!existsSync(pkgDir)) {
    throw new Error(`未找到包 ${pkgName}，请确认依赖已安装（当前目录: ${NODE_MODULES_DIR}）`);
  }
  const pkgJsonPath = path.join(pkgDir, "package.json");
  let entry = "index.js";
  try {
    const pkgJson = JSON.parse(readFileSync(pkgJsonPath, "utf8"));
    if (pkgJson.exports && pkgJson.exports["."] && pkgJson.exports["."].import) {
      entry = pkgJson.exports["."].import;
    } else {
      entry = pkgJson.module || pkgJson.main || "index.js";
    }
  } catch {
    // 回退到 index.js
  }
  return import(pathToFileURL(path.join(pkgDir, entry)).href);
}

/**
 * 首次加载 Pyodide 运行时（单例）。
 * 首次加载需拉起 wasm 与标准库，较慢；后续复用同一实例。
 */
async function ensurePyodide() {
  if (pyodide) return pyodide;
  const mod = await loadModule("pyodide");
  pyodide = await mod.loadPyodide({
    indexURL: path.join(NODE_MODULES_DIR, "pyodide") + "/",
  });
  return pyodide;
}

/**
 * 执行一段 Python 代码并捕获标准输出、标准错误与异常。
 * 使用同步 runPython，使 KeyboardInterrupt 能被 try/catch 正常接住。
 *
 * @param {string} code - 待执行的 Python 源代码
 * @returns {Promise<{output: string, error: string, execution_time_ms: number}>}
 */
async function runPython(code) {
  const py = await ensurePyodide();
  // 每次执行前清零中断缓冲区，避免上次残留信号误触发
  if (interruptBuffer) interruptBuffer[0] = 0;

  let stdout = "";
  let stderr = "";
  py.setStdout({ batched: (chunk) => (stdout += chunk) });
  py.setStderr({ batched: (chunk) => (stderr += chunk) });

  const start = Date.now();
  let errorText = "";
  try {
    py.runPython(code);
  } catch (err) {
    // Pyodide 抛出的可能是 Python Proxy 对象，访问 .message 偶尔会二次抛错，单独兜底
    let msg = "";
    try {
      msg = err && err.message ? err.message : "";
    } catch {
      msg = "";
    }
    errorText = (stderr ? stderr + "\n" : "") + (msg || String(err) || "执行出错");
  } finally {
    py.setStdout({ batched: () => {} });
    py.setStderr({ batched: () => {} });
  }

  return { output: stdout, error: errorText, execution_time_ms: Date.now() - start };
}

parentPort.on("message", async (msg) => {
  try {
    if (msg.cmd === "setInterruptBuffer") {
      interruptBuffer = msg.buffer;
      const py = await ensurePyodide();
      py.setInterruptBuffer(interruptBuffer);
      parentPort.postMessage({ type: "ready" });
      return;
    }
    if (msg.cmd === "run") {
      const result = await runPython(msg.code);
      // 必须回传 requestId，主线程据此把 result 匹配到对应的 pending 请求
      parentPort.postMessage({ type: "result", requestId: msg.requestId, ...result });
    }
  } catch (outer) {
    // 任何未预期异常都转成正常 result 返回，避免 worker 因单次执行异常而崩掉
    parentPort.postMessage({
      type: "result",
      output: "",
      error: "沙箱内部错误: " + (outer && outer.message ? outer.message : String(outer)),
      execution_time_ms: 0,
    });
  }
});
