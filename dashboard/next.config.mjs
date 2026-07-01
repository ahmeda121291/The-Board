/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // /docs reads the synced markdown (content/) at request time — make sure the
  // files ship inside the serverless bundle on Vercel. (Next 14: experimental.)
  experimental: {
    outputFileTracingIncludes: {
      "/docs": ["./content/**"],
    },
  },
};
export default nextConfig;
