export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    // FastAPI 的错误体是 {"detail": "..."}，解开后再展示
    let msg = text || res.statusText
    try {
      const body = JSON.parse(text)
      if (typeof body?.detail === 'string') msg = body.detail
    } catch { /* 非 JSON 原文展示 */ }
    throw new Error(msg)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
