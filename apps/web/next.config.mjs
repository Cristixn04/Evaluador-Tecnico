/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@evaluador/contracts"],
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
