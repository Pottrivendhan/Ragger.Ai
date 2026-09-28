/**
 * Universal HTTP API Bridge for Browser Development Mode & Electron Production Package.
 * - In Development (Browser/Vite): Proxies through /api/dev/session and relative /api paths.
 * - In Production (Electron file://): Resolves dynamic loopback port and bearer token via IPC,
 *   connecting directly to http://127.0.0.1:<port> with 256-bit Bearer Authentication.
 */

let cachedToken: string | null = null;
let cachedBaseUrl: string | null = null;

export function isElectron(): boolean {
  return typeof window !== 'undefined' && Boolean((window as any).ragger);
}

export async function getApiConfig(forceRefresh = false): Promise<{ baseUrl: string; token: string | null }> {
  if (cachedBaseUrl && cachedToken && !forceRefresh) {
    return { baseUrl: cachedBaseUrl, token: cachedToken };
  }

  // 1. In Electron environment, query the supervisor via IPC
  if (isElectron() && window.ragger?.engine?.getApiConfig) {
    try {
      const res = await window.ragger.engine.getApiConfig();
      if (res?.success && res.data) {
        if (res.data.baseUrl) {
          cachedBaseUrl = res.data.baseUrl.replace(/\/+$/, '');
        }
        if (res.data.token) {
          cachedToken = res.data.token;
        }
        return { baseUrl: cachedBaseUrl || '', token: cachedToken };
      }
    } catch (ipcErr) {
      console.warn('[apiBridge] Error getting engine API config via IPC:', ipcErr);
    }
  }

  // 2. In Browser development mode, query Vite dev proxy /api/dev/session
  try {
    const res = await fetch('/api/dev/session');
    if (res.ok) {
      const data = await res.json();
      if (data.token) {
        cachedToken = data.token;
      }
      if (data.port) {
        // In dev server, relative URLs are proxied by Vite, so baseUrl remains empty string
        cachedBaseUrl = '';
      }
      return { baseUrl: cachedBaseUrl || '', token: cachedToken };
    }
  } catch {
    // Non-fatal, will be handled during authenticated request
  }

  return { baseUrl: cachedBaseUrl || '', token: cachedToken };
}

// Setup real-time invalidation when supervisor engine status changes in Electron
if (isElectron() && window.ragger?.engine?.onStatusChange) {
  try {
    window.ragger.engine.onStatusChange((status) => {
      if (status?.port) {
        const newBaseUrl = `http://127.0.0.1:${status.port}`;
        if (cachedBaseUrl !== newBaseUrl) {
          cachedBaseUrl = newBaseUrl;
          cachedToken = null; // Invalidate token to re-query with dynamic port
        }
      } else if (!status?.is_running) {
        cachedBaseUrl = null;
        cachedToken = null;
      }
    });
  } catch (err) {
    console.warn('[apiBridge] Failed to register onStatusChange listener:', err);
  }
}

export async function getAuthToken(forceRefresh = false): Promise<string | null> {
  const config = await getApiConfig(forceRefresh);
  return config.token;
}

