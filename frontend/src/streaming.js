export function tryParseJson(text) {
  const s = typeof text === 'string' ? text : ''
  const start = s.indexOf('{')
  if (start === -1) return null
  let depth = 0, inStr = false, esc = false
  for (let i = start; i < s.length; i++) {
    const c = s[i]
    if (inStr) {
      if (esc) esc = false
      else if (c === '\\') esc = true
      else if (c === '"') inStr = false
      continue
    }
    if (c === '"') inStr = true
    else if (c === '{') depth++
    else if (c === '}') {
      depth--
      if (depth === 0) {
        try { return JSON.parse(s.slice(start, i + 1)) } catch { return null }
      }
    }
  }
  return null
}

export function extractLiveSlides(text) {
  const s = typeof text === 'string' ? text : ''
  const result = { title: null, slides: [] }
  const titleMatch = s.match(/"deck_title"\s*:\s*"((?:\\.|[^"\\])*)"/) || s.match(/"title"\s*:\s*"((?:\\.|[^"\\])*)"/)
  if (titleMatch) result.title = titleMatch[1]
  const arrIdx = s.indexOf('"slides"')
  if (arrIdx === -1) return result
  const bracket = s.indexOf('[', arrIdx)
  if (bracket === -1) return result
  let i = bracket + 1, depth = 0, inStr = false, esc = false, objStart = -1
  for (; i < s.length; i++) {
    const c = s[i]
    if (inStr) {
      if (esc) esc = false
      else if (c === '\\') esc = true
      else if (c === '"') inStr = false
      continue
    }
    if (c === '"') { inStr = true; continue }
    if (c === '{') { if (depth === 0) objStart = i; depth++ }
    else if (c === '}') {
      depth--
      if (depth === 0 && objStart !== -1) {
        try {
          const raw = JSON.parse(s.slice(objStart, i + 1))
          result.slides.push({
            title: raw.title || raw.slide_title || `Slide ${result.slides.length + 1}`,
            subtitle: raw.subtitle || '',
            bullets: raw.bullets || [],
            note: raw.note || raw.speaker_notes || '',
            image: raw.image || '',
          })
        } catch {}
        objStart = -1
      }
    }
    if (c === ']' && depth === 0) break
  }
  return result
}

export function extractLiveArray(text, key) {
  const s = typeof text === 'string' ? text : ''
  const keyIdx = s.indexOf(`"${key}"`)
  if (keyIdx === -1) return []
  const bracket = s.indexOf('[', keyIdx)
  if (bracket === -1) return []
  const out = []
  let i = bracket + 1, depth = 0, inStr = false, esc = false
  let objStart = -1, strStart = -1
  for (; i < s.length; i++) {
    const c = s[i]
    if (inStr) {
      if (esc) esc = false
      else if (c === '\\') esc = true
      else if (c === '"') {
        inStr = false
        if (depth === 0 && strStart !== -1) {
          try { out.push(JSON.parse(s.slice(strStart, i + 1))) } catch {}
          strStart = -1
        }
      }
      continue
    }
    if (c === '"') {
      inStr = true
      if (depth === 0 && strStart === -1) strStart = i
      continue
    }
    if (c === '{') {
      if (depth === 0 && objStart === -1) objStart = i
      depth++
    } else if (c === '}') {
      depth--
      if (depth === 0 && objStart !== -1) {
        try { out.push(JSON.parse(s.slice(objStart, i + 1))) } catch {}
        objStart = -1
      }
    }
    if (c === ']' && depth === 0) break
  }
  return out
}

export function extractPartialString(text, key) {
  const s = typeof text === 'string' ? text : ''
  const re = new RegExp(`"${key}"\\s*:\\s*"`)
  const m = s.match(re)
  if (!m) return null
  const start = m.index + m[0].length
  let out = ''
  let esc = false
  for (let i = start; i < s.length; i++) {
    const c = s[i]
    if (esc) { out += c; esc = false; continue }
    if (c === '\\') { esc = true; continue }
    if (c === '"') break
    out += c
  }
  return out || null
}

export function normalizeSlides(data) {
  return {
    title: data?.deck_title || data?.title || 'Slides',
    slides: (data?.slides || []).map((s, i) => ({
      title: s.title || s.slide_title || `Slide ${i + 1}`,
      subtitle: s.subtitle || '',
      bullets: s.bullets || [],
      note: s.note || s.speaker_notes || '',
      image: s.image || '',
    })),
  }
}