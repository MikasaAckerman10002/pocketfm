import type { PublicClue, PublicPersona } from '../types'

type Props = {
  persona: PublicPersona
  narration: string[]
  clues: PublicClue[]
}

export default function Sidebar({ persona, narration, clues }: Props) {
  return (
    <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-80">
      <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-white/10 bg-neutral-900/50">
        <h2
          className="border-b border-white/10 px-4 py-2.5 text-xs tracking-[0.2em] uppercase"
          style={{ color: persona.accent_color }}
        >
          {persona.name}
        </h2>
        <div className="min-h-24 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {narration.map((line, i) => (
            <p
              key={i}
              className="fade-up text-sm leading-relaxed whitespace-pre-wrap text-neutral-400 italic"
            >
              {line}
            </p>
          ))}
        </div>
      </section>

      <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-white/10 bg-neutral-900/50">
        <h2 className="flex items-center justify-between border-b border-white/10 px-4 py-2.5 text-xs tracking-[0.2em] text-neutral-400 uppercase">
          Case file
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[11px] tracking-normal text-neutral-300">
            {clues.length}
          </span>
        </h2>
        <div className="min-h-24 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {clues.length === 0 && (
            <p className="text-sm text-neutral-600">
              Nothing yet. Talk to someone, or look closer at something.
            </p>
          )}
          {clues.map((c) => (
            <article
              key={c.id}
              className="fade-up rounded-lg border border-white/10 bg-black/30 p-3"
            >
              <h3 className="text-sm font-semibold text-amber-200/90">{c.name}</h3>
              <p className="mt-1 text-xs leading-relaxed text-neutral-400">{c.text}</p>
            </article>
          ))}
        </div>
      </section>
    </aside>
  )
}
