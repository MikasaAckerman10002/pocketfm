import { useState } from 'react'
import type { AccusationOptions } from '../types'

type Props = {
  options: AccusationOptions
  accent: string
  busy: boolean
  onSubmit: (suspect: string, motive: string, weapon: string) => void
  onClose: () => void
}

function Choice({
  label,
  values,
  picked,
  onPick,
  accent,
}: {
  label: string
  values: string[]
  picked: string | null
  onPick: (v: string) => void
  accent: string
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs tracking-[0.2em] text-neutral-500 uppercase">
        {label}
      </legend>
      <div className="space-y-1.5">
        {values.map((v) => (
          <button
            key={v}
            onClick={() => onPick(v)}
            style={picked === v ? { borderColor: accent, background: `${accent}22` } : undefined}
            className="block w-full cursor-pointer rounded-lg border border-white/10 px-3 py-2
                       text-left text-sm text-neutral-300 transition hover:bg-white/5"
          >
            {v}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export default function SolveModal({ options, accent, busy, onSubmit, onClose }: Props) {
  const [suspect, setSuspect] = useState<string | null>(null)
  const [motive, setMotive] = useState<string | null>(null)
  const [weapon, setWeapon] = useState<string | null>(null)
  const ready = suspect && motive && weapon

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4">
      <div className="fade-up flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl border border-white/10 bg-neutral-950 shadow-2xl">
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div>
            <h2 className="text-xl font-semibold text-neutral-100">Make the accusation</h2>
            <p className="text-sm text-neutral-500">You only get one shot at this.</p>
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded px-2 py-1 text-sm text-neutral-500 hover:bg-white/5 hover:text-neutral-200"
          >
            Not yet
          </button>
        </header>

        <div className="grid flex-1 gap-6 overflow-y-auto p-6 md:grid-cols-3">
          <Choice label="Who" values={options.suspects} picked={suspect} onPick={setSuspect} accent={accent} />
          <Choice label="Why" values={options.motives} picked={motive} onPick={setMotive} accent={accent} />
          <Choice label="How" values={options.weapons} picked={weapon} onPick={setWeapon} accent={accent} />
        </div>

        <footer className="border-t border-white/10 p-4">
          <button
            disabled={!ready || busy}
            onClick={() => ready && onSubmit(suspect, motive, weapon)}
            style={{ backgroundColor: ready ? accent : undefined }}
            className="w-full cursor-pointer rounded-lg px-4 py-3 text-sm font-semibold text-black transition
                       hover:brightness-110 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-600"
          >
            {busy ? 'Making the case…' : ready ? 'Name them' : 'Pick who, why, and how'}
          </button>
        </footer>
      </div>
    </div>
  )
}
