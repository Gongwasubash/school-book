import React, { useEffect, useState } from 'react'
import {
  Bell, BookOpen, Brain, ChevronDown, ChevronLeft, ChevronRight,
  Cog, ExternalLink, FileText, Flame, GraduationCap,
  ListChecks, Menu, Presentation, Send, Settings, Sparkles, Target, Wrench, X, LogOut,
} from 'lucide-react'
import MCQViewer from './MCQViewer'
import Login from './Login'
import { tryParseJson, extractLiveSlides, extractLiveArray, extractPartialString, normalizeSlides } from './streaming'

const API = import.meta.env.VITE_API_URL || ''

const TEACHER_RESOURCES = [
  'Lesson Plan', 'Teaching Notes', 'Classroom Activity', 'Assignment',
  'Quiz', 'Discussion Questions', 'Assessment Rubric',
]

const STUDENT_TOOLS = [
  'Summary', 'Key Points', 'Key Terms', 'Vocabulary', 'Flashcards', 'MCQ',
  'Questions', 'Real-Life Examples', 'Fun Facts', 'Group Activity',
  'Project Work', 'Mind Map', 'Slides', 'Points to Remember', 'Videos',
]

const TOOL_LABELS = {
  'Summary': 'Summary',
  'Key Points': 'Points',
  'Key Terms': 'Terms',
  'Vocabulary': 'Vocab',
  'Flashcards': 'Cards',
  'MCQ': 'MCQ',
  'Questions': 'Q&A',
  'Real-Life Examples': 'Examples',
  'Fun Facts': 'Facts',
  'Group Activity': 'Activity',
  'Project Work': 'Projects',
  'Mind Map': 'Mindmap',
  'Slides': 'Slides',
  'Points to Remember': 'Remember',
  'Videos': 'Videos',
}

const DIFFICULTY_LEVELS = ['Easy', 'Medium', 'Hard']

const RESOURCE_ICONS = {
  'Lesson Plan': FileText, 'Teaching Notes': FileText, 'Classroom Activity': Sparkles,
  Assignment: ListChecks, Quiz: Target, 'Discussion Questions': ListChecks,
  'Assessment Rubric': Target, Progress: Flame,
  Summary: FileText, 'Key Points': ListChecks, 'Key Terms': BookOpen,
  Vocabulary: BookOpen, Flashcards: FileText, MCQ: Target, Questions: ListChecks,
  'Real-Life Examples': Sparkles, 'Fun Facts': Sparkles, 'Group Activity': Sparkles,
  'Project Work': Target, 'Mind Map': Brain, Slides: FileText,
  'Points to Remember': ListChecks, Videos: Sparkles,
}

const NAV_LINKS = []

const safeStr = (v) => {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number') return String(v)
  if (Array.isArray(v)) return v.map(safeStr).join(', ')
  if (typeof v === 'object') return Object.values(v).map(safeStr).join(', ')
  return String(v)
}

const isMathQuestion = (text) => {
  if (!text) return false
  const s = String(text).toLowerCase()
  const mathWords = /\b(solve|calculate|evaluate|compute|simplify|factor|differentiate|integrate|find the value|solve for|sum of|difference of|product of|ratio|percentage|perimeter|area of|volume of|probability|mean|average|fraction|decimal|algebra|equation|trigonometr|quadratic|linear equation|derivative|integral|what is [a-z]+\s*[=+\-]|find x|find the value of x|simplify the)\b/
  const hasDigits = /\d/
  const hasMathOps = /[+\-*/^=√×÷]|\b(square root|cube|power)\b/
  return (
    (mathWords.test(s) && (hasDigits.test(s) || /[=+\-*/^]/.test(s))) ||
    /[0-9]\s*[+\-*/^]\s*[0-9]/.test(s) ||
    /^[a-z]\s*=\s*-?\d/.test(s.trim())
  )
}

const L = {
  en: {
    badge: 'Nepal Curriculum • Grade 1–10',
    raiseTicket: 'Raise Ticket',
    dashboard: 'Dashboard', aiBooks: 'AI Books', attendance: 'Attendance',
    assessments: 'Assessments', liveCode: 'Live Code Studio', games: 'Games',
    curriculum: 'Curriculum', chapters: 'Chapters', all: 'All',
    buildKb: 'Build Knowledge Base', notAvailable: 'Not available',
    tabTopic: 'Topic Content', tabTeacher: 'Teacher Resources',
    tabObjectives: 'Learning Objectives', tabGrid: 'Grid Image',
    studyTools: 'Study Tools', generate: 'Generate',
    kbReady: 'Knowledge base ready — {chunks} chunks · {label}',
    kbHint: 'Select chapters and build a knowledge base to start',
    buildFirst: 'Build a knowledge base first (select chapters and press Build).',
    teacherReady: 'Teacher-ready resources generated from the current knowledge base.',
    objectivesHint: 'Per-unit learning objectives will appear here once a knowledge base is built.',
    gridHint: 'Grid image preview will appear here once a knowledge base is built.',
    contents: 'Contents & Interactive Tools',
    progress: 'Progress', ask: 'Ask', thinking: 'thinking…',
    askHint: 'Ask anything about the selected chapters.', loading: 'Loading…',
    language: 'Language', of: 'of',
  },
  ne: {
    badge: 'नेपाल पाठ्यक्रम • कक्षा १–१०',
    raiseTicket: 'टिकट पेश गर्नुहोस्',
    dashboard: 'ड्यासबोर्ड', aiBooks: 'AI पुस्तकहरू', attendance: 'उपस्थिति',
    assessments: 'मूल्याङ्कन', liveCode: 'लाइभ कोड स्टुडियो', games: 'खेलहरू',
    curriculum: 'पाठ्यक्रम', chapters: 'अध्यायहरू', all: 'सबै',
    buildKb: 'ज्ञान भण्डार बनाउनुहोस्', notAvailable: 'उपलब्ध छैन',
    tabTopic: 'विषय सामग्री', tabTeacher: 'शिक्षक स्रोतहरू',
    tabObjectives: 'सिकाइ उद्देश्यहरू', tabGrid: 'ग्रिड छवि',
    studyTools: 'अध्ययन उपकरणहरू', generate: 'उत्पन्न गर्नुहोस्',
    kbReady: 'ज्ञान भण्डार तयार छ — {chunks} खण्डहरू · {label}',
    kbHint: 'अध्यायहरू छानेर ज्ञान भण्डार बनाउनुहोस्',
    buildFirst: 'पहिले ज्ञान भण्डार बनाउनुहोस् (अध्याय छानेर Build थिच्नुहोस्)।',
    teacherReady: 'हालको ज्ञान भण्डारबाट शिक्षकका लागि तयार स्रोतहरू।',
    objectivesHint: 'ज्ञान भण्डार बनेपछि एकाइका सिकाइ उद्देश्यहरू यहाँ देखिनेछन्।',
    gridHint: 'ज्ञान भण्डार बनेपछि ग्रिड छवि यहाँ देखिनेछ।',
    contents: 'सामग्री र अन्तरक्रियात्मक उपकरणहरू',
    progress: 'प्रगति', ask: 'सोध्नुहोस्', thinking: 'सोच्दै…',
    askHint: 'चुनिएका अध्यायहरूबारे केही पनि सोध्नुहोस्।', loading: 'लोड हुँदै…',
    language: 'भाषा', of: 'मध्ये',
  },
  hi: {
    badge: 'नेपाल पाठ्यक्रम • कक्षा १–१०',
    raiseTicket: 'टिकट भेजें',
    dashboard: 'डैशबोर्ड', aiBooks: 'AI पुस्तकें', attendance: 'उपस्थिति',
    assessments: 'मूल्यांकन', liveCode: 'लाइव कोड स्टूडियो', games: 'खेल',
    curriculum: 'पाठ्यक्रम', chapters: 'अध्याय', all: 'सभी',
    buildKb: 'ज्ञान भंडार बनाएं', notAvailable: 'उपलब्ध नहीं',
    tabTopic: 'विषय सामग्री', tabTeacher: 'शिक्षक संसाधन',
    tabObjectives: 'सीखने के उद्देश्य', tabGrid: 'ग्रिड छवि',
    studyTools: 'अध्ययन उपकरण', generate: 'उत्पन्न करें',
    kbReady: 'ज्ञान भंडार तैयार — {chunks} खंड · {label}',
    kbHint: 'अध्याय चुनकर ज्ञान भंडार बनाएं',
    buildFirst: 'पहले ज्ञान भंडार बनाएं (अध्याय चुनकर Build दबाएं)।',
    teacherReady: 'वर्तमान ज्ञान भंडार से शिक्षक संसाधन।',
    objectivesHint: 'ज्ञान भंडार बनने पर इकाई उद्देश्य यहां दिखेंगे।',
    gridHint: 'ज्ञान भंडार बनने पर ग्रिड छवि यहां दिखेगी।',
    contents: 'सामग्री और इंटरैक्टिव उपकरण',
    progress: 'प्रगति', ask: 'पूछें', thinking: 'सोच रहे हैं…',
    askHint: 'चुने गए अध्यायों के बारे में कुछ भी पूछें।', loading: 'लोड हो रहा…',
    language: 'भाषा', of: 'में से',
  },
}

