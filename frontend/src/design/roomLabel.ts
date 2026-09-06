import { ROOM_LABELS } from './roomTypes'

/** Shared by the legacy `SketchSvg` rendering path and the new `ArchitecturalFloorPlan` so a room
 * type's display label/numbering logic exists in exactly one place. */
export function roomLabel(type: string, indexAmongSameType: number, countOfSameType: number): string {
  const base = ROOM_LABELS[type] ?? type
  return countOfSameType > 1 ? `${base} ${indexAmongSameType + 1}` : base
}
