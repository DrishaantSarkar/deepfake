// Vercel Serverless Edge API Gateway for TRUSTLENS
// Routes /api/* to the dedicated TRUSTLENS backend service configured via TRUSTLENS_BACKEND_URL

export default async function handler(req, res) {
  const backendUrl = process.env.TRUSTLENS_BACKEND_URL || process.env.BACKEND_API_URL;
  const path = req.url || '';

  // Return live health status even if backend is pending configuration
  if (path.includes('/api/health') || path === '/health') {
    return res.status(200).json({
      status: "available",
      application: "trustlens-vercel-edge",
      backend_configured: Boolean(backendUrl),
      message: backendUrl
        ? "TRUSTLENS Vercel gateway active with upstream backend connected."
        : "TRUSTLENS Vercel frontend is live. Configure TRUSTLENS_BACKEND_URL in Vercel Environment Variables to route to your ML container."
    });
  }

  // Return capabilities fallback if backend is pending
  if (!backendUrl) {
    if (path.includes('/api/capabilities') || path === '/capabilities') {
      return res.status(200).json({
        supported_upload_extensions: [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".wav", ".mp3"],
        max_upload_bytes: 104857600,
        image: {
          ingestion: "available",
          frequency_descriptor: "available",
          trained_detector: "pending_backend_connection",
          model: { name: "resnet18-frame-baseline", status: "configured_in_backend_container" }
        },
        gateway: "vercel_edge",
        note: "Add TRUSTLENS_BACKEND_URL in Vercel Project Settings -> Environment Variables."
      });
    }

    if (path.includes('/api/stats') || path === '/stats') {
      return res.status(200).json({ total: 0, completed: 0, partial: 0, failed: 0, unavailable: 0, human_review: 0 });
    }

    return res.status(503).json({
      error: {
        code: "backend_unconfigured",
        message: "TRUSTLENS_BACKEND_URL is not configured in Vercel Project Settings. Please add your backend service URL."
      }
    });
  }

  // Transparently proxy request to dedicated backend container
  try {
    const cleanBase = backendUrl.replace(/\/$/, '');
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const targetUrl = `${cleanBase}${cleanPath}`;

    const headers = { ...req.headers };
    delete headers.host;
    delete headers.connection;

    const method = req.method ? req.method.toUpperCase() : 'GET';
    const fetchOptions = {
      method: method,
      headers: headers,
    };

    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && req.body) {
      if (typeof req.body === 'object' && !Buffer.isBuffer(req.body)) {
        fetchOptions.body = JSON.stringify(req.body);
        headers['content-type'] = 'application/json';
      } else {
        fetchOptions.body = req.body;
      }
    }

    const response = await fetch(targetUrl, fetchOptions);
    const contentType = response.headers.get('content-type') || 'application/json';
    
    res.status(response.status);
    res.setHeader('Content-Type', contentType);

    const disposition = response.headers.get('content-disposition');
    if (disposition) {
      res.setHeader('Content-Disposition', disposition);
    }

    const buffer = await response.arrayBuffer();
    return res.send(Buffer.from(buffer));
  } catch (err) {
    return res.status(502).json({
      error: {
        code: "bad_gateway",
        message: `Failed to connect to backend at ${backendUrl}: ${err.message}`
      }
    });
  }
}
