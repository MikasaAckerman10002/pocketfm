import type { SolveResponse } from '../types'

type Props = {
  result: SolveResponse
  personaName: string
  accent: string
  onNewCase: () => void
}

export default function EndingOverlay({ result, personaName, accent, onNewCase }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4">
      <div className="fade-up w-full max-w-xl rounded-2xl border border-white/10 bg-neutral-950 p-8 text-center shadow-2xl">
        <p
          className="text-xs tracking-[0.35em] uppercase"
          style={{ color: result.correct ? accent : '#b45f5f' }}
        >
          {result.correct ? 'Case closed' : 'Case cold'}
        </p>

        <p className="mt-5 text-left text-[15px] leading-relaxed whitespace-pre-wrap text-neutral-300">
          {result.narration}
        </p>

        <p className="mt-6 text-right text-xs text-neutral-600">— {personaName}</p>

        <button
          onClick={onNewCase}
          style={{ backgroundColor: accent }}
          className="mt-7 w-full cursor-pointer rounded-lg px-4 py-3 text-sm font-semibold text-black transition hover:brightness-110"
        >
          New case
        </button>
      </div>
    </div>
  )
}