import { localAuth } from './localAuth';

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const maxRetries = 2;
  let lastError: any = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const isRetry = attempt > 0;
    const config = await getApiConfig(isRetry);
    const token = config.token;
    const baseUrl = config.baseUrl;

    const headers = new Headers(options.headers || {});

    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    const session = localAuth.getSession();
    if (session?.accountId && !headers.has('X-Account-ID')) {
      headers.set('X-Account-ID', session.accountId);
    }

    // Construct absolute URL if baseUrl is available, or ensure leading slash
    const path = endpoint.startsWith('/') ? endpoint : `/api/v1/${endpoint}`;
    const fullUrl = baseUrl ? `${baseUrl}${path}` : path;

    let response: Response;
    try {
      response = await fetch(fullUrl, {
        ...options,
        headers,
      });
    } catch (netErr: any) {
      lastError = netErr;
      console.warn(`[Production API Network Attempt ${attempt + 1}/${maxRetries + 1}] Failed to connect to engine:`, {
        fullUrl,
        baseUrl,
        path,
        error: netErr?.message || netErr,
      });

      // Clear cache so next attempt refreshes the dynamic loopback port & token
      cachedBaseUrl = null;
      cachedToken = null;

      if (attempt < maxRetries) {
        // Short exponential backoff (400ms, 800ms) before retry
        await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
        continue;
      }

      console.error(`[Production API Network Error] All retries exhausted:`, {
        fullUrl,
        baseUrl,
        path,
        isElectron: isElectron(),
        error: netErr?.message || netErr,
      });

      throw new Error(
        netErr?.message === 'Failed to fetch'
          ? `Failed to fetch from backend engine (${fullUrl}). Engine may be initializing or unreachable.`
          : netErr?.message || 'Network error'
      );
    }

    // If 401 Unauthorized occurs, invalidate cached token and attempt next retry
    if (response.status === 401 && attempt < maxRetries) {
      cachedToken = null;
      cachedBaseUrl = null;
      await new Promise((resolve) => setTimeout(resolve, 300));
      continue;
    }

    if (!response.ok) {
      let errorDetail = `HTTP ${response.status} ${response.statusText}`;
      try {
        const errJson = await response.json();
        errorDetail =
          errJson.detail?.error?.message ||
          errJson.detail?.message ||
          errJson.detail ||
          errJson.message ||
          errorDetail;
        if (typeof errorDetail === 'object') {
          errorDetail = JSON.stringify(errorDetail);
        }
      } catch {
        // Use fallback error text
      }
      console.error(`[Production API Error Response]`, {
        url: fullUrl,
        status: response.status,
        errorDetail,
      });
      throw new Error(errorDetail);
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return (await response.json()) as T;
    }
    return (await response.text()) as unknown as T;
  }

  throw lastError || new Error('Network request failed');
}

/**
 * Resolves an authoritative absolute URL and default headers for streaming/SSE requests.
 */
export async function resolveApiUrl(endpoint: string): Promise<{ url: string; headers: Record<string, string> }> {
  const config = await getApiConfig();
  const token = config.token;
  const baseUrl = config.baseUrl;

  const headers: Record<string, string> = {
    'Accept': 'text/event-stream',
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const session = localAuth.getSession();
  if (session?.accountId) {
    headers['X-Account-ID'] = session.accountId;
  }

  const path = endpoint.startsWith('/') ? endpoint : `/api/v1/${endpoint}`;
  const url = baseUrl ? `${baseUrl}${path}` : path;
  return { url, headers };
}

/**
 * Executes a streaming fetch request to the authoritative engine endpoint with auto-retry and cache invalidation.
 */
export async function apiStream(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const maxRetries = 1;
  let lastError: any = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const isRetry = attempt > 0;
    const config = await getApiConfig(isRetry);
    const token = config.token;
    const baseUrl = config.baseUrl;

    const headers = new Headers(options.headers || {});
    if (!headers.has('Accept')) {
      headers.set('Accept', 'text/event-stream');
    }
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    const session = localAuth.getSession();
    if (session?.accountId && !headers.has('X-Account-ID')) {
      headers.set('X-Account-ID', session.accountId);
    }

    const path = endpoint.startsWith('/') ? endpoint : `/api/v1/${endpoint}`;
    const fullUrl = baseUrl ? `${baseUrl}${path}` : path;

    try {
      const response = await fetch(fullUrl, {
        ...options,
        headers,
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errJson = await response.json();
          errorDetail =
            errJson.detail?.error?.message ||
            errJson.detail?.message ||
            errJson.detail ||
            errJson.message ||
            errorDetail;
          if (typeof errorDetail === 'object') {
            errorDetail = JSON.stringify(errorDetail);
          }
        } catch {
          // fallback
        }
        throw new Error(errorDetail);
      }

      return response;
    } catch (netErr: any) {
      lastError = netErr;
      cachedBaseUrl = null;
      cachedToken = null;
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 400));
        continue;
      }
      console.error(`[apiStream] Streaming connection failed:`, {
        fullUrl,
        error: netErr?.message || netErr,
      });
      throw new Error(
        netErr?.message === 'Failed to fetch'
          ? `Failed to fetch from backend engine (${fullUrl}). Engine may be initializing or unreachable.`
          : netErr?.message || 'Network streaming error'
      );
    }
  }

  throw lastError || new Error('Stream request failed');
}
