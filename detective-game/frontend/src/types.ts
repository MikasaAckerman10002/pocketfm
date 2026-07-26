// Mirrors the public Pydantic models in backend/app/models.py.
// If a field does not exist here, the player is not supposed to know it.

export type PublicPersona = {
  id: string
  name: string
  tagline: string
  visual_style: string
  accent_color: string
}

export type PublicHotspot = {
  id: string
  kind: 'npc' | 'object'
  label: string
  x: number
  y: number
  w: number
  h: number
}

export type PublicRoom = {
  id: string
  name: string
  image_url: string | null
  locked: boolean
  hotspots: PublicHotspot[]
}

export type PublicClue = { id: string; name: string; text: string }

export type AccusationOptions = {
  suspects: string[]
  motives: string[]
  weapons: string[]
}

export type PublicView = {
  case_id: string
  title: string
  setting: string
  victim: string
  public_setup: string
  persona: PublicPersona
  rooms: PublicRoom[]
  current_room: string
  discovered_clues: PublicClue[]
  npc_trust: Record<string, number>
  accusation_options: AccusationOptions
  solved: boolean
  images_pending: boolean
}

export type NewCaseResponse = {
  session_id: string
  view: PublicView
  intro: string
}

export type AskResponse = {
  speaker: string
  reply: string
  clue_unlocked: PublicClue | null
  trust_delta: number
  persona_reaction: string | null
  room_unlocked: string | null
  view: PublicView
}

export type SolveResponse = {
  correct: boolean
  narration: string
  truth: { killer: string; motive: string; weapon: string }
}

export type Message = { role: 'player' | 'them'; text: string }
