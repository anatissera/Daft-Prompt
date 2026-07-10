FROM node:22-bookworm-slim

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./

RUN npm ci

COPY apps/web .
COPY .git/HEAD /tmp/llminem-git/HEAD
COPY .git/refs /tmp/llminem-git/refs
RUN head_ref="$(cat /tmp/llminem-git/HEAD)"; \
    if printf '%s' "$head_ref" | grep -q '^ref: '; then \
      revision="$(cat "/tmp/llminem-git/${head_ref#ref: }")"; \
    else revision="$head_ref"; fi; \
    printf '{"commit":"%s","service":"web"}\n' "$revision" > /app/build-info.json; \
    rm -rf /tmp/llminem-git

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
