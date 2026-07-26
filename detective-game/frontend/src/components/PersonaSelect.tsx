import type { PublicPersona } from '../types'

type Props = {
  personas: PublicPersona[]
  busy: boolean
  onPick: (id: string) => void
}

export default function PersonaSelect({ personas, busy, onPick }: Props) {
  return (
    <div className="min-h-full flex flex-col items-center justify-center p-8">
      <p className="text-xs tracking-[0.35em] text-neutral-500 uppercase">
        An infinite mystery engine
      </p>
      <h1 className="mt-3 text-5xl font-semibold tracking-tight text-neutral-100">
        Choose your host
      </h1>
      <p className="mt-3 max-w-lg text-center text-sm text-neutral-400">
        The case is generated fresh either way. The host decides how it feels.
      </p>

      <div className="mt-10 grid w-full max-w-5xl gap-5 md:grid-cols-3">
        {personas.map((p) => (
          <button
            key={p.id}
            disabled={busy}
            onClick={() => onPick(p.id)}
            style={{ borderColor: `${p.accent_color}55` }}
            className="group cursor-pointer rounded-2xl border bg-neutral-900/60 p-6 text-left transition
                       hover:-translate-y-1 hover:bg-neutral-900 disabled:cursor-wait disabled:opacity-50"
          >
            <div
              className="h-28 rounded-xl border border-white/5"
              style={{
                background: `radial-gradient(120% 100% at 30% 0%, ${p.accent_color}44, transparent 70%), #12141b`,
              }}
            />
            <h2
              className="mt-4 text-lg font-semibold"
              style={{ color: p.accent_color }}
            >
              {p.name}
            </h2>
            <p className="mt-1 text-sm text-neutral-400">{p.tagline}</p>
            <p className="mt-3 text-xs leading-relaxed text-neutral-600 italic">
              {p.visual_style}
            </p>
            <span className="mt-4 inline-block text-xs font-medium tracking-wide text-neutral-500 group-hover:text-neutral-300">
              {busy ? 'Opening the file…' : 'Start a case →'}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
