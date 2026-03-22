/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  async rewrites() {
    // NOTE: WebSocket (ws://) cannot be proxied via Next.js rewrites.
    // The frontend connects to the WS backend URL directly from the browser.
    // Only HTTP API routes are proxied here.
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
      {
        source: '/metrics/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/metrics/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
