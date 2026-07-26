import { speak } from './api'

// One line speaks at a time. Without this, a persona reaction lands on top of the NPC
// reply that triggered it and you hear two voices at once.
let current: HTMLAudioElement | null = null
let enabled = true

// Browsers only allow audio.play() synchronously inside a user-gesture handler.
// After any await (e.g. a fetch) the gesture is considered "stale" and play() is
// silently blocked. Calling unlock() synchronously in the click handler (before the
// fetch) creates and immediately pauses a silent Audio element, which marks the page
// as having had a gesture. The real play() that follows the await then succeeds.
export function unlock() {
  if (!enabled) return
  const a = new Audio()
  a.play().catch(() => {})
  a.pause()
}

export function setEnabled(value: boolean) {
  enabled = value
  if (!value) stop()
}

export function stop() {
  current?.pause()
  current = null
}

export async function say(
  sessionId: string,
  text: string,
  speaker: 'persona' | 'npc' = 'persona',
  npcName?: string,
) {
  if (!enabled || !text.trim()) return
  try {
    const { audio_url } = await speak(sessionId, text, speaker, npcName)
    // Re-check: the player may have muted while synthesis was in flight.
    if (!audio_url || !enabled) return
    stop()
    current = new Audio(audio_url)
    // Autoplay is only permitted after a user gesture; every line here follows a
    // click, but a rejected promise must not surface as an unhandled error.
    current.play().catch((e) => console.warn('[speech] play() blocked:', e))
  } catch (e) {
    console.warn('[speech] say() failed:', e)
  }
}
