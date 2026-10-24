const FEEDBACK_ROUTE = '^/api/feedback(?:\\?.*)?$'

// These settings run in Vite's server, never in the browser bundle.
export function createApiProxy(env = {}) {
  const localApi = {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
    // WhisperX and the downstream models may take several minutes on CPU.
    timeout: 0,
    proxyTimeout: 0,
  }
  const feedbackUrl = env.FEEDBACK_API_URL?.trim()
  if (!feedbackUrl) return { '/api': localApi }

  let target
  try {
    target = new URL(feedbackUrl)
  } catch {
    throw new Error('FEEDBACK_API_URL must be an HTTP or HTTPS server origin.')
  }
  if (!['http:', 'https:'].includes(target.protocol)
      || target.username || target.password || target.pathname !== '/'
      || target.search || target.hash) {
    throw new Error('FEEDBACK_API_URL must be an HTTP or HTTPS server origin without a path, credentials, query, or fragment.')
  }
  const token = env.FEEDBACK_API_TOKEN?.trim()
  if (!token || /\s/.test(token)) {
    throw new Error('FEEDBACK_API_TOKEN is required when FEEDBACK_API_URL is set and must not contain whitespace.')
  }

  // Exact feedback requests go to the shared receiver. Other API calls remain
  // local. Proxy failures return an error; they never retry the local endpoint.
  return {
    [FEEDBACK_ROUTE]: {
      target: target.origin,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
      headers: { Authorization: `Bearer ${token}` },
      timeout: 15000,
      proxyTimeout: 15000,
    },
    '/api': localApi,
  }
}
