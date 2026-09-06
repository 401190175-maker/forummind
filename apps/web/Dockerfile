# syntax=docker/dockerfile:1

# ForumMind Web — Next.js 前端镜像。
#
# 构建上下文为 apps/web（Task 13 的 docker-compose 也从同一上下文构建）：
#   docker build -t forummind-web ./apps/web
# 运行：
#   docker run --rm -p 3000:3000 forummind-web
#
# 设计约束（changes/design.md §8.4）：基础镜像固定版本、不复制 .env/缓存/日志。
# 非 standalone 模式：构建阶段产出 .next，运行阶段安装生产依赖并以 `next start` 启动。
# （standalone 输出会让 Windows 主机上的本地 next build 在追踪符号链接阶段 EPERM 失败，
#   为保持「本地 next build 可用」的既有兼容性，故不使用 standalone 模式。）

# ---- 构建阶段 ----
# 固定稳定 LTS 基础镜像，禁止 latest。用 node:22 而非 node:20：
# 仓库固定的 pnpm@11.7.0 要求 Node >=22.13（依赖 node:sqlite），node:20 无法运行它。
FROM node:22-alpine AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# pnpm 版本与仓库根 package.json 的 packageManager 字段一致（pnpm@11.7.0）。
# 注意：构建上下文是 apps/web，仓库根的 pnpm-lock.yaml / pnpm-workspace.yaml 不在上下文内，
# 因此这里做全新安装、不传 --frozen-lockfile（权衡说明见 task-12-report.md）。
RUN npm install -g pnpm@11.7.0

# pnpm 11 不再读取 package.json 中的 pnpm 字段，构建脚本白名单必须声明在 pnpm-workspace.yaml。
# 上下文里没有工作区文件，故在镜像内生成单项目工作区声明，放行 Next.js 可选依赖 sharp
# 的构建脚本（否则 pnpm 11 直接以 ERR_PNPM_IGNORED_BUILDS 失败退出）。
RUN cat > pnpm-workspace.yaml <<'EOF'
allowBuilds:
  sharp: true
EOF

# 先复制 package.json 并安装依赖，利用 Docker 层缓存（package.json 不变则不重装）。
COPY package.json ./
RUN pnpm install

# NEXT_PUBLIC_* 变量在构建期注入客户端 bundle（page.tsx 是 "use client"），
# 必须在 next build 之前以 ENV 形式存在。默认 http://localhost:8000（浏览器可访问地址）。
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

# 复制构建所需源码（本应用没有 public/ 目录，无静态资源可复制）。
COPY next.config.ts tsconfig.json next-env.d.ts ./
COPY app ./app

# 构建生产产物（.next/）。
RUN pnpm build

# ---- 运行阶段 ----
FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# 与构建阶段相同的 pnpm 安装与 sharp 构建脚本白名单。
RUN npm install -g pnpm@11.7.0
RUN cat > pnpm-workspace.yaml <<'EOF'
allowBuilds:
  sharp: true
EOF

# 只安装生产依赖（不含 typescript/@types 等 devDependencies）。
COPY package.json ./
RUN pnpm install --prod

# 复制构建产物（.next/ 含页面、静态资源与 server 代码）。不复制宿主 node_modules/.next。
COPY --from=builder /app/.next ./.next

# 前端服务端口。
EXPOSE 3000

# 启动 Next.js 服务，绑定 0.0.0.0:3000（直接以 node 执行，避免 shell 包装）。
CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