const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'ne', label: 'नेपाली' },
  { code: 'hi', label: 'हिंदी' },
]

function t(lang, key, vars) {
  let s = (L[lang] && L[lang][key]) || (L.en[key] ?? key)
  if (vars) Object.entries(vars).forEach(([k, v]) => { s = s.replace(`{${k}}`, v) })
  return s
}

async function post(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

async function postStream(path, body, { onDelta, onDone, onError } = {}) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop()
    for (const evt of events) {
      for (const line of evt.split('\n')) {
        if (!line.startsWith('data: ')) continue
        let data
        try { data = JSON.parse(line.slice(6)) } catch { continue }
        if (data.error) { onError?.(data.error); return }
        if (data.delta) onDelta?.(data.delta)
        if (data.step) onDelta?.(data)
        if (data.complete || data.done) { onDone?.(data.text || data); return }
        if (data.sources) onDone?.({ sources: data.sources })
      }
    }
  }
  if (buffer.trim()) {
    for (const line of buffer.trim().split('\n')) {
      if (!line.startsWith('data: ')) continue
      let data
      try { data = JSON.parse(line.slice(6)) } catch { continue }
      if (data.error) { onError?.(data.error); return }
      if (data.delta) onDelta?.(data.delta)
      if (data.step) onDelta?.(data)
      if (data.complete || data.done) { onDone?.(data.text || data); return }
      if (data.sources) onDone?.({ sources: data.sources })
    }
    onError?.('Stream ended before completion.')
  } else {
    onError?.('Connection closed before the stream finished.')
  }
}

async function get(path) {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json()
}

