/** @type {import('next').NextConfig} */
const standalone = process.env.NEXT_OUTPUT === "standalone";
const staticExport = process.env.NEXT_OUTPUT === "static";

const nextConfig = {
  reactStrictMode: true,
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
