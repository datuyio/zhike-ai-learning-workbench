// 智课代码沙箱微服务
// 基于 Node + Pyodide 在 WASM 沙箱中执行用户提交的 Python 代码
// FastAPI 后端通过 HTTP 转发调用，本服务不直接对外暴露
//
// 依赖位置：
//   Pyodide 体积较大（数百 MB），实际 node_modules 安装在 D 盘专用目录，
//   通过环境变量 SANDBOX_NODE_MODULES 指向（默认 D:/zhike-sandbox-deps/node_modules），
//   避免污染项目仓库与 C 盘。
//
// 安全设计：
// - Pyodide 本身运行在 WASM 沙箱中，无法访问宿主文件系统与网络
// - 输出通过 setStdout/setStderr 重定向，运行结束恢复默认
// - 执行超时由 Promise.race 兜底，超时自动返回错误而非无限阻塞

import { pathToFileURL } from "node:url";
import { existsSync } from "node:fs";
import path from "node:path";

const PORT = process.env.PORT || 8002;
// Pyodide 依赖所在目录，默认指向 D 盘专用目录
const NODE_MODULES_DIR = process.env.SANDBOX_NODE_MODULES || "D:/zhike-sandbox-deps/node_modules";
// 代码长度上限（与后端 SANDBOX_MAX_CODE_BYTES 对齐）
const MAX_CODE_BYTES = Number(process.env.MAX_CODE_BYTES || 65536);
// 执行超时（毫秒），略小于后端 SANDBOX_EXECUTION_TIMEOUT_SECONDS
const EXEC_TIMEOUT_MS = Number(process.env.EXEC_TIMEOUT_MS || 9000);

let pyodide = null;
let pyodideReady = false;

/**
 * 动态加载 D 盘依赖目录中的模块（ESM 无法用 NODE_PATH，改为绝对路径 import）。
 * 由于 pyodide/express 安装在 D 盘专用目录（不在本服务 node_modules 内），
 * 通过绝对路径动态 import 解析。
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
    const fs = await import("node:fs");
    const pkgJson = JSON.parse(fs.readFileSync(pkgJsonPath, "utf8"));
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
 * 动态加载 Pyodide 模块并返回 loadPyodide 函数。
 */
async function loadPyodideModule() {
  const mod = await loadModule("pyodide");
  return mod.loadPyodide;
}

/**
 * 加载 Pyodide 运行时（单例）。
 * 首次加载较慢（需加载 wasm 与标准库），后续复用。
 */
async function ensurePyodide() {
  if (pyodideReady) return pyodide;
  console.log("[sandbox] 正在加载 Pyodide 运行时...");
  const loadPyodide = await loadPyodideModule();
  pyodide = await loadPyodide({
    indexURL: path.join(NODE_MODULES_DIR, "pyodide") + "/",
  });
  pyodideReady = true;
  console.log("[sandbox] Pyodide 加载完成");
  return pyodide;
}

/**
 * 执行一段 Python 代码并捕获标准输出、标准错误与异常。
 *
 * @param {string} code - 待执行的 Python 源代码
 * @returns {Promise<{output: string, error: string, execution_time_ms: number}>}
 */
async function runPython(code) {
  const py = await ensurePyodide();

  let stdout = "";
  let stderr = "";

  py.setStdout({ batched: (chunk) => (stdout += chunk) });
  py.setStderr({ batched: (chunk) => (stderr += chunk) });

  const start = Date.now();
  let errorText = stderr;
  try {
    await Promise.race([
      py.runPythonAsync(code),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("__TIMEOUT__")), EXEC_TIMEOUT_MS)
      ),
    ]);
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    if (msg === "__TIMEOUT__") {
      errorText = (stderr ? stderr + "\n" : "") + `执行超时（${EXEC_TIMEOUT_MS / 1000} 秒）`;
    } else {
      errorText = (stderr ? stderr + "\n" : "") + msg;
    }
  } finally {
    py.setStdout({ batched: () => {} });
    py.setStderr({ batched: () => {} });
  }

  return { output: stdout, error: errorText, execution_time_ms: Date.now() - start };
}

const expressMod = await loadModule("express");
const express = expressMod.default;
const app = express();
app.use(express.json({ limit: "1mb" }));

// 健康检查端点，供后端探活
app.get("/health", (_req, res) => {
  res.json({ status: pyodideReady ? "ready" : "loading" });
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

// 启动前预加载 Pyodide，避免首个请求长时间等待
ensurePyodide()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`[sandbox] 代码沙箱微服务已启动，监听 http://127.0.0.1:${PORT}`);
    });
  })
  .catch((err) => {
    console.error("[sandbox] Pyodide 加载失败，服务退出:", err);
    process.exit(1);
  });
