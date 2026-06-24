/**
 * Optional same-origin API proxy: /api/* -> BACKEND_URL/*
 * Set BACKEND_URL in Vercel project settings.
 *
 * For chat requests (can run several minutes), set VITE_API_URL to your
 * backend URL instead so the browser calls the backend directly.
 */
export default async function handler(req, res) {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    res.status(503).json({
      detail: 'BACKEND_URL is not configured. Set it in Vercel env vars, or set VITE_API_URL for direct backend calls.',
    });
    return;
  }

  const pathParam = req.query.path;
  const pathSegments = Array.isArray(pathParam) ? pathParam.join('/') : pathParam || '';
  const queryIndex = req.url?.indexOf('?') ?? -1;
  const query = queryIndex >= 0 ? req.url.slice(queryIndex) : '';
  const targetUrl = `${backendUrl.replace(/\/$/, '')}/${pathSegments}${query}`;

  const headers = { ...req.headers };
  delete headers.host;
  delete headers.connection;
  delete headers['content-length'];

  const init = {
    method: req.method,
    headers,
  };

  if (req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined) {
    init.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    if (!headers['content-type']) {
      headers['content-type'] = 'application/json';
    }
  }

  try {
    const response = await fetch(targetUrl, init);
    const body = await response.text();

    res.status(response.status);
    response.headers.forEach((value, key) => {
      if (!['transfer-encoding', 'connection', 'content-encoding'].includes(key.toLowerCase())) {
        res.setHeader(key, value);
      }
    });
    res.send(body);
  } catch (error) {
    res.status(502).json({
      detail: `Backend unreachable: ${error.message}`,
    });
  }
}

export const config = {
  api: {
    bodyParser: {
      sizeLimit: '4mb',
    },
  },
  maxDuration: 60,
};
