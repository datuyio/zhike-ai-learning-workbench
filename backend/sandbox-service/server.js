// 智课代码沙箱微服务
// 基于 Node + Pyodide 在 WASM 沙箱中执行用户提交的 Python 代码
// FastAPI 后端通过 HTTP 转发调用，本服务不直接对外暴露
//
// 依赖位置：
//   默认使用本服务目录下的 node_modules（即 backend/sandbox-service/node_modules），
//   在该目录执行 npm install 即可装齐 pyodide 与 express，无需额外配置。
//   若本机希望把体积较大的 Pyodide 依赖放到其他盘符避免占用项目目录，
//   可用环境变量 SANDBOX_NODE_MODULES 指向自备依赖目录（仅本机优化，不作为项目默认）。
//
// 安全设计：
// - Pyodide 本身运行在 WASM 沙箱中，无法访问宿主文件系统与网络
// - 输出通过 setStdout/setStderr 重定向，运行结束恢复默认
// - 执行放在独立 worker 线程，主线程持 SharedArrayBuffer 中断缓冲区，
//   超时后写入 SIGINT 触发 KeyboardInterrupt，能真正中断死循环等长耗时代码
// - 默认仅监听 127.0.0.1，不对外网暴露（如需容器内访问经 SANDBOX_HOST 显式放开）
//
// 线程模型说明：
//   Pyodide 跑同步 Python 时会霸占所在线程的事件循环。若在主线程执行，
//   超时定时器的回调永远排不上队，超时形同虚设。因此把 Pyodide 放进 worker，
//   主线程不被阻塞，到点写中断信号即可打断 worker 中的执行。

import { fileURLToPath, pathToFileURL } from "node:url";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { Worker } from "node:worker_threads";

const PORT = process.env.PORT || 8003;
// 监听地址：默认仅 127.0.0.1，避免沙箱微服务被外网直连（危险模块校验在后端，微服务本身不校验）
const HOST = process.env.SANDBOX_HOST || "127.0.0.1";
// 本服务文件所在目录（ESM 下没有 __dirname，用 import.meta.url 推导）
const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Pyodide/express 依赖所在目录，默认用本服务目录下的 node_modules；
// 仅本机优化时可经 SANDBOX_NODE_MODULES 指向外部目录（如 D:/zhike-sandbox-deps/node_modules）
const NODE_MODULES_DIR = process.env.SANDBOX_NODE_MODULES || path.join(__dirname, "node_modules");
// 代码长度上限（与后端 SANDBOX_MAX_CODE_BYTES 对齐）
const MAX_CODE_BYTES = Number(process.env.MAX_CODE_BYTES || 65536);
// 执行超时（毫秒），略小于后端 SANDBOX_EXECUTION_TIMEOUT_SECONDS
const EXEC_TIMEOUT_MS = Number(process.env.EXEC_TIMEOUT_MS || 9000);

let worker = null;
let workerReady = false;
// 中断缓冲区：主线程写、worker 线程读。Uint8Array + SharedArrayBuffer 才能跨线程共享
let interruptBuffer = null;
// 自增请求 id，用于把超时回调匹配到对应的 pending 请求
let nextRequestId = 1;
const pending = new Map();

/**
 * 按绝对路径动态 import 加载依赖包（仅主线程用于加载 express）。
 * ESM 无法用 NODE_PATH，因此统一指向 NODE_MODULES_DIR 中的具体入口文件解析。
 *
 * ESM 入口解析优先级：package.json 的 exports["."].import > module > main > index.js。
 * Node 的 ESM 解析器不支持目录 import，必须指向具体文件。
 */
