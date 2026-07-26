import { useEffect, useState } from 'react'

// Case generation takes 13-16s. Phase 3 extends this screen with real per-room image
// progress; for now the rotating lines keep the wait from reading as a hang.
const LINES = [
  'Finding a body…',
  'Deciding who did it…',
  'Hiding the evidence…',
  'Briefing the witnesses…',
  'Getting their stories straight…',
  'Setting the scene…',
  'Painting the first room…',
]

export default function LoadingScreen({ accent }: { accent: string }) {
  const [i, setI] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % LINES.length), 2400)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6">
      <div
        className="h-10 w-10 animate-spin rounded-full border-2 border-white/10"
        style={{ borderTopColor: accent }}
      />
      <p key={i} className="fade-up text-sm tracking-wide text-neutral-400">
        {LINES[i]}
      </p>
      <p className="text-xs text-neutral-700">
        Writing the case, then painting room one. The other rooms finish while you play.
      </p>
    </div>
  )
}
