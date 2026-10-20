/** @type {import('next').NextConfig} */
const nextConfig = {
  // The app has no next/image usage; turning the optimizer off removes the Image Optimizer DoS surface in Next 14.
  images: { unoptimized: true },
  experimental: {
    optimizePackageImports: ['lucide-react', 'recharts', 'motion', 'katex'],
  },
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
