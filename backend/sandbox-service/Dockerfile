FROM node:20-alpine

WORKDIR /app

# 先拷贝依赖清单以利用 Docker 构建缓存，国内 npm 镜像安装 Pyodide 与 Express
COPY package.json package-lock.json ./
RUN npm install --no-audit --no-fund --registry=https://registry.npmmirror.com

# 拷贝服务源码；node_modules 已由上一阶段生成，避免重复安装
COPY server.js sandbox-worker.js ./

# 容器内需要监听所有网卡，供同网络中的 FastAPI 后端转发调用
ENV SANDBOX_HOST=0.0.0.0
EXPOSE 8003

CMD ["node", "server.js"]