export default function App() {
  const [lang, setLang] = useState('en')
  const [groups, setGroups] = useState([])
  const [openGroup, setOpenGroup] = useState(null)
  const [books, setBooks] = useState(null)
  const [chapters, setChapters] = useState([])
  const [kb, setKb] = useState({ built: false, label: null, chunks: 0 })
  const [auth, setAuth] = useState(null)
  const [notebook, setNotebook] = useState(null)
  const [notebookBusy, setNotebookBusy] = useState(false)
  const [notebookStream, setNotebookStream] = useState('')
  const [kbProgress, setKbProgress] = useState([])
  const [phase, setPhase] = useState(null)
  const [tab, setTab] = useState('Topic Content')
  const [provider, setProvider] = useState('')
  const [providers, setProviders] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(null)
  const [chat, setChat] = useState([])
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)
  const [streamText, setStreamText] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [modalType, setModalType] = useState('MCQ')
  const [quantity, setQuantity] = useState(5)
  const [difficulty, setDifficulty] = useState('Medium')
  const [currentBook, setCurrentBook] = useState(null)
  const [exercise, setExercise] = useState(null)
  const [exerciseBusy, setExerciseBusy] = useState(false)
  const [exerciseStream, setExerciseStream] = useState('')
  const [selectedChapter, setSelectedChapter] = useState(null)
  const [loadingChapters, setLoadingChapters] = useState(false)
  const [isChatOpen, setIsChatOpen] = useState(false)

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [fileMode, setFileMode] = useState('md')
  const [user, setUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('aibooks_user')
    if (saved) {
      try { setUser(JSON.parse(saved)) } catch {}
    }
    setAuthLoading(false)
  }, [])

  useEffect(() => {
    get('/api/books')
      .then((d) => { setGroups(d.groups || []); setKb({ built: false, label: null, chunks: 0 }) })
      .catch((e) => setError(e.message))
    get('/api/kb/status')
      .then(setKb)
      .catch(() => {})
    get('/api/providers')
      .then((d) => { setProviders(d.providers || []); setProvider(d.providers?.[0] || '') })
      .catch(() => {})
    get('/api/progress').then(setProgress).catch(() => {})
    get('/api/google/auth').then(setAuth).catch(() => {})
  }, [])

  const toggleGroup = async (g) => {
    if (openGroup === g.id) { setOpenGroup(null); return }
    setOpenGroup(g.id)
    try {
      const group = await get(`/api/books/${g.id}/subjects`)
      setBooks(group.subjects || group.books || [])
    } catch (e) { setError(e.message) }
  }

  const loadChapters = async (book) => {
    setCurrentBook(book)
    setNotebook(null)
    setSelectedChapter(null)
    setExercise(null)
    setKb({ built: false, label: null, chunks: 0 })
    setChapters([])
    setLoadingChapters(true)
    try {
      const d = await get(`/api/chapters?class_num=${book.class}&file=${encodeURIComponent(book.file)}`)
      const list = (d.chapters || []).map((c, i) => ({ ...c, id: i }))
      setChapters(list)
    } catch (e) { setError(e.message) }
    finally {
      setLoadingChapters(false)
    }
  }

  const connectGoogle = () => {
    if (!auth?.auth_url) { get('/api/google/auth').then(setAuth).catch(() => {}); return }
    window.open(auth.auth_url, '_blank')
  }

  const refreshAuth = async () => {
    try { setAuth(await get('/api/google/auth')) } catch (e) { setError(e.message) }
  }

  const selectChapter = async (chapter) => {
    if (!currentBook) return
    setNotebookBusy(true); setNotebook(null); setNotebookStream(''); setKbProgress([]); setPhase('kb'); setError(null)
    setSelectedChapter(chapter)
    let built = false
    try {
      const meta = await post('/api/kb/build', {
        class_num: currentBook.class,
        file: currentBook.file,
        chapters: [{ title: chapter.title, start: chapter.start, end: chapter.end }],
      })
      if (meta && meta.chunks != null) {
        built = true
        setKb({ built: true, label: meta.label, chunks: meta.chunks })
      }
    } catch (e) {
      setError(e.message)
      setKbProgress([]); setPhase(null)
      if (/authoriz|token|account|401|502/i.test(e.message)) refreshAuth()
    }
    if (!built) {
      try {
        const st = await get('/api/kb/status')
        if (st && st.built) {
          setKb({ built: true, label: st.label, chunks: st.chunks })
          built = true
        }
      } catch {}
    }
    if (built) setPhase('ready')
    setNotebookBusy(false)
  }

  const startSlideGeneration = async (chapter) => {
    if (!currentBook) return
    setNotebookBusy(true); setNotebook(null); setNotebookStream(''); setKbProgress([]); setPhase('slides'); setError(null)
    try {
      await postStream('/api/notebook/stream', {
        class_num: currentBook.class,
        file: currentBook.file,
        chapter: { title: chapter.title, start: chapter.start, end: chapter.end },
        provider,
      }, {
        onDelta: (delta) => setNotebookStream((s) => s + delta),
        onDone: (text) => {
          const parsed = tryParseJson(text)
          if (parsed) setNotebook(normalizeSlides(parsed))
          else setError('Could not parse generated slides.')
          setNotebookStream(''); setPhase(null)
        },
        onError: (msg) => { setError(msg); setNotebookStream(''); setPhase(null) },
      })
    } catch (e) {
      setError(e.message)
      setNotebookStream(''); setPhase(null)
      if (/authoriz|token|account|401|502/i.test(e.message)) refreshAuth()
    }
    setNotebookBusy(false)
  }

  const solveExercise = async (chapter) => {
    if (!currentBook) return
    const ch = chapter || selectedChapter
    if (!ch) { setError('Select a chapter first.'); return }
    setExerciseBusy(true); setExercise(null); setError(null); setExerciseStream('')
    try {
      await postStream('/api/exercise/stream', {
        class_num: currentBook.class,
        file: currentBook.file,
        chapter: { title: ch.title, start: ch.start, end: ch.end },
        provider,
        exclude: [],
      }, {
        onDelta: (delta) => setExerciseStream((s) => s + delta),
        onDone: (data) => {
          let parsed = data
          if (typeof data === 'string') {
            let s = data.trim()
            s = s.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim()
            try { parsed = JSON.parse(s) } catch {
              const m = s.match(/\{[\s\S]*\}/)
              if (m) try { parsed = JSON.parse(m[0]) } catch {}
            }
          }
          if (parsed?.questions) {
            if (parsed.questions.length > 0) setExercise(parsed)
            else setError('No exercises found in this chapter.')
          }
          else if (parsed?.multiple_choice_questions?.length) {
            setExercise({ questions: parsed.multiple_choice_questions.map(q => ({
              question: q.question, answer: q.correct_answer || q.options?.[0] || '', explanation: ''
            }))})
          }
          else if (parsed?.raw) {
            try {
              const inner = JSON.parse(parsed.raw)
              if (inner?.questions) { setExercise(inner); return }
            } catch {}
            setError('Could not parse exercise output.')
          }
          else setError('Could not parse exercise output.')
          setExerciseStream('')
          setExerciseBusy(false)
        },
        onError: (msg) => { setError(msg); setExerciseStream(''); setExerciseBusy(false) },
      })
    } catch (e) { setError(e.message); setExerciseBusy(false) }
  }

  const loadMoreExercises = async () => {
    if (!currentBook || !exercise) return
    const ch = selectedChapter
    if (!ch) return
    const exclude = (exercise.questions || []).map(q => q.question)
    setExerciseBusy(true); setExerciseStream('')
    try {
      await postStream('/api/exercise/stream', {
        class_num: currentBook.class,
        file: currentBook.file,
        chapter: { title: ch.title, start: ch.start, end: ch.end },
        provider,
        exclude,
      }, {
        onDelta: (delta) => setExerciseStream((s) => s + delta),
        onDone: (data) => {
          let parsed = data
          if (typeof data === 'string') {
            let s = data.trim()
            s = s.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim()
            try { parsed = JSON.parse(s) } catch {
              const m = s.match(/\{[\s\S]*\}/)
              if (m) try { parsed = JSON.parse(m[0]) } catch {}
            }
          }
          const newQuestions = parsed?.questions || parsed?.multiple_choice_questions?.map(q => ({
            question: q.question, answer: q.correct_answer || q.options?.[0] || '', explanation: ''
          })) || []
          if (newQuestions.length > 0) {
            setExercise(prev => ({ ...prev, questions: [...(prev?.questions || []), ...newQuestions] }))
          } else {
            setError('No more questions available.')
          }
          setExerciseStream('')
          setExerciseBusy(false)
        },
        onError: (msg) => { setError(msg); setExerciseStream(''); setExerciseBusy(false) },
      })
    } catch (e) { setError(e.message); setExerciseBusy(false) }
  }

  const openTool = (type) => {
    if (!kb.built) {
      if (notebookBusy && phase === 'kb') {
        setError('Knowledge base is still building, please wait a moment…')
        return
      }
      setError(t(lang, 'buildFirst'))
      return
    }
    if (type === 'Slides') {
      generateSlides()
      return
    }
    generate(type)
  }

  const generateSlides = async () => {
    if (!currentBook || !selectedChapter) { setError('Select a chapter first.'); return }
    setBusy(true); setError(null); setResult(null)
    try {
      const d = await post('/api/google-slides/create', {
        class_num: currentBook.class,
        file: currentBook.file,
        chapter: selectedChapter,
      })
      setResult({ type: 'GoogleSlides', data: d })
      window.open(d.url, '_blank')
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const extractExcludeList = (type, data) => {
    if (!data) return []
    switch (type) {
      case 'MCQ': return (data.multiple_choice_questions || []).map(q => q.question)
      case 'Summary': return [...(data.concepts || []), ...(data.takeaways || [])]
      case 'Key Points': case 'Points to Remember': return data.points || []
      case 'Key Terms': return (data.terms || []).map(t => t.term)
      case 'Vocabulary': return (data.items || []).map(t => t.term)
      case 'Flashcards': return (data.cards || []).map(c => c.front)
      case 'Questions': return (data.questions || []).map(q => q.q)
      case 'Real-Life Examples': return (data.examples || []).map(e => e.title)
      case 'Fun Facts': return data.facts || []
      case 'Group Activity': return data.activity?.steps || []
      case 'Project Work': return data.project?.activities || []
      case 'Mind Map': return data.branches || []
      default: return []
    }
  }

  const mergeToolData = (type, oldData, newData) => {
    if (!newData) return oldData
    switch (type) {
      case 'MCQ':
        return { ...oldData, multiple_choice_questions: [...(oldData.multiple_choice_questions || []), ...(newData.multiple_choice_questions || [])] }
      case 'Summary':
        return {
          ...oldData,
          overview: oldData.overview || newData.overview,
          concepts: [...(oldData.concepts || []), ...(newData.concepts || [])],
          takeaways: [...(oldData.takeaways || []), ...(newData.takeaways || [])],
        }
      case 'Key Points': case 'Points to Remember':
        return { ...oldData, points: [...(oldData.points || []), ...(newData.points || [])] }
      case 'Key Terms':
        return { ...oldData, terms: [...(oldData.terms || []), ...(newData.terms || [])] }
      case 'Vocabulary':
        return { ...oldData, items: [...(oldData.items || []), ...(newData.items || [])] }
      case 'Flashcards':
        return { ...oldData, cards: [...(oldData.cards || []), ...(newData.cards || [])] }
      case 'Questions':
        return { ...oldData, questions: [...(oldData.questions || []), ...(newData.questions || [])] }
      case 'Real-Life Examples':
        return { ...oldData, examples: [...(oldData.examples || []), ...(newData.examples || [])] }
      case 'Fun Facts':
        return { ...oldData, facts: [...(oldData.facts || []), ...(newData.facts || [])] }
      case 'Group Activity':
        return { ...oldData, activity: { ...oldData.activity, steps: [...(oldData.activity?.steps || []), ...(newData.activity?.steps || [])] } }
      case 'Project Work':
        return { ...oldData, project: { ...oldData.project, activities: [...(oldData.project?.activities || []), ...(newData.project?.activities || [])] } }
      case 'Mind Map':
        return { ...oldData, branches: [...(oldData.branches || []), ...(newData.branches || [])] }
      default:
        return { ...oldData, ...newData }
    }
  }

  const generate = async (type) => {
    setShowModal(false)
    setBusy(true); setError(null); setResult(null); setStreamText('')
    try {
      await postStream('/api/resource/stream', { type, provider, class_num: currentBook?.class, file: currentBook?.file, chapter: selectedChapter?.title }, {
        onDelta: (delta) => setStreamText((s) => s + delta),
        onDone: (data) => {
          let parsed = data
          if (typeof data === 'string') {
            let s = data.trim()
            s = s.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim()
            try { parsed = JSON.parse(s) } catch {
              const m = s.match(/\{[\s\S]*\}/)
              if (m) try { parsed = JSON.parse(m[0]) } catch {}
            }
          }
          if (!parsed || typeof parsed !== 'object') {
            setError('Could not parse generated content. Please try again.')
          } else {
            if (['mcq', 'quiz', 'cards', 'topic', 'project'].includes(type.toLowerCase()) || type === 'MCQ') {
              post('/api/progress/record', { action: 'mcq', correct: true, score: 0, total: 0 }).then(setProgress).catch(() => {})
            }
            setResult({ type, data: parsed })
          }
          setStreamText('')
          setBusy(false)
        },
        onError: (msg) => { setError(msg); setStreamText(''); setBusy(false) },
      })
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const loadMoreTool = async () => {
    if (!result || !result.data) return
    const { type, data } = result
    const exclude = extractExcludeList(type, data)
    setBusy(true); setError(null); setStreamText('')
    try {
      await postStream('/api/resource/stream', { type, provider, class_num: currentBook?.class, file: currentBook?.file, chapter: selectedChapter?.title, exclude }, {
        onDelta: (delta) => setStreamText((s) => s + delta),
        onDone: (newData) => {
          let parsed = newData
          if (typeof newData === 'string') {
            let s = newData.trim()
            s = s.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim()
            try { parsed = JSON.parse(s) } catch {
              const m = s.match(/\{[\s\S]*\}/)
              if (m) try { parsed = JSON.parse(m[0]) } catch {}
            }
          }
          if (parsed && typeof parsed === 'object') {
            const merged = mergeToolData(type, data, parsed)
            setResult({ type, data: merged })
          } else {
            setError('Could not generate more content. Please try again.')
          }
          setStreamText('')
          setBusy(false)
        },
        onError: (msg) => { setError(msg); setStreamText(''); setBusy(false) },
      })
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const sendChat = async () => {
    if (!message.trim()) return
    const text = message
    const math = isMathQuestion(text)
    setMessage('')
    setChat((c) => [...c, { role: 'user', content: text }])
    setChat((c) => [...c, { role: 'assistant', content: '', steps: [], math, done: false }])
    setBusy(true)
    try {
      await postStream(math ? '/api/math/stream' : '/api/chat/stream', math ? { message: text } : { message: text, provider, class_num: currentBook?.class, file: currentBook?.file, chapter: selectedChapter?.title }, {
        onDelta: (delta) => setChat((c) => {
          const next = [...c]
          const cur = next[next.length - 1]
          if (!math) {
            next[next.length - 1] = { ...cur, content: (cur.content || '') + delta }
            return next
          }
          const merged = (cur.raw || '') + delta
          next[next.length - 1] = {
            ...cur,
            raw: merged,
            steps: extractLiveArray(merged, 'steps'),
            content: extractPartialString(merged, 'answer') || '',
            explanation: extractPartialString(merged, 'explanation'),
          }
          return next
        }),
        onDone: (meta) => {
          setChat((c) => {
            const next = [...c]
            const cur = next[next.length - 1]
            if (math) {
              const parsed = tryParseJson(meta?.text || meta || '')
              if (parsed) {
                next[next.length - 1] = {
                  ...cur,
                  raw: undefined,
                  content: parsed.answer || cur.content || '',
                  steps: parsed.steps || cur.steps || [],
                  explanation: parsed.explanation || cur.explanation,
                  done: true,
                }
              } else {
                next[next.length - 1] = { ...cur, content: meta?.text || cur.content || '', done: true }
              }
            } else if (meta && meta.sources) {
              next[next.length - 1] = { ...cur, sources: meta.sources, done: true }
            }
            return next
          })
        },
        onError: (msg) => setChat((c) => [...c, { role: 'assistant', content: `Error: ${msg}` }]),
      })
    } catch (e) {
      setChat((c) => [...c, { role: 'assistant', content: `Error: ${e.message}` }])
    }
    setBusy(false)
  }

  const disabled = busy || !selectedChapter

  const handleLogout = () => {
    localStorage.removeItem('aibooks_user')
    setUser(null)
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
        <div className="text-gray-500 text-lg">Loading...</div>
      </div>
    )
  }

  if (!user) {
    return <Login onLogin={setUser} />
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-shell text-slate-200">
      <Header
        lang={lang}
        user={user}
        onLogout={handleLogout}
        onTicket={() => generate('Progress')}
        onMenu={() => setSidebarOpen(true)}
        onTools={() => setToolsOpen(true)}
      />
      {error && (
        <div className="mx-3 mt-3 flex items-center justify-between rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300 sm:mx-6 sm:mt-4">
          <span>{error}</span>
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}
      <div className="flex">
        <div className="hidden md:block">
          <Sidebar
            groups={groups}
            openGroup={openGroup}
            toggleGroup={toggleGroup}
            books={books}
            loadChapters={loadChapters}
            chapters={chapters}
            selectChapter={selectChapter}
            selectedChapter={selectedChapter}
            busy={busy}
            currentBook={currentBook}
            result={result}
            lang={lang}
            auth={auth}
            connectGoogle={connectGoogle}
            refreshAuth={refreshAuth}
            loadingChapters={loadingChapters}
            fileMode={fileMode}
            setFileMode={setFileMode}
          />
        </div>
        <main className="min-w-0 flex-1 px-3 py-4 sm:px-6 sm:py-6">
          {kb.built && (
            <div className="mb-2 text-sm text-slate-400">{kb.label}</div>
          )}
          {kb.built && phase === 'ready' && (
            <div className="mb-6 rounded-xl border border-accent/40 bg-accent/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-white">Knowledge base ready</div>
                  <div className="text-xs text-slate-400">{kb.chunks} chunks indexed from the selected chapter.</div>
                </div>
                <button
                  onClick={() => startSlideGeneration(selectedChapter)}
                  className="flex shrink-0 items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-shell hover:bg-orange-500"
                >
                  <Presentation size={16} /> Generate Slides
                </button>
              </div>
            </div>
          )}
          {notebook && (
            <div className="mb-6">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">{safeStr(notebook.title) || 'Slides'}</h3>
                <button onClick={() => setNotebook(null)} className="text-slate-400 hover:text-slate-200"><X size={16} /></button>
              </div>
              <SlideViewer slides={notebook.slides} />
            </div>
          )}
          {notebookBusy && (
            <div className="mb-6 rounded-xl border border-panel bg-panel/60 p-4 text-sm text-slate-300">
              {phase === 'kb' ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-3 font-medium text-white">
                    <Cog size={18} className="animate-spin text-accent" />
                    Building knowledge base…
                  </div>
                  {kbProgress.map((ev, i) => {
                    const done = ev.step === 'embed' && ev.done != null && ev.total
                    const pct = done ? Math.round((ev.done / ev.total) * 100) : null
                    return (
                      <div key={i} className="flex items-center gap-2 pl-1 text-slate-400">
                        <span className="text-accent">▸</span>
                        <span>{ev.message}</span>
                        {pct != null && <span className="ml-auto text-xs text-slate-500">{pct}% ({ev.done}/{ev.total})</span>}
                      </div>
                    )
                  })}
                  {(() => {
                    const last = kbProgress[kbProgress.length - 1]
                    if (last?.step === 'embed' && last.done != null && last.total) {
                      return (
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/40">
                          <div
                            className="h-full rounded-full bg-accent transition-all duration-300"
                            style={{ width: `${Math.round((last.done / last.total) * 100)}%` }}
                          />
                        </div>
                      )
                    }
                    return (
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/40">
                        <div className="h-full w-1/3 animate-[progress-slide_1.2s_ease-in-out_infinite] rounded-full bg-accent" />
                      </div>
                    )
                  })()}
                </div>
              ) : (
                <div>
                  {(() => {
                    const live = extractLiveSlides(notebookStream)
                    if (live.slides.length > 0) {
                      return (
                        <>
                          {live.title && <h3 className="mb-3 text-lg font-bold text-white">{live.title}</h3>}
                          <SlideViewer slides={live.slides} />
                        </>
                      )
                    }
                    return (
                      <div className="flex items-center gap-3 text-sm text-slate-300">
                        <Cog size={18} className="animate-spin text-accent" />
                        <span className="font-medium text-white">Generating NotebookLM slides…</span>
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>
          )}

          {exerciseBusy && !exercise && !exerciseStream && (
            <div className="mb-6"><GeneratingCard title="Solving exercises..." /></div>
          )}
          {exerciseStream && !exercise && (
            <div className="mb-6 rounded-xl border border-accent/30 bg-panel/60 p-5">
              <div className="mb-3 flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                <h3 className="font-semibold text-accent">Solving exercises...</h3>
              </div>
              <pre className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{exerciseStream}<span className="animate-pulse text-accent">|</span></pre>
            </div>
          )}

          {exercise && (
            <div className="mb-6">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">{safeStr(exercise.title) || 'Exercise Solutions'}</h3>
                <button onClick={() => setExercise(null)} className="text-slate-400 hover:text-slate-200"><X size={16} /></button>
              </div>
              <ExerciseView exercise={exercise} onLoadMore={loadMoreExercises} loadingMore={exerciseBusy} />
              {exerciseBusy && !exerciseStream && (
                <div className="mt-4"><GeneratingCard title="Generating more questions..." /></div>
              )}
              {exerciseBusy && exerciseStream && (
                <div className="mt-4 rounded-xl border border-accent/30 bg-panel/60 p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                    <h3 className="text-sm font-semibold text-accent">Generating more questions...</h3>
                  </div>
                  <pre className="max-h-40 overflow-hidden whitespace-pre-wrap text-xs leading-relaxed text-slate-400">{exerciseStream.slice(-500)}<span className="animate-pulse text-accent">|</span></pre>
                </div>
              )}
            </div>
          )}
          <Tabs tab={tab} setTab={setTab} lang={lang} />
          {tab === 'Topic Content' && (
            <TopicContent
              kb={kb}
              busy={busy}
              openTool={openTool}
              provider={provider}
              setProvider={setProvider}
              lang={lang}
            />
          )}
          {tab === 'Teacher Resources' && (
            <TeacherResources kb={kb} generate={generate} busy={busy} lang={lang} />
          )}
          {tab === 'Learning Objectives' && (
            <LearningObjectives lang={lang} />
          )}
          {tab === 'Grid Image' && (
            <GridImage lang={lang} />
          )}
          {busy && !streamText && !result && (
            <div className="mt-6"><GeneratingCard title="Generating..." /></div>
          )}
          {!busy && !result && !streamText && (
            <p className="mt-6 text-sm text-slate-500">Select a chapter, then pick a tool to generate learning resources.</p>
          )}
          {result && (
            <div className="mt-6 rounded-xl border border-panel bg-panel/60 p-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-semibold text-accent">{TOOL_LABELS[result.type] || result.type}</h3>
                <button onClick={() => setResult(null)} className="text-slate-400 hover:text-slate-200"><X size={16} /></button>
              </div>
              <ResourceView data={result.data} type={result.type} lang={lang} onRegenerate={() => generate('MCQ')} generating={busy} loadMore={loadMoreTool} busy={busy} />
            </div>
          )}
          {busy && streamText && result && (
            <div className="mt-4 rounded-xl border border-accent/30 bg-panel/60 p-4">
              <div className="mb-2 flex items-center gap-2">
                <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                <h3 className="text-sm font-semibold text-accent">Generating more...</h3>
              </div>
              <pre className="max-h-40 overflow-hidden whitespace-pre-wrap text-xs leading-relaxed text-slate-400">{streamText.slice(-500)}<span className="animate-pulse text-accent">|</span></pre>
            </div>
          )}
          {busy && !streamText && result && (
            <div className="mt-4"><GeneratingCard title="Generating more..." /></div>
          )}
        </main>
        <div className="hidden lg:block">
          <ToolsPanel
            progress={progress}
            busy={busy}
            building={notebookBusy}
            generate={generate}
            openTool={openTool}
            solveExercise={solveExercise}
            exerciseBusy={exerciseBusy}
            kb={kb}
            selectedChapter={selectedChapter}
            lang={lang}
            setLang={setLang}
          />
        </div>
      </div>
      {/* Mobile drawers */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex max-w-[85vw] flex-col bg-shell shadow-2xl">
            <div className="flex justify-end border-b border-panel p-2">
              <button onClick={() => setSidebarOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-panel hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <Sidebar
                groups={groups}
                openGroup={openGroup}
                toggleGroup={(g) => { toggleGroup(g); if (openGroup !== g.id) setSidebarOpen(false) }}
                books={books}
                loadChapters={(b) => { loadChapters(b); setSidebarOpen(false) }}
                chapters={chapters}
                selectChapter={(c) => { selectChapter(c); setSidebarOpen(false) }}
                selectedChapter={selectedChapter}
                busy={busy}
                currentBook={currentBook}
                result={result}
                lang={lang}
                auth={auth}
                connectGoogle={connectGoogle}
                refreshAuth={refreshAuth}
                loadingChapters={loadingChapters}
                fileMode={fileMode}
                setFileMode={setFileMode}
              />
            </div>
          </div>
        </div>
      )}
      {toolsOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setToolsOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex max-w-[85vw] flex-col bg-shell shadow-2xl">
            <div className="flex justify-end border-b border-panel p-2">
              <button onClick={() => setToolsOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-panel hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <ToolsPanel
                progress={progress}
                busy={busy}
                building={notebookBusy}
                generate={generate}
                openTool={(type) => { openTool(type); setToolsOpen(false) }}
                solveExercise={() => { solveExercise(); setToolsOpen(false) }}
                exerciseBusy={exerciseBusy}
                kb={kb}
                selectedChapter={selectedChapter}
                lang={lang}
                setLang={setLang}
              />
            </div>
          </div>
        </div>
      )}
      {/* Floating Chat Button & Drawer */}
      <button
        onClick={() => setToolsOpen(true)}
        className="fixed bottom-24 right-6 z-40 rounded-full border border-panel bg-panel p-4 shadow-xl text-accent transition-all hover:scale-105 focus:outline-none lg:hidden"
        aria-label="Open tools"
      >
        <Wrench size={22} className="text-accent" />
      </button>
      <button
        onClick={() => setIsChatOpen(true)}
        className="fixed bottom-6 right-6 z-50 rounded-full bg-accent p-4 shadow-xl text-shell hover:bg-orange-500 transition-all hover:scale-105 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-shell"
        aria-label="Open AI Chat"
      >
        <Brain size={24} className="text-shell" />
      </button>
      {isChatOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-end">
          <div className="absolute inset-0 bg-black/50" onClick={() => setIsChatOpen(false)} />
          <div className="relative flex h-[85dvh] w-full max-w-md flex-col overflow-hidden rounded-tl-2xl rounded-tr-2xl border border-panel bg-panel/95 shadow-2xl animate-slide-up sm:h-[70vh] sm:rounded-2xl sm:mr-4 sm:mb-4">
            <div className="flex items-center justify-between border-b border-panel px-4 py-3">
              <h3 className="flex items-center gap-2 font-semibold text-white">
                <Brain size={20} className="text-accent" /> {t(lang, 'ask')}
              </h3>
              <button onClick={() => setIsChatOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-panel hover:text-white">
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 p-4">
              {chat.length === 0 && <p className="text-slate-400 text-center py-8">{t(lang, 'askHint')}</p>}
              {chat.map((m, i) => (
                <div key={i} className="max-w-[85%]">
                  <ChatBubble m={m} busy={busy} />
                </div>
              ))}
              {busy && <div className="flex items-center gap-2 text-xs text-slate-400"><Cog size={14} className="animate-spin" /> {t(lang, 'thinking')}</div>}
            </div>
            <div className="border-t border-panel p-4">
              <div className="flex gap-2">
                <input
                  name="chat-message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !disabled && sendChat()}
                  disabled={disabled}
                  placeholder={t(lang, 'ask')}
                  className="flex-1 rounded-xl border border-panel bg-shell px-4 py-2.5 text-sm outline-none focus:border-accent disabled:opacity-50"
                />
                <button onClick={sendChat} disabled={disabled} className="rounded-xl bg-accent px-5 text-shell hover:bg-orange-500 disabled:opacity-50">
                  <Send size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showModal && (
        <GenerateModal
          type={modalType}
          quantity={quantity}
          setQuantity={setQuantity}
          difficulty={difficulty}
          setDifficulty={setDifficulty}
          onClose={() => setShowModal(false)}
          onGenerate={() => generate(modalType)}
          provider={provider}
          setProvider={setProvider}
          providers={providers}
          lang={lang}
        />
      )}
    </div>
  )
}

function Header({ lang, user, onLogout, onTicket, onMenu, onTools }) {
  const userLabel = user?.full_name || user?.username || 'User'
  const userInitial = userLabel.charAt(0).toUpperCase()
  return (
    <header className="flex h-14 items-center justify-between border-b border-panel bg-panel/60 px-3 sm:h-16 sm:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onMenu}
          className="rounded-lg border border-panel p-2 text-slate-400 hover:text-slate-200 md:hidden"
          aria-label="Open menu"
        >
          <Menu size={18} />
        </button>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-shell sm:h-9 sm:w-9">
          <BookOpen size={18} />
        </div>
        <span className="text-base font-bold text-white sm:text-lg">AI Books</span>
        <span className="ml-2 hidden rounded-full bg-accent/15 px-3 py-1 text-xs font-medium text-accent sm:inline">
          {t(lang, 'badge')}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-1.5 sm:gap-3">
        <button
          onClick={onTools}
          className="rounded-lg border border-accent/50 p-2 text-accent hover:bg-accent/10 lg:hidden"
          aria-label="Open tools"
        >
          <Wrench size={17} />
        </button>
        <button
          onClick={onTicket}
          className="hidden rounded-lg border border-accent/50 px-3 py-2 text-sm font-medium text-accent hover:bg-accent/10 sm:inline-block"
        >
          {t(lang, 'raiseTicket')}
        </button>
        <button className="hidden rounded-lg border border-panel p-2 text-slate-400 hover:text-slate-200 sm:block">
          <Bell size={18} />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-orange-500 text-sm font-bold text-shell sm:h-9 sm:w-9">
            {userInitial}
          </div>
          <div className="hidden lg:block">
            <div className="text-sm font-semibold text-white">{userLabel}</div>
            <div className="text-xs text-slate-400">{user?.role || 'Student'}</div>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="rounded-lg border border-panel p-2 text-slate-400 hover:text-red-400 hover:border-red-500/30"
          title="Sign out"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  )
}

function Sidebar({ groups, openGroup, toggleGroup, books, loadChapters, chapters, selectChapter, selectedChapter, busy, currentBook, result, lang, auth, connectGoogle, refreshAuth, loadingChapters, fileMode, setFileMode }) {
  const filteredBooks = (books || []).filter((b) => {
    if (!b || !b.file) return false
    return b.file.endsWith('.md')
  })
  return (
    <aside className="w-72 shrink-0 border-r border-panel p-4">
      <div className="mb-3 flex items-center justify-between rounded-lg border border-panel bg-panel/40 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${auth?.authorized ? 'bg-green-400' : 'bg-slate-500'}`} />
          <span className="text-xs font-medium text-slate-300">
            {auth === null ? t(lang, 'loading') : auth?.authorized ? 'Google Connected' : 'Google'}
          </span>
        </div>
        {!auth?.authorized ? (
          <button onClick={connectGoogle} className="rounded bg-accent/15 px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/25">
            Connect
          </button>
        ) : (
          <button onClick={refreshAuth} className="rounded px-2 py-1 text-xs text-slate-400 hover:text-slate-200">Refresh</button>
        )}
      </div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
        {t(lang, 'curriculum')}
      </h2>
      <h3 className="mb-2 text-sm font-semibold text-slate-200">Books</h3>
      <div className="space-y-1">
        {groups.map((g) => (
          <div key={g.id}>
            <button
              onClick={() => toggleGroup(g)}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-panel"
            >
              <span className="font-medium">{g.label}</span>
              <span className="flex items-center gap-1 text-xs text-slate-400">
                {g.level}
                {openGroup === g.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            </button>
            {openGroup === g.id && filteredBooks && (
              <div className="ml-3 space-y-0.5 border-l border-panel pl-3">
                {filteredBooks.map((b, i) => b.available ? (
                  <div key={i}>
                    <button
                      onClick={() => loadChapters({ ...b, class: g.class_num || parseInt(openGroup, 10) })}
                      className={`block w-full rounded px-2 py-1.5 text-left text-sm leading-tight ${
                        currentBook?.file === b.file ? 'bg-accent/15 text-accent' : 'text-slate-300 hover:bg-panel'
                      }`}
                    >
                      {b.subject || b.file}
                    </button>
                    {currentBook?.file === b.file && (
                      <div className="mt-1 space-y-1 border-l border-panel pl-2">
                        <h3 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                          {t(lang, 'chapters')}
                        </h3>
                        {loadingChapters && (
                          <div className="flex items-center gap-2 text-slate-400 text-xs py-2">
                            <Cog size={14} className="animate-spin text-accent" />
                            <span>{t(lang, 'loading')}</span>
                          </div>
                        )}
                        <div className="max-h-80 space-y-1 overflow-y-auto pr-1">
                          {chapters.map((c) => (
                            <button
                              key={c.id}
                              onClick={() => selectChapter(c)}
                              disabled={busy}
                              className={`block w-full rounded px-2 py-1.5 text-left text-xs leading-tight hover:bg-panel disabled:opacity-50 ${
                                selectedChapter?.id === c.id
                                  ? 'bg-accent/15 text-accent font-semibold'
                                  : result?.type === 'Slides' && result?.data?.topic?.includes(c.title)
                                    ? 'text-accent'
                                    : 'text-slate-300'
                              }`}
                            >
                              {typeof c.title === 'string' ? c.title : (typeof c.title === 'object' && c.title ? (c.title['सुरु'] || Object.values(c.title)[0] || `Chapter ${c.id + 1}`) : `Chapter ${c.id + 1}`)}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div key={i} className="flex items-center justify-between rounded px-2 py-1.5 text-sm text-slate-500">
                    <span>{b.subject || b.file}</span>
                    <span className="text-xs">{t(lang, 'notAvailable')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  )
}

function Tabs({ tab, setTab, lang }) {
  const tabs = [
    ['Topic Content', 'tabTopic'],
    ['Teacher Resources', 'tabTeacher'],
    ['Learning Objectives', 'tabObjectives'],
    ['Grid Image', 'tabGrid'],
  ]
  return (
    <div className="mb-6 flex gap-2 overflow-x-auto">
      {tabs.map(([id, key]) => (
        <button
          key={id}
          onClick={() => setTab(id)}
          className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${
            tab === id ? 'bg-accent text-shell' : 'bg-panel text-slate-300 hover:bg-panel/70'
          }`}
        >
          {t(lang, key)}
        </button>
      ))}
    </div>
  )
}

function TopicContent({ kb, busy, openTool, provider, setProvider, lang }) {
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-panel bg-panel/40 p-4">
        <div>
          <h3 className="font-semibold text-white">{t(lang, 'studyTools')}</h3>
          <p className="text-sm text-slate-400">
            {kb.built
              ? t(lang, 'kbReady', { chunks: kb.chunks, label: kb.label })
              : t(lang, 'kbHint')}
          </p>
        </div>
        <select
          name="provider"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="rounded-lg border border-panel bg-shell px-3 py-2 text-sm"
        >
          {['Groq (openai/gpt-oss-20b)', 'Qwen (free HF endpoint)'].map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-3 rounded-xl border border-panel bg-panel/60 p-4 text-sm text-slate-300">
        <ListChecks size={18} className="text-accent" />
        Use the tools on the right to generate learning resources from the selected chapters.
      </div>
      {busy && (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-panel bg-panel/60 p-4 text-sm text-slate-300">
          <Cog size={18} className="animate-spin text-accent" />
          Generating with {provider || 'model'}…
        </div>
      )}
    </div>
  )
}

function TeacherResources({ kb, generate, busy, lang }) {
  return (
    <div>
      <div className="mb-4 rounded-xl border border-panel bg-panel/40 p-4 text-sm text-slate-400">
        {t(lang, 'teacherReady')}
        {!kb.built && ' ' + t(lang, 'buildFirst')}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {[...TEACHER_RESOURCES, 'Progress'].map((tool) => {
          const Icon = RESOURCE_ICONS[tool] || FileText
          return (
            <button
              key={tool}
              onClick={() => generate(tool)}
              className="flex items-center gap-3 rounded-xl border border-panel bg-panel/60 p-4 text-left transition hover:border-accent/50 hover:bg-panel"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
                <Icon size={18} />
              </div>
              <div>
                <div className="text-sm font-semibold text-white">{tool}</div>
                <div className="text-xs text-slate-400">{t(lang, 'generate')} {tool.toLowerCase()}</div>
              </div>
            </button>
          )
        })}
      </div>
      {busy && (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-panel bg-panel/60 p-4 text-sm text-slate-300">
          <Cog size={18} className="animate-spin text-accent" />
          Generating teacher resource…
        </div>
      )}
    </div>
  )
}

function LearningObjectives({ lang }) {
  return (
    <div className="rounded-xl border border-panel bg-panel/40 p-8 text-center">
      <GraduationCap size={32} className="mx-auto mb-3 text-accent" />
      <h3 className="font-semibold text-white">{t(lang, 'tabObjectives')}</h3>
      <p className="mt-2 text-sm text-slate-400">{t(lang, 'objectivesHint')}</p>
    </div>
  )
}

function GridImage({ lang }) {
  return (
    <div className="rounded-xl border border-panel bg-panel/40 p-8 text-center">
      <FileText size={32} className="mx-auto mb-3 text-accent" />
      <h3 className="font-semibold text-white">{t(lang, 'tabGrid')}</h3>
      <p className="mt-2 text-sm text-slate-400">{t(lang, 'gridHint')}</p>
    </div>
  )
}

function ToolsPanel({ progress, busy, building, generate, openTool, solveExercise, exerciseBusy, kb, selectedChapter, lang, setLang }) {
  const hasChapter = !!selectedChapter
  const disabled = !hasChapter || busy || building || exerciseBusy
  return (
    <aside className="flex w-60 shrink-0 flex-col gap-4 overflow-y-auto border-l border-panel p-4">
      {!hasChapter && (
        <div className="rounded-xl border border-panel bg-panel/40 p-3 text-center text-xs text-slate-500">
          Select a chapter to enable tools &amp; generate slides
        </div>
      )}
      <div className={!hasChapter ? 'pointer-events-none opacity-40' : ''}>
        <div>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <ListChecks size={16} className="text-accent" /> {t(lang, 'contents')}
          </h3>
          <div className="grid grid-cols-1 gap-1.5">
            <button
              onClick={() => solveExercise()}
              disabled={disabled}
              className="flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-left text-xs font-semibold text-accent hover:border-accent/70 hover:bg-accent/20 disabled:opacity-50"
            >
              <FileText size={14} className="shrink-0" />
              <span className="truncate">Exercise</span>
            </button>
            {STUDENT_TOOLS.map((tool) => {
              const Icon = RESOURCE_ICONS[tool] || Sparkles
              return (
                <button
                  key={tool}
                  onClick={() => openTool(tool)}
                  disabled={disabled}
                  className="flex items-center gap-2 rounded-lg border border-panel bg-panel/40 px-2.5 py-1.5 text-left text-xs text-slate-300 hover:border-accent/50 hover:text-white disabled:opacity-50"
                >
                  <Icon size={14} className="shrink-0 text-accent" />
                  <span className="truncate">{TOOL_LABELS[tool] || tool}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="mt-4 rounded-xl border border-panel bg-panel/60 p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <Flame size={16} className="text-accent" /> {t(lang, 'progress')}
          </h3>
          {progress ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Overall</span><span className="font-bold text-accent">{progress.overall}%</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Topics</span><span>{progress.topics_viewed}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Cards</span><span>{progress.flashcards_completed}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">MCQs</span><span>{progress.mcqs_completed}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Quiz avg</span><span>{progress.quiz_avg}%</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Streak</span><span>{progress.streak}d</span></div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-shell">
                <div className="h-full rounded-full bg-accent" style={{ width: `${progress.overall}%` }} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">{t(lang, 'loading')}</p>
          )}
        </div>
        </div>

        <div className="flex items-center justify-between rounded-xl border border-panel bg-panel/40 px-3 py-2">
          <span className="text-xs text-slate-400">{t(lang, 'language')}</span>
        <select
          name="language"
          value={lang}
          onChange={(e) => setLang(e.target.value)}
          className="rounded-lg border border-panel bg-shell px-2 py-1 text-xs"
        >
          {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
        </select>
      </div>
    </aside>
  )
}

function GenerateModal({ type, quantity, setQuantity, difficulty, setDifficulty, onClose, onGenerate, provider, setProvider, providers, lang }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-2xl border border-panel bg-panel p-5 sm:p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-white">Generate {type}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <label className="mb-1 block text-sm text-slate-400">Quantity</label>
        <div className="mb-4 flex items-center gap-3">
          <input
            name="quantity"
            type="range"
            min={1}
            max={20}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
            className="range-accent flex-1"
          />
          <span className="w-8 text-right text-sm font-semibold text-white">{quantity}</span>
        </div>

        <label className="mb-1 block text-sm text-slate-400">Difficulty</label>
        <div className="mb-4 flex gap-2">
          {DIFFICULTY_LEVELS.map((d) => (
            <button
              key={d}
              onClick={() => setDifficulty(d)}
              className={`flex-1 rounded-lg border py-1.5 text-sm ${
                difficulty === d ? 'border-accent bg-accent/15 text-accent' : 'border-panel bg-shell text-slate-300'
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        <label className="mb-1 block text-sm text-slate-400">Model</label>
        <select
          name="model"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="mb-5 w-full rounded-lg border border-panel bg-shell px-3 py-2 text-sm"
        >
          {(providers.length ? providers : ['Mistral (free)', 'Groq (openai/gpt-oss-20b)', 'Qwen (free HF endpoint)']).map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-panel py-2 text-sm text-slate-300 hover:bg-shell">
            Cancel
          </button>
          <button onClick={onGenerate} className="flex-1 rounded-lg bg-accent py-2 text-sm font-semibold text-shell hover:bg-orange-500">
            Generate
          </button>
        </div>
      </div>
    </div>
  )
}

function SlideViewer({ slides }) {
  const total = slides?.length || 0
  const [idx, setIdx] = useState(0)
  if (!total) return null
  const s = slides[Math.min(idx, total - 1)]
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <button
          onClick={() => setIdx(Math.max(0, idx - 1))}
          disabled={idx === 0}
          className="rounded-lg border border-panel p-2 text-slate-400 hover:text-slate-200 disabled:opacity-40"
        >
          <ChevronLeft size={18} />
        </button>
        <span className="text-sm text-slate-400">Page {idx + 1} of {total}</span>
        <button
          onClick={() => setIdx(Math.min(total - 1, idx + 1))}
          disabled={idx === total - 1}
          className="rounded-lg border border-panel p-2 text-slate-400 hover:text-slate-200 disabled:opacity-40"
        >
          <ChevronRight size={18} />
        </button>
      </div>
      <div className="flex aspect-video items-stretch justify-center overflow-hidden rounded-xl border border-panel bg-shell">
        {s.image && (
          <div className="hidden w-2/5 shrink-0 items-center justify-center border-r border-panel bg-panel/20 p-2 sm:flex">
            <img
              src={s.image}
              alt={s.title}
              loading="lazy"
              className="h-full w-full rounded-lg object-cover"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          </div>
        )}
        <div className="flex flex-1 flex-col items-center justify-center p-4 text-center sm:p-8">
          <div className="text-xs font-semibold uppercase tracking-wider text-accent">Slide {idx + 1}</div>
          <h4 className="mt-3 text-lg font-bold text-white sm:text-2xl">{s.title}</h4>
          {s.subtitle && <p className="mt-1 text-xs text-slate-400 sm:text-sm">{s.subtitle}</p>}
          {s.bullets?.length > 0 && (
            <ul className="mt-4 list-disc space-y-1.5 pl-5 text-left text-xs text-slate-300 sm:text-sm">
              {s.bullets.map((b, j) => <li key={j}>{b}</li>)}
            </ul>
          )}
        </div>
      </div>
      {s.note && (
        <div className="mt-3 rounded-lg border border-panel bg-panel/40 px-4 py-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Speaker notes</div>
          <p className="text-sm text-slate-300">{s.note}</p>
        </div>
      )}
      <div className="mt-3 flex justify-center gap-1.5">
        {slides.map((_, i) => (
          <button
            key={i}
            onClick={() => setIdx(i)}
            className={`h-2 rounded-full ${i === idx ? 'w-6 bg-accent' : 'w-2 bg-panel hover:bg-slate-600'}`}
          />
        ))}
      </div>
    </div>
  )
}

function SolutionWindow({ steps, streaming, open, onToggle }) {
  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-indigo-400/30 bg-slate-900/85">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs font-semibold text-indigo-300 transition-colors hover:bg-indigo-500/10"
      >
        <span className="flex items-center gap-1.5">
          <Sparkles size={12} className="text-accent" /> Step-by-step solution
        </span>
        <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="max-h-56 overflow-y-auto border-t border-indigo-400/20 px-3 py-2 font-mono text-xs leading-relaxed text-slate-200">
          {steps.map((s, i) => (
            <div key={i} className="mb-1 whitespace-pre-wrap break-words">{s}</div>
          ))}
          {streaming && <span className="inline-block h-3 w-1.5 animate-pulse bg-accent align-middle" />}
        </div>
      )}
    </div>
  )
}

function ChatBubble({ m, busy }) {
  const [open, setOpen] = useState(true)
  const user = m.role === 'user'
  return (
    <div className={`rounded-xl px-4 py-3 ${user ? 'ml-auto bg-accent/20 text-white' : 'mr-auto bg-shell text-slate-300'}`}>
      {user ? (
        m.content
      ) : (
        <>
          {m.steps && m.steps.length > 0 && (
            <SolutionWindow steps={m.steps} streaming={!m.done && busy} open={open} onToggle={() => setOpen(!open)} />
          )}
          {m.content}
          {!m.content && busy && <span className="inline-block h-3 w-1.5 animate-pulse bg-accent align-middle" />}
          {m.sources && m.sources.length > 0 && (
            <div className="mt-2 text-xs text-slate-500">Sources: {m.sources.map((s) => s.page || s.title).join(', ')}</div>
          )}
        </>
      )}
    </div>
  )
}

function ExerciseView({ exercise, onLoadMore, loadingMore }) {
  return (
    <div className="space-y-4">
      {Array.isArray(exercise?.questions) ? exercise.questions.map((q, i) => (
        <div key={i} className="rounded-xl border border-panel bg-panel/60 p-4">
          <div className="mb-2 font-semibold text-accent">
            Q{i + 1}. {safeStr(q.question)}
          </div>
          <div className="mb-1 text-slate-200">
            <span className="font-semibold text-slate-400">Answer: </span>{safeStr(q.answer)}
          </div>
          {q.explanation && (
            <div className="text-sm text-slate-400">
              <span className="font-semibold text-slate-500">Explanation: </span>{safeStr(q.explanation)}
            </div>
          )}
        </div>
      )) : null}
      {Array.isArray(exercise?.questions) && exercise.questions.length > 0 && (
        <LoadMoreButton onClick={onLoadMore} loading={loadingMore} />
      )}
    </div>
  )
}

function LoadMoreButton({ onClick, loading }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="mt-4 w-full rounded-xl border-2 border-dashed border-accent/40 bg-accent/5 py-3 text-sm font-medium text-accent hover:bg-accent/10 hover:border-accent/60 transition disabled:opacity-50"
    >
      {loading ? 'Loading more...' : 'Load More'}
    </button>
  )
}

function GeneratingCard({ title = 'Generating...' }) {
  return (
    <div className="rounded-xl border border-accent/30 bg-panel/60 p-5">
      <div className="mb-3 flex items-center gap-2">
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        <h3 className="font-semibold text-accent">{title}</h3>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-3/4 animate-pulse rounded bg-shell" />
        <div className="h-3 w-full animate-pulse rounded bg-shell" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-shell" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-shell" />
      </div>
    </div>
  )
}

function ResourceView({ data, type, lang, onRegenerate, generating, loadMore, busy }) {
  const d = data || {}
  if (type === 'Progress') {
    return (
      <div className="space-y-2 text-sm">
        <div className="flex justify-between"><span className="text-slate-400">Overall</span><b className="text-accent">{d.overall}%</b></div>
        <div className="flex justify-between"><span className="text-slate-400">Topics viewed</span><span>{d.topics_viewed}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Flashcards</span><span>{d.flashcards_completed}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">MCQs completed</span><span>{d.mcqs_completed}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Quiz average</span><span>{d.quiz_avg}%</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Projects</span><span>{d.projects}</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Streak</span><span>{d.streak}d</span></div>
        <div className="flex justify-between"><span className="text-slate-400">Activity days</span><span>{d.activity_days}</span></div>
        {d.insight && <p className="rounded-lg bg-shell p-3 text-slate-300">{safeStr(d.insight)}</p>}
      </div>
    )
  }
  if (type === 'GoogleSlides') {
    return (
      <div className="space-y-3 text-sm">
        <p className="text-slate-300">Google Slides presentation created successfully!</p>
        <p className="text-slate-400 text-xs">Title: {safeStr(d.title)}</p>
        <a href={d.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-accent hover:underline">
          <ExternalLink size={16} /> Open in Google Slides
        </a>
        <p className="text-xs text-slate-500">Presentation ID: {safeStr(d.presentation_id)}</p>
      </div>
    )
  }
  if (type === 'Summary') {
    return (
      <div className="space-y-3 text-sm">
        <p className="text-slate-300">{safeStr(d.overview)}</p>
        {d.concepts?.length > 0 && <List label="Concepts" items={d.concepts} />}
        {d.takeaways?.length > 0 && <List label="Takeaways" items={d.takeaways} />}
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Key Points' || type === 'Points to Remember') {
    return (
      <div>
        <List label={type} items={d.points} />
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Key Terms') {
    return (
      <div className="space-y-2 text-sm">
        {Array.isArray(d.terms) ? d.terms.map((tm, i) => (
          <div key={i} className="rounded-lg bg-shell p-3">
            <b className="text-accent">{safeStr(tm.term)}</b>
            <p className="text-slate-300">{safeStr(tm.definition)}</p>
          </div>
        )) : null}
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Vocabulary') {
    return (
      <div className="space-y-2 text-sm">
        {Array.isArray(d.items) ? d.items.map((it, i) => (
          <div key={i} className="rounded-lg bg-shell p-3">
            <b className="text-accent">{safeStr(it.term)}</b>
            <p className="text-slate-300">{safeStr(it.meaning)}</p>
            {it.example && <p className="text-xs text-slate-400">e.g. {safeStr(it.example)}</p>}
          </div>
        )) : null}
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Flashcards') {
    return (
      <div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {Array.isArray(d.cards) ? d.cards.map((c, i) => (
            <div key={i} className="rounded-lg bg-shell p-3">
              <b className="text-white">{safeStr(c.front)}</b>
              <p className="mt-1 text-slate-300">{safeStr(c.back)}</p>
            </div>
          )) : null}
        </div>
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'MCQ') {
    let mcqData = d
    if (Array.isArray(d.multiple_choice_questions) && !d.questions) {
      mcqData = {
        ...d,
        questions: d.multiple_choice_questions.map((q) => ({
          q: q.question,
          options: q.options,
          answer: q.correct_answer,
        })),
      }
    }
    return (
      <div>
        <MCQViewer data={mcqData} onRegenerate={onRegenerate} generating={generating} />
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Questions') {
    return (
      <div className="space-y-2 text-sm">
        {Array.isArray(d.questions) ? d.questions.map((q, i) => (
          <div key={i} className="rounded-lg bg-shell p-3">
            <b className="text-white">{i + 1}. {safeStr(q.q)}</b>
            <p className="mt-1 text-slate-300">{safeStr(q.a)}</p>
          </div>
        )) : null}
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Real-Life Examples') {
    return (
      <div className="space-y-2 text-sm">
        {Array.isArray(d.examples) ? d.examples.map((ex, i) => (
          <div key={i} className="rounded-lg bg-shell p-3">
            <b className="text-accent">{safeStr(ex.title)}</b>
            <p className="text-slate-300">{safeStr(ex.description)}</p>
          </div>
        )) : null}
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Fun Facts') {
    return (
      <div>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-300">
          {Array.isArray(d.facts) ? d.facts.map((f, i) => <li key={i}>{safeStr(f)}</li>) : null}
        </ul>
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Group Activity') {
    return (
      <div className="space-y-2 text-sm">
        <b className="text-accent">{safeStr(d.activity?.title)}</b>
        <p className="text-slate-300">{safeStr(d.activity?.description)}</p>
        <ol className="list-decimal space-y-1 pl-5 text-slate-300">
          {Array.isArray(d.activity?.steps) ? d.activity.steps.map((s, i) => <li key={i}>{safeStr(s)}</li>) : null}
        </ol>
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Project Work') {
    return (
      <div className="space-y-2 text-sm">
        <b className="text-accent">{safeStr(d.project?.title)}</b>
        <p className="text-slate-300">{safeStr(d.project?.objective)}</p>
        <List label="Activities" items={d.project?.activities} />
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Mind Map') {
    return (
      <div className="space-y-2 text-sm">
        <b className="text-accent">Center: {safeStr(d.center)}</b>
        <div className="flex flex-wrap gap-2">
          {Array.isArray(d.branches) ? d.branches.map((b, i) => (
            <span key={i} className="rounded-full bg-accent/15 px-3 py-1 text-accent">{safeStr(b)}</span>
          )) : null}
        </div>
        {loadMore && <LoadMoreButton onClick={loadMore} loading={busy} />}
      </div>
    )
  }
  if (type === 'Slides') {
    return <SlideViewer slides={d.slides} />
  }
  if (type === 'Videos') {
    return (
      <div className="space-y-2 text-sm">
        {Array.isArray(d.videos) ? d.videos.map((v, i) => (
          <div key={i} className="rounded-lg bg-shell p-3">
            <b className="text-accent">{safeStr(v.title)}</b>
            {v.url && <p className="truncate text-xs text-slate-500">{v.url}</p>}
            {v.desc && <p className="text-slate-300">{safeStr(v.desc)}</p>}
          </div>
        )) : null}
      </div>
    )
  }
  return (
    <pre className="whitespace-pre-wrap rounded-lg bg-shell p-4 text-sm text-slate-300">
      {typeof d === 'string' ? d : JSON.stringify(d, null, 2)}
    </pre>
  )
}

function List({ label, items }) {
  return (
    <div>
      {label && <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</h4>}
      <ul className="list-disc space-y-1 pl-5 text-slate-300">
        {Array.isArray(items) ? items.map((it, i) => <li key={i}>{safeStr(it)}</li>) : null}
      </ul>
    </div>
  )
}