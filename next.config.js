/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config, { dev }) => {
    if (dev) {
      config.output.chunkLoadTimeout = 300000;
    }
    return config;
  },
  async redirects() {
    return [
      {
        source: '/approvals',
        destination: '/assistant',
        permanent: false,
      },
    ];
  },
};

module.exports = nextConfig;
