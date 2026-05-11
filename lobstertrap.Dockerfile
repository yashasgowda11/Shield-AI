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

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -q --spider http://localhost:8080/_lobstertrap/ || exit 1

# `serve` defaults to --listen :8080 (binds 0.0.0.0:8080 — all interfaces).
# Backend hop to Ollama at 11434 will fail (no Ollama in this image) but DPI
# inspection runs first, which is all we need.
ENTRYPOINT ["lobstertrap"]
CMD ["serve"]
