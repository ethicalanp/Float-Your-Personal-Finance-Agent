/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async redirects() {
    return [
      {
        source: "/assistant",
        destination: "/chat",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
