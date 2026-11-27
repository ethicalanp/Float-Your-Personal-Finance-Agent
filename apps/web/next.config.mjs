/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async redirects() {
    return [
      {
        source: "/settings",
        destination: "/profile/settings",
        permanent: true,
      },
      {
        source: "/assistant",
        destination: "/chat",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
