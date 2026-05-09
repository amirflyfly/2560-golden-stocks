export async function csrfToken(page) {
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === 'promo_panel_csrf')?.value || '';
}

export async function apiRequest(page, path, options = {}) {
  const method = options.method || 'GET';
  const headers = {
    Accept: 'application/json',
    'X-Tenant-ID': String(options.tenantId || 1),
    ...(options.headers || {}),
  };
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    headers['X-CSRF-Token'] = await csrfToken(page);
  }
  return page.request.fetch(path, {
    method,
    headers,
    data: options.body,
  });
}

export async function jsonData(response) {
  const payload = await response.json();
  return payload.data;
}
