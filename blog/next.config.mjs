/** @type {import('next').NextConfig} */
const nextConfig = {
  // 静态导出，Cloudflare Pages 直接托管，无需 Node 运行时
  output: "export",
  // 图片来自 R2 CDN / 本地 public，关闭 Next 图片优化以兼容静态导出
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};

export default nextConfig;
