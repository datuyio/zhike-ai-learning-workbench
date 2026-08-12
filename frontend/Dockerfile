FROM node:22-alpine
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.25.0 --activate
COPY package.json pnpm-lock.yaml* .npmrc .pnpmrc ./
RUN pnpm config set registry https://registry.npmmirror.com \
    && pnpm install
COPY . .
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
