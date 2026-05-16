import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function proxy(req: NextRequest, path: string[]) {
  const url = new URL(req.url);

  // FastAPI routes end with a trailing slash (e.g. GET /contracts/).
  // Next.js strips trailing slashes from [...path] segments, so we must
  // restore them — otherwise FastAPI returns a 307 redirect which
  // Next.js server-side fetch may not follow correctly in Cloud Run.
  const originalPathname = url.pathname; // e.g. "/api/backend/contracts/"
  const trailingSlash = originalPathname.endsWith("/") ? "/" : "";

  // Filter out any empty segments produced by the trailing slash before joining.
  const cleanPath = path.filter(Boolean).join("/");
  const target = `${BACKEND}/${cleanPath}${trailingSlash}${url.search}`;

  const res = await fetch(target, {
    method: req.method,
    redirect: "follow",   // explicit — avoids Cloud Run quirks with 307 redirects
    // Forward content-type from the original request when present
    headers: req.headers.get("Content-Type")
      ? { "Content-Type": req.headers.get("Content-Type")! }
      : {},
    body: req.method !== "GET" && req.method !== "DELETE" ? req.body : undefined,
    // @ts-ignore — required for streaming request bodies in Node.js
    duplex: "half",
  });

  // SSE streams must be piped directly — buffering with arrayBuffer() would
  // hold the entire stream in memory until the server closes it (which for a
  // pipeline that takes 60-120 s means the client sees nothing until it's over).
  const contentType = res.headers.get("Content-Type") ?? "";
  if (contentType.includes("text/event-stream")) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
      },
    });
  }

  const data = await res.arrayBuffer();
  return new Response(data, {
    status: res.status,
    headers: { "Content-Type": contentType || "application/json" },
  });
}

type Context = { params: Promise<Record<string, string | string[]>> };

export async function GET(req: NextRequest, ctx: Context) {
  const p = await ctx.params;
  return proxy(req, (p.path as string[]) ?? []);
}
export async function POST(req: NextRequest, ctx: Context) {
  const p = await ctx.params;
  return proxy(req, (p.path as string[]) ?? []);
}
export async function PUT(req: NextRequest, ctx: Context) {
  const p = await ctx.params;
  return proxy(req, (p.path as string[]) ?? []);
}
export async function DELETE(req: NextRequest, ctx: Context) {
  const p = await ctx.params;
  return proxy(req, (p.path as string[]) ?? []);
}