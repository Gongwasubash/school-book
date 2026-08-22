import React, { useEffect, useRef, useState } from 'react'
import {
  Check, X, Lightbulb, ChevronLeft, ChevronRight, RefreshCw,
  Trophy, Clock, RotateCcw, ListChecks, CircleAlert,
} from 'lucide-react'

const LETTERS = ['A', 'B', 'C', 'D']

function useTimer(running) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [running])
  return elapsed
}

function fmt(sec) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function MCQViewer({ data, onRegenerate, generating }) {
  const questions = data?.questions || []
  const title = data?.topic || data?.title || 'MCQ Practice'
  const [idx, setIdx] = useState(0)
  const [answers, setAnswers] = useState({})      // {qIndex: chosenOptionIndex}
  const [direction, setDirection] = useState('right')
  const [submitted, setSubmitted] = useState(false)
  const [startedAt] = useState(Date.now())
  const [elapsed, setElapsed] = useState(0)
  const [showReview, setShowReview] = useState(false)
  const timerRef = useRef(null)

  const total = questions.length
  const q = questions[idx]
  const answered = Object.keys(answers).length
  const progress = total ? (answered / total) * 100 : 0

  useEffect(() => {
    if (submitted) {
      setElapsed(Math.round((Date.now() - startedAt) / 1000))
      if (timerRef.current) clearInterval(timerRef.current)
    } else if (!timerRef.current) {
      timerRef.current = setInterval(() => setElapsed(Math.round((Date.now() - startedAt) / 1000)), 1000)
    }
    return () => clearInterval(timerRef.current)
  }, [submitted, startedAt])

  const correctCount = questions.reduce(
    (acc, qq, i) => acc + (answers[i] !== undefined && qq.options[answers[i]] === qq.answer ? 1 : 0),
    0,
  )
  const scorePct = total ? Math.round((correctCount / total) * 100) : 0

  const pick = (i) => {
    if (submitted) return
    setAnswers((a) => ({ ...a, [idx]: i }))
  }

  const go = (dir) => {
    setDirection(dir)
    setIdx((i) => {
      const n = i + (dir === 'right' ? 1 : -1)
      return Math.max(0, Math.min(total - 1, n))
    })
  }

  const retry = () => {
    setAnswers({}); setIdx(0); setSubmitted(false); setShowReview(false); setElapsed(0)
  }

  if (!total) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-xl border border-panel bg-panel/40 p-8 text-sm text-slate-400">
        <CircleAlert size={18} className="text-accent" /> No MCQs generated yet.
      </div>
    )
  }

  if (submitted && !showReview) {
    const grade = scorePct >= 80 ? 'Excellent!' : scorePct >= 60 ? 'Good job!' : scorePct >= 40 ? 'Keep practicing!' : 'Try again!'
    return (
      <div className="mcq-pop flex flex-col items-center rounded-2xl border border-panel bg-panel/60 p-6 text-center sm:p-10">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/15 sm:h-20 sm:w-20">
          <Trophy size={32} className="text-accent" />
        </div>
        <h3 className="mt-4 text-xl font-bold text-white sm:text-2xl">{grade}</h3>
        <p className="mt-1 text-sm text-slate-400">{title}</p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-4 sm:gap-8">
          <div className="text-center">
            <div className="text-3xl font-bold text-accent">{scorePct}%</div>
            <div className="mt-1 text-xs uppercase tracking-wider text-slate-500">Score</div>
          </div>
          <div className="h-10 w-px bg-panel" />
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-3xl font-bold text-white">
              <Clock size={20} className="text-slate-400" /> {fmt(elapsed)}
            </div>
            <div className="mt-1 text-xs uppercase tracking-wider text-slate-500">Time</div>
          </div>
          <div className="h-10 w-px bg-panel" />
          <div className="text-center">
            <div className="text-3xl font-bold text-emerald-400">{correctCount}/{total}</div>
            <div className="mt-1 text-xs uppercase tracking-wider text-slate-500">Correct</div>
          </div>
        </div>

        <div className="mt-2 h-2 w-full max-w-sm overflow-hidden rounded-full bg-shell">
          <div className="h-full rounded-full bg-accent" style={{ width: `${scorePct}%` }} />
        </div>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button onClick={() => setShowReview(true)}
            className="flex items-center gap-2 rounded-lg border border-panel bg-panel/40 px-4 py-2 text-sm text-slate-300 hover:bg-panel">
            <ListChecks size={16} /> Review Answers
          </button>
          <button onClick={retry}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-shell hover:bg-orange-500">
            <RotateCcw size={16} /> Retry Quiz
          </button>
        </div>
      </div>
    )
  }

  const choice = answers[idx]
  const answeredThis = choice !== undefined
  const chosenCorrect = answeredThis && q.options[choice] === q.answer
  const correctIdx = q.options.findIndex((o) => o === q.answer)

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <p className="text-sm text-slate-400">Question {idx + 1} of {total}</p>
        </div>
        <button
          onClick={onRegenerate}
          disabled={generating}
          className="flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-sm font-semibold text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          <RefreshCw size={14} className={generating ? 'animate-spin' : ''} /> {generating ? 'Generating…' : 'Regenerate'}
        </button>
      </div>

      {/* progress bar */}
      <div className="h-1.5 overflow-hidden rounded-full bg-shell">
        <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${progress}%` }} />
      </div>

      {/* Question card */}
      <div key={idx} className={`rounded-2xl border border-panel bg-panel/60 p-6 shadow-lg shadow-black/20 ${direction === 'right' ? 'mcq-enter-right' : 'mcq-enter-left'}`}>
        <div className="mb-5 flex items-start gap-2">
          <span className="mt-0.5 shrink-0 rounded-lg bg-accent/15 px-2 py-1 text-xs font-bold text-accent">Q{idx + 1}</span>
          <p className="text-lg font-bold leading-relaxed text-white">{q.q}</p>
        </div>

        <div className="space-y-2.5">
          {q.options.map((opt, i) => {
            const isChosen = choice === i
            const isCorrect = opt === q.answer
            const showCorrect = answeredThis && isCorrect
            const showWrong = answeredThis && isChosen && !isCorrect
            return (
              <button
                key={i}
                onClick={() => pick(i)}
                disabled={submitted || answeredThis}
                className={`group flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all duration-150 hover:scale-[1.01] disabled:cursor-default ${
                  showCorrect
                    ? 'border-emerald-500 bg-emerald-500/10'
                    : showWrong
                      ? 'border-rose-500 bg-rose-500/10'
                      : isChosen
                        ? 'border-accent bg-accent/10'
                        : 'border-panel bg-shell/60 hover:border-accent/50 hover:bg-panel'
                }`}
              >
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                  showCorrect
                    ? 'bg-emerald-500 text-white'
                    : showWrong
                      ? 'bg-rose-500 text-white'
                      : isChosen
                        ? 'bg-accent text-shell'
                        : 'bg-panel text-slate-400 group-hover:text-accent'
                }`}>
                  {LETTERS[i]}
                </span>
                <span className={`flex-1 text-sm ${showWrong ? 'text-rose-200' : showCorrect ? 'text-emerald-200' : 'text-slate-200'}`}>
                  {opt}
                </span>
                <span className="ml-2 shrink-0">
                  {showCorrect && <Check size={18} className="text-emerald-400" />}
                  {showWrong && <X size={18} className="text-rose-400" />}
                </span>
              </button>
            )
          })}
        </div>

        {/* Explanation drawer */}
        <div className={`mcq-expand ${answeredThis ? 'mcq-expand-open' : ''}`}>
          <div className="mt-4 flex gap-2 rounded-xl border border-accent/30 bg-accent/10 p-3">
            <Lightbulb size={16} className="mt-0.5 shrink-0 text-accent" />
            <div className="text-sm text-slate-300">
              <span className="font-semibold text-accent">Explanation:</span>{' '}
              {q.explanation || `The correct answer is "${q.answer}".`}
            </div>
          </div>
        </div>

        {/* Bottom nav */}
        <div className="mt-6 flex items-center justify-between">
          <button
            onClick={() => go('left')}
            disabled={idx === 0}
            className="flex items-center gap-1 rounded-lg border border-panel px-3 py-2 text-sm text-slate-300 hover:bg-panel disabled:opacity-40"
          >
            <ChevronLeft size={16} /> Previous
          </button>
          {idx < total - 1 ? (
            <button
              onClick={() => go('right')}
              disabled={!answeredThis}
              className="flex items-center gap-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-shell hover:bg-orange-500 disabled:opacity-40"
            >
              Next <ChevronRight size={16} />
            </button>
          ) : (
            <button
              onClick={() => setSubmitted(true)}
              disabled={!answeredThis}
              className="flex items-center gap-1 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-40"
            >
              <Trophy size={16} /> Submit Quiz
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
