import type { PublicHotspot, PublicRoom } from '../types'

// Fallback plate for a room whose art has not landed (or failed).
const PLATES = ['#1b2230', '#2a1f1a', '#1d2622']

type Props = {
  room: PublicRoom
  index: number
  visited: Set<string>
  /** Show every hotspot at once — held Space, or the eye button. */
  reveal: boolean
  onOpen: (hotspot: PublicHotspot) => void
}

export default function RoomView({ room, index, visited, reveal, onOpen }: Props) {
  return (
    <div
      className="room-plate relative w-full overflow-hidden rounded-2xl border border-white/10"
      style={{ aspectRatio: '16 / 9', backgroundColor: PLATES[index % PLATES.length] }}
    >
      {room.image_url && (
        <img
          src={room.image_url}
          alt={room.name}
          className="absolute inset-0 h-full w-full object-cover"
        />
      )}

      <div className="absolute left-4 top-3 text-xs tracking-[0.3em] text-white/40 uppercase">
        {room.name}
      </div>

      {room.hotspots.map((hs) => {
        const npc = hs.kind === 'npc'
        const seen = visited.has(hs.id)

        // Nothing is drawn until the cursor is over it. The boxes are placed from
        // coordinates written before the art existed, so a permanently visible box
        // advertises every small misalignment; revealing on hover does not.
        // Written out in full rather than interpolated: Tailwind only compiles class
        // names it can see literally in the source.
        const revealed = npc
          ? 'border-amber-300/80 bg-amber-200/15'
          : 'border-sky-300/70 bg-sky-200/15'
        const onHover = npc
          ? 'hover:border-amber-300/80 hover:bg-amber-200/15'
          : 'hover:border-sky-300/70 hover:bg-sky-200/15'

        return (
          <button
            key={hs.id}
            onClick={() => onOpen(hs)}
            aria-label={hs.label}
            style={{
              left: `${hs.x * 100}%`,
              top: `${hs.y * 100}%`,
              width: `${hs.w * 100}%`,
              height: `${hs.h * 100}%`,
            }}
            className={`group absolute cursor-pointer rounded-lg border-2 transition-all
                        duration-150 ${onHover}
                        ${reveal ? revealed : 'border-transparent'}
                        ${seen ? 'opacity-80' : ''}`}
          >
            <span
              className={`pointer-events-none absolute -bottom-1 left-1/2 -translate-x-1/2
                          translate-y-full whitespace-nowrap rounded bg-black/85 px-2 py-0.5
                          text-[11px] text-neutral-200 transition-opacity duration-150
                          group-hover:opacity-100 ${reveal ? 'opacity-100' : 'opacity-0'}`}
            >
              {npc ? '🗣 ' : '🔍 '}
              {hs.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
