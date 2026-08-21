# Frontend — React/Vite chat + agent trace viewer, built once and served as static files.
# Build from the frontend/ directory:
#   docker build -t mcp-frontend ./frontend
FROM node:20-alpine AS build

WORKDIR /app

# Reasoning: Copy manifests first so `npm ci` caches independently of source edits.
# npm ci (not npm install) installs exactly the lockfile, keeping image builds reproducible.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Reasoning: Vite inlines env vars at BUILD time, not run time — so the API URL has to be
# baked in here as a build arg rather than passed as a container env var, which would be
# silently ignored. The default is localhost:8000 because the browser making this call
# runs on the *host*, not inside the compose network, so Docker service names like
# "orchestrator" would not resolve for it.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Reasoning: Serve the built assets from nginx rather than shipping node and `vite preview`.
# The runtime image carries no toolchain, no node_modules, and no source.
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
