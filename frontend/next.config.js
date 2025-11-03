/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
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
  output: "standalone",
  experimental: {
    ppr: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
};

module.exports = nextConfig;
