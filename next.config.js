/** @type {import('next').NextConfig} */
const nextConfig = {
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
