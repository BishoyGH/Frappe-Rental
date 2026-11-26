const STATUS_THEME = {
  Draft: 'gray',
  Hold: 'orange',
  Confirmed: 'blue',
  'Checked Out': 'violet',
  Returned: 'green',
  Closed: 'green',
  Cancelled: 'red',
  'No Show': 'red',
}
export const statusTheme = (s) => STATUS_THEME[s] || 'gray'

export function fmtDate(value, withTime = false) {
  if (!value) return ''
  const d = new Date(String(value).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return value
  const opts = { day: 'numeric', month: 'short' }
  if (withTime) Object.assign(opts, { year: 'numeric', hour: '2-digit', minute: '2-digit' })
  return d.toLocaleString(undefined, opts)
}

export function fmtMoney(value) {
  const n = Number(value || 0)
  return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

export function fromNow(value, now) {
  if (!value) return ''
  const parse = (v) => new Date(String(v).replace(' ', 'T')).getTime()
  const sec = ((now ? parse(now) : Date.now()) - parse(value)) / 1000
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, s] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(sec) >= s) return rtf.format(-Math.round(sec / s), unit)
  }
  return rtf.format(0, 'minute')
}

// Per-viewer convenience only (columns picked); never required state.
export function stored(key, fallback) {
  try {
    const v = localStorage.getItem(key)
    return v ? JSON.parse(v) : fallback
  } catch {
    return fallback
  }
}
export function store(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable */
  }
}
