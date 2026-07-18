/** @type {import('next').NextConfig} */
const standalone = process.env.NEXT_OUTPUT === "standalone";
const staticExport = process.env.NEXT_OUTPUT === "static";

// Security headers applied to every response served by the Next.js server.
// Note: a static export (NEXT_OUTPUT=static) is served by an external web
// server, so these must be reproduced in that server's config too.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
  {
    // Conservative CSP. 'unsafe-inline'/'unsafe-eval' are required by the
    // Next.js runtime; tighten with nonces if the app moves off them.
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "img-src 'self' data: blob: https: http:",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "connect-src 'self' https: http:",
      "font-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig = {
  reactStrictMode: true,
  // headers() is not honored under `output: export` (files are served by an
  // external web server), so only attach it for the server-backed builds.
  ...(staticExport
    ? {}
    : {
        async headers() {
          return [{ source: "/:path*", headers: securityHeaders }];
        },
      }),
  images: {
    // Static export cannot run the Next.js image optimisation server,
    // so we fall back to unoptimised <img> tags and let the browser
    // fetch images directly from MinIO.
    unoptimized: staticExport,
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "9000",
        pathname: "/images/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "3000",
      },
    ],
  },
  experimental: {
    ppr: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  ...(standalone ? { output: "standalone" } : {}),
  ...(staticExport ? { output: "export", trailingSlash: true } : {}),
};

module.exports = nextConfig;
