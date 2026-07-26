import { useEffect, useState } from 'react'
import * as api from './api'
import ChatPanel from './components/ChatPanel'
import EndingOverlay from './components/EndingOverlay'
import LoadingScreen from './components/LoadingScreen'
import PersonaSelect from './components/PersonaSelect'
import RoomView from './components/RoomView'
import Sidebar from './components/Sidebar'
import SolveModal from './components/SolveModal'
import * as speech from './speech'
import type {
  Message,
  PublicHotspot,
  PublicPersona,
  PublicView,
  SolveResponse,
} from './types'

export default function App() {
  const [personas, setPersonas] = useState<PublicPersona[]>([])
  const [pendingPersona, setPendingPersona] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [view, setView] = useState<PublicView | null>(null)
  const [narration, setNarration] = useState<string[]>([])

  const [active, setActive] = useState<PublicHotspot | null>(null)
  // Transcripts are presentational only — the server holds the authoritative log.
  const [transcripts, setTranscripts] = useState<Record<string, Message[]>>({})
  const [visited, setVisited] = useState<Set<string>>(new Set())

  const [solveOpen, setSolveOpen] = useState(false)
  const [ending, setEnding] = useState<SolveResponse | null>(null)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [muted, setMuted] = useState(false)
  // Hotspots are invisible until hovered. Holding Space (or the eye button) shows them
  // all, so a player who cannot find the next lead is never stuck sweeping the mouse.
  const [revealHeld, setRevealHeld] = useState(false)
  const [revealPinned, setRevealPinned] = useState(false)

  useEffect(() => {
    api
      .getPersonas()
      .then(setPersonas)
      .catch((e) => setError((e as Error).message))
  }, [])

  // Rooms beyond the first finish generating after the game has already started.
  // Poll until they land, then stop — the flag comes from the server, so this ends
  // on its own rather than running for the life of the session.
  useEffect(() => {
    if (!sessionId || !view?.images_pending) return
    const t = setInterval(async () => {
      try {
        const res = await api.getSession(sessionId)
        setView(res.view)
      } catch {
        /* transient; the next tick retries */
      }
    }, 3000)
    return () => clearInterval(t)
  }, [sessionId, view?.images_pending])

  useEffect(() => {
    const typing = (t: EventTarget | null) =>
      t instanceof HTMLElement &&
      (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)

    const down = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || typing(e.target)) return
      e.preventDefault() // otherwise Space scrolls the page
      setRevealHeld(true)
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space') setRevealHeld(false)
    }
    // Releasing Space after tabbing away never fires keyup, leaving it stuck on.
    const blur = () => setRevealHeld(false)

    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
    }
  }, [])

  const reset = () => {
    speech.stop()
    setSessionId(null)
    setView(null)
    setNarration([])
    setActive(null)
    setTranscripts({})
    setVisited(new Set())
    setSolveOpen(false)
    setEnding(null)
  }

  async function startCase(personaId: string) {
    // Unlock the audio context now, while we're still inside the click gesture.
    // api.newCase() is async; by the time it resolves the gesture is stale and
    // audio.play() would be silently blocked without this priming call.
    speech.unlock()
    setPendingPersona(personaId)
    setBusy(true)
    setError(null)
    try {
      const res = await api.newCase(personaId)
      reset()
      setSessionId(res.session_id)
      setView(res.view)
      setNarration([res.intro])
      speech.say(res.session_id, res.intro, 'persona')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function goToRoom(roomId: string) {
    if (!sessionId) return
    try {
      const res = await api.enterRoom(sessionId, roomId)
      setView(res.view)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  /** Open a hotspot. Objects narrate themselves; only people are worth questioning. */
  async function openHotspot(hs: PublicHotspot) {
    setActive(hs)
    if (hs.kind === 'object' && !(transcripts[hs.id]?.length)) {
      await runTurn(hs, 'The detective examines this closely.', false)
    }
  }

  /**
   * One exchange with a hotspot. `record` is false for object examinations: the
   * player never typed anything, so showing a question they did not ask would be a
   * lie about what happened.
   */
  async function runTurn(hs: PublicHotspot, question: string, record: boolean) {
    if (!sessionId) return
    const hotspotId = hs.id
    if (record) {
      setTranscripts((t) => ({
        ...t,
        [hotspotId]: [...(t[hotspotId] ?? []), { role: 'player', text: question }],
      }))
    }
    setBusy(true)
    try {
      const res = await api.askHotspot(sessionId, hotspotId, question)
      setTranscripts((t) => ({
        ...t,
        [hotspotId]: [...(t[hotspotId] ?? []), { role: 'them', text: res.reply }],
      }))
      setView(res.view)
      setVisited((v) => new Set(v).add(hotspotId))

      // The NPC speaks in their own voice; an object examination is the host talking.
      if (hs.kind === 'npc') {
        speech.say(sessionId, res.reply, 'npc', hs.label)
      } else {
        speech.say(sessionId, res.reply, 'persona')
      }

      if (res.persona_reaction) {
        const reaction = res.persona_reaction
        setNarration((n) => [...n, reaction])
      }
      if (res.room_unlocked) {
        const room = res.view.rooms.find((r) => r.id === res.room_unlocked)
        if (room) setNarration((n) => [...n, `— ${room.name} is open to you now.`])
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const ask = (question: string) => {
    if (active) void runTurn(active, question, true)
  }

  async function accuse(suspect: string, motive: string, weapon: string) {
    if (!sessionId) return
    setBusy(true)
    try {
      const res = await api.solveCase(sessionId, suspect, motive, weapon)
      setSolveOpen(false)
      setEnding(res)
      speech.say(sessionId, res.narration, 'persona')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !view) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-neutral-300">{error}</p>
        <p className="text-sm text-neutral-600">Is the backend running on port 8000?</p>
      </div>
    )
  }

  if (!view || !sessionId) {
    const accent = personas.find((p) => p.id === pendingPersona)?.accent_color ?? '#e8e4dc'
    return busy ? (
      <LoadingScreen accent={accent} />
    ) : (
      <PersonaSelect personas={personas} busy={busy} onPick={startCase} />
    )
  }

  const room = view.rooms.find((r) => r.id === view.current_room)
  const roomIndex = view.rooms.findIndex((r) => r.id === view.current_room)
  const accent = view.persona.accent_color

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold text-neutral-100">{view.title}</h1>
          <p className="truncate text-xs text-neutral-500">{view.victim}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRevealPinned((v) => !v)}
            title="Show every hotspot (or hold Space)"
            aria-label="Show every hotspot"
            aria-pressed={revealPinned}
            className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition
              ${
                revealPinned
                  ? 'border-amber-300/40 bg-amber-200/10 text-amber-200'
                  : 'border-white/15 text-neutral-400 hover:bg-white/5 hover:text-neutral-200'
              }`}
          >
            {revealPinned ? '👁' : '👁‍🗨'}
          </button>
          <button
            onClick={() => {
              const next = !muted
              setMuted(next)
              speech.setEnabled(!next)
            }}
            title={muted ? 'Unmute narration' : 'Mute narration'}
            aria-label={muted ? 'Unmute narration' : 'Mute narration'}
            className="cursor-pointer rounded-lg border border-white/15 px-3 py-2 text-sm text-neutral-400 transition hover:bg-white/5 hover:text-neutral-200"
          >
            {muted ? '🔇' : '🔊'}
          </button>
          <button
            onClick={() => setSolveOpen(true)}
            style={{ borderColor: accent, color: accent }}
            className="cursor-pointer rounded-lg border px-4 py-2 text-sm font-medium transition hover:bg-white/5"
          >
            Solve case
          </button>
          <button
            onClick={reset}
            className="cursor-pointer rounded-lg border border-white/15 px-4 py-2 text-sm text-neutral-400 transition hover:bg-white/5 hover:text-neutral-200"
          >
            New case
          </button>
        </div>
      </header>

      {error && (
        <p className="border-b border-red-500/20 bg-red-950/40 px-5 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4 lg:flex-row lg:overflow-hidden">
        <main className="flex min-w-0 flex-1 flex-col gap-3">
          <nav className="flex flex-wrap gap-2">
            {view.rooms.map((r) => (
              <button
                key={r.id}
                disabled={r.locked}
                onClick={() => goToRoom(r.id)}
                style={
                  r.id === view.current_room ? { borderColor: accent, color: accent } : undefined
                }
                className="cursor-pointer rounded-lg border border-white/10 px-3 py-1.5 text-sm text-neutral-400
                           transition hover:bg-white/5 disabled:cursor-not-allowed disabled:text-neutral-700"
              >
                {r.locked ? '🔒 ' : ''}
                {r.name}
              </button>
            ))}
          </nav>

          {room && (
            <RoomView
              room={room}
              index={roomIndex}
              visited={visited}
              reveal={revealHeld || revealPinned}
              onOpen={openHotspot}
            />
          )}

          <p className="text-xs leading-relaxed text-neutral-600">
            {view.images_pending && (
              <span className="mr-2 text-neutral-500 italic">
                Still painting the other rooms…
              </span>
            )}
            {view.public_setup}
            <span className="mt-1 block text-neutral-700">
              Move the cursor over the scene to find people and objects — hold{' '}
              <kbd className="rounded border border-white/15 px-1 text-[10px]">Space</kbd>{' '}
              to show them all.
            </span>
          </p>
        </main>

        <Sidebar persona={view.persona} narration={narration} clues={view.discovered_clues} />
      </div>

      {active && (
        <ChatPanel
          hotspot={active}
          messages={transcripts[active.id] ?? []}
          busy={busy}
          accent={accent}
          onAsk={ask}
          onClose={() => setActive(null)}
        />
      )}

      {solveOpen && (
        <SolveModal
          options={view.accusation_options}
          accent={accent}
          busy={busy}
          onSubmit={accuse}
          onClose={() => setSolveOpen(false)}
        />
      )}

      {ending && (
        <EndingOverlay
          result={ending}
          personaName={view.persona.name}
          accent={accent}
          onNewCase={reset}
        />
      )}
    </div>
  )
}
