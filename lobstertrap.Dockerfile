# Veea Lobster Trap — multi-stage build from source.
# Result: small Alpine image, non-root, no Go toolchain in the final layer.
# Repo: https://github.com/veeainc/lobstertrap

# ---- Build stage ----
FROM golang:1.22-alpine AS build

RUN apk add --no-cache git make

WORKDIR /src
ARG LOBSTERTRAP_REF=main
RUN git clone --depth 1 --branch ${LOBSTERTRAP_REF} \
    https://github.com/veeainc/lobstertrap.git .
RUN make build

# ---- Runtime stage ----
FROM alpine:3.20

RUN apk add --no-cache ca-certificates wget && \
    addgroup -S lobster && adduser -S -G lobster lobster

# Binary + the configs/ directory it looks up relative to its CWD.
# WORKDIR /app makes `configs/default_policy.yaml` resolve correctly.
COPY --from=build /src/lobstertrap /usr/local/bin/lobstertrap
COPY --from=build /src/configs /app/configs

WORKDIR /app
USER lobster

# Cloud Run injects PORT at runtime (default 8080 for local dev).
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q --spider http://localhost:${PORT}/_lobstertrap/ || exit 1

# Use shell form so ${PORT} is expanded at runtime.
# Backend hop to Ollama at 11434 will fail (no Ollama) but DPI inspection
# runs first — which is all Shield AI needs.
CMD ["sh", "-c", "lobstertrap serve --listen :${PORT}"]
