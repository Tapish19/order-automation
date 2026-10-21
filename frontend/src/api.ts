export async function api<T>(path: string, options?: RequestInit, actor = 'Interview Manager'): Promise<T> {
  const response = await fetch('/api' + path, { ...options, headers: { 'X-User': actor, ...(!(options?.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options?.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail) } catch { /* use HTTP status */ }
    throw new Error(message)
  }
  return response.json()
}
export function query(values: object) {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key,value]) => { if (value !== '' && value !== undefined && value !== null) params.set(key, String(value)) })
  return params.size ? '?' + params.toString() : ''
}
export function localToday() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit' }).format(new Date()) }
export function when(value: string | null) {
  if (!value) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value + ' (date only)'
  return new Intl.DateTimeFormat('en-IN', { timeZone:'Asia/Kolkata', day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false }).format(new Date(value)) + ' IST'
}
export const money = (value: number) => new Intl.NumberFormat('en-IN', {style:'currency',currency:'INR',maximumFractionDigits:2}).format(value)