async function loadModule(pkgName) {
  const pkgDir = path.join(NODE_MODULES_DIR, pkgName);
  if (!existsSync(pkgDir)) {
    throw new Error(
      `未找到包 ${pkgName}，请确认 SANDBOX_NODE_MODULES 指向正确（当前: ${NODE_MODULES_DIR}）`
    );
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
 * 启动 worker 并完成 Pyodide 首次加载。
 * 创建 SharedArrayBuffer 中断缓冲区并交给 worker，主线程保留引用以便超时写信号。
 */
function startWorker() {
  interruptBuffer = new Uint8Array(new SharedArrayBuffer(1));
  interruptBuffer[0] = 0;

  worker = new Worker(path.join(__dirname, "sandbox-worker.js"), {
    workerData: { nodeModulesDir: NODE_MODULES_DIR },
  });

  worker.on("message", (msg) => {
    if (msg.type === "ready") {
      workerReady = true;
      console.log("[sandbox] Pyodide 加载完成（worker）");
      return;
    }
    if (msg.type === "result") {
      const ctx = pending.get(msg.requestId);
      if (!ctx) return; // 已被超时清理
      clearTimeout(ctx.timer);
      clearTimeout(ctx.recoveryTimer);
      pending.delete(msg.requestId);
      if (!ctx.resolved) {
        ctx.resolved = true;
        // 只透出业务字段，内部 type/requestId 不暴露给调用方
        ctx.resolve({
          output: msg.output,
          error: msg.error,
          execution_time_ms: msg.execution_time_ms,
        });
      }
    }
  });

  worker.on("error", (err) => {
    console.error("[sandbox] worker 异常:", err);
    // worker 崩了：把所有 pending 请求都失败掉，并尝试重启
    for (const [id, ctx] of pending) {
      clearTimeout(ctx.timer);
      ctx.resolve({
        output: "",
        error: "沙箱执行线程异常，请重试",
        execution_time_ms: 0,
      });
    }
    pending.clear();
    workerReady = false;
    // 重启 worker，恢复后续可用性
    setTimeout(() => startWorker().catch(() => process.exit(1)), 500);
  });

  worker.on("exit", (code) => {
    if (code !== 0) console.warn(`[sandbox] worker 退出，code=${code}`);
  });

  worker.postMessage({ cmd: "setInterruptBuffer", buffer: interruptBuffer });
}

/**
 * 在 worker 中执行一段 Python 代码，超时则写 SIGINT 中断。
 *
 * @param {string} code - 待执行的 Python 源代码
 * @returns {Promise<{output: string, error: string, execution_time_ms: number}>}
 */
function runPython(code) {
  if (!workerReady) {
    return Promise.resolve({
      output: "",
      error: "沙箱尚未就绪，请稍后重试",
      execution_time_ms: 0,
    });
  }
  const requestId = nextRequestId++;
  return new Promise((resolve) => {
    const ctx = { resolve, resolved: false, timer: null };
    ctx.timer = setTimeout(() => {
      // 主线程未被 Pyodide 阻塞，定时器能正常触发：往中断缓冲区写 SIGINT(2)，
      // Pyodide 轮询到即抛 KeyboardInterrupt，worker 的 try/catch 会接住并回 result。
      // 中断后 worker 仍健康，可继续处理后续请求（已验证）。
      if (interruptBuffer) interruptBuffer[0] = 2;
      // 给 worker 一点时间让中断生效并返回真实 result；若仍无响应（异常情况）再兜底返回超时
      ctx.recoveryTimer = setTimeout(() => {
        if (ctx.resolved) return;
        pending.delete(requestId);
        resolve({
          output: "",
          error: `执行超时（${EXEC_TIMEOUT_MS / 1000} 秒）`,
          execution_time_ms: EXEC_TIMEOUT_MS,
        });
      }, 800);
    }, EXEC_TIMEOUT_MS);

    pending.set(requestId, ctx);
    worker.postMessage({ cmd: "run", code, requestId });
  });
}

/**
 * 重建 worker：终止当前 worker 并启动新的。
 * 仅在 worker 抛出未捕获异常（真正崩溃）时调用，保证服务自愈。
 * 正常超时中断不会触发此函数——中断后 worker 仍可继续服务。
 */
function recoverWorker() {
  workerReady = false;
  if (interruptBuffer) interruptBuffer[0] = 0;
  if (worker) {
    try { worker.terminate(); } catch { /* 忽略终止失败 */ }
  }
  for (const [, c] of pending) {
    clearTimeout(c.timer);
    clearTimeout(c.recoveryTimer);
  }
  pending.clear();
  setTimeout(() => startWorker(), 100);
}

const expressMod = await loadModule("express");
const express = expressMod.default;
const app = express();
app.use(express.json({ limit: "1mb" }));

// 健康检查端点，供后端探活
app.get("/health", (_req, res) => {
  res.json({ status: workerReady ? "ready" : "loading" });
});

// 代码执行端点，由 FastAPI 后端转发调用
app.post("/execute", async (req, res) => {
  const { code, language } = req.body || {};
  if (typeof code !== "string" || code.length === 0) {
    return res.status(400).json({ error: "code 不能为空" });
  }
  if (Buffer.byteLength(code, "utf8") > MAX_CODE_BYTES) {
    return res.status(400).json({ error: `代码体积超过上限（${MAX_CODE_BYTES / 1024} KB）` });
  }
  if (language && language !== "python") {
    return res.status(400).json({ error: `暂不支持的语言：${language}` });
  }

  try {
    const result = await runPython(code);
    return res.json(result);
  } catch (err) {
    console.error("[sandbox] 执行异常:", err);
    return res.status(500).json({
      output: "",
      error: "沙箱内部错误",
      execution_time_ms: 0,
    });
  }
});

// 启动 worker 预加载 Pyodide，完成后开 HTTP 服务
startWorker();
const readyChecker = setInterval(() => {
  if (workerReady) {
    clearInterval(readyChecker);
    app.listen(PORT, HOST, () => {
      console.log(`[sandbox] 代码沙箱微服务已启动，监听 http://${HOST}:${PORT}`);
    });
  }
}, 100);
// 兜底：若 60 秒仍未就绪，报错退出
setTimeout(() => {
  if (!workerReady) {
    console.error("[sandbox] Pyodide 加载超时，服务退出");
    process.exit(1);
  }
}, 60000);
