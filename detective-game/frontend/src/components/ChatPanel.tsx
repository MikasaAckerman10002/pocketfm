import { useEffect, useRef, useState } from 'react'
import * as speech from '../speech'
import type { Message, PublicHotspot } from '../types'

type Props = {
  hotspot: PublicHotspot
  messages: Message[]
  busy: boolean
  accent: string
  onAsk: (question: string) => void
  onClose: () => void
}

export default function ChatPanel({
  hotspot,
  messages,
  busy,
  accent,
  onAsk,
  onClose,
}: Props) {
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, busy])

  const isNpc = hotspot.kind === 'npc'

  useEffect(() => {
    if (isNpc) inputRef.current?.focus()
  }, [hotspot.id, isNpc])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = text.trim()
    if (!q || busy) return
    // Unlock the audio context synchronously while still inside the gesture handler,
    // so the play() call that follows the async API round-trip is not blocked.
    speech.unlock()
    setText('')
    onAsk(q)
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={onClose}
    >
      <div
        className={`fade-up flex w-full max-w-2xl flex-col rounded-2xl border border-white/10
                    bg-neutral-950 shadow-2xl ${isNpc ? 'h-[32rem]' : 'max-h-[28rem]'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <h3 className="font-semibold text-neutral-100">{hotspot.label}</h3>
            <p className="text-xs text-neutral-500">
              {isNpc ? 'Ask anything — no dialogue tree' : 'You take a closer look'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded px-2 py-1 text-sm text-neutral-500 hover:bg-white/5 hover:text-neutral-200"
          >
            Close
          </button>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {messages.length === 0 && !busy && isNpc && (
            <p className="pt-10 text-center text-sm text-neutral-600">
              {hotspot.label} waits for you to say something.
            </p>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={`fade-up flex ${m.role === 'player' ? 'justify-end' : 'justify-start'}`}
            >
              <p
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                  m.role === 'player'
                    ? 'bg-neutral-700 text-neutral-100'
                    : 'bg-neutral-900 text-neutral-300'
                }`}
                style={
                  m.role === 'them' && !isNpc
                    ? { borderLeft: `2px solid ${accent}`, fontStyle: 'italic' }
                    : undefined
                }
              >
                {m.text}
              </p>
            </div>
          ))}

          {busy && (
            <p className="text-sm text-neutral-600 italic">
              {isNpc ? 'thinking…' : 'looking…'}
            </p>
          )}
          <div ref={endRef} />
        </div>

        {/* Only people are worth questioning. An object has already said everything it
            has to say by the time this panel opened, so it gets no input box. */}
        {isNpc ? (
          <form onSubmit={submit} className="flex gap-2 border-t border-white/10 p-3">
            <input
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask them anything…"
              className="flex-1 rounded-lg border border-white/10 bg-neutral-900 px-3 py-2 text-sm
                         text-neutral-100 outline-none placeholder:text-neutral-600 focus:border-white/25"
            />
            <button
              type="submit"
              disabled={busy}
              style={{ backgroundColor: accent }}
              className="cursor-pointer rounded-lg px-4 py-2 text-sm font-medium text-black transition
                         hover:brightness-110 disabled:cursor-wait disabled:opacity-50"
            >
              Ask
            </button>
          </form>
        ) : (
          <div className="border-t border-white/10 p-3">
            <button
              onClick={onClose}
              disabled={busy}
              className="w-full cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm
                         text-neutral-300 transition hover:bg-white/5 disabled:cursor-wait
                         disabled:opacity-50"
            >
              {busy ? 'Looking…' : 'Done'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
