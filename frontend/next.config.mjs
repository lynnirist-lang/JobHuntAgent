/** @type {import('next').NextConfig} */
const nextConfig = {
  // 将 /api 请求代理到 FastAPI 后端，前端代码中可直接调用 /api/...
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://localhost:${process.env.BACKEND_PORT || 8000}/:path*`,
      },
    ];
  },
};

export default nextConfig;
