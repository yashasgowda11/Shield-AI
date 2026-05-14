import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Prevent Next.js from 308-redirecting URLs with trailing slashes before
  // the /api/backend/[...path] proxy handler can see them.
  // Without this, "/api/backend/contracts/" gets redirected to
  // "/api/backend/contracts" — stripping the slash FastAPI needs.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;