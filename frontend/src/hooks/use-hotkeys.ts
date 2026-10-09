"use client"

/**
 * Keyboard shortcuts.
 *
 *   useHotkey('mod+k', openPalette)   // mod = Cmd or Ctrl
 *   useHotkey('g i', goToIncidents)   // sequence: g then i within 1s
 *   useHotkey('n', createItem)
 *   useHotkey('?', showHelp)
 *
 * Events from inputs, textareas, selects and contenteditable elements are
 * ignored, except for combos with a `mod`/`ctrl`/`meta` modifier (so `mod+k`
 * works while typing). Events already handled (`defaultPrevented`) and key
 * auto-repeat are ignored too.
 */
import { useEffect, useRef } from 'react'

export interface Chord {
  key: string
  mod: boolean
  ctrl: boolean
  meta: boolean
  alt: boolean
  shift: boolean
}

export const CHORD_TIMEOUT_MS = 1000

const KEY_ALIASES: Record<string, string> = {
  esc: 'escape',
  space: ' ',
  del: 'delete',
  up: 'arrowup',
  down: 'arrowdown',
  left: 'arrowleft',
  right: 'arrowright',
  plus: '+',
}

/** Parse 'mod+shift+k' or a space-separated sequence 'g i' into chords. */
export function parseCombo(combo: string): Chord[] {
  return combo
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const tokens = part.toLowerCase().split('+')
      // A trailing '+' (e.g. 'shift++') leaves an empty token for the '+' key.
      const rawKey = tokens.pop() || '+'
      const chord: Chord = {
        key: KEY_ALIASES[rawKey] ?? rawKey,
        mod: false,
        ctrl: false,
        meta: false,
        alt: false,
        shift: false,
      }
      tokens.forEach((t) => {
        if (t === 'mod') chord.mod = true
        else if (t === 'ctrl' || t === 'control') chord.ctrl = true
        else if (t === 'meta' || t === 'cmd') chord.meta = true
        else if (t === 'alt' || t === 'option') chord.alt = true
        else if (t === 'shift') chord.shift = true
      })
      return chord
    })
}

type KeyLike = Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>

/** Does a keyboard event satisfy one chord? */
export function matchesChord(e: KeyLike, chord: Chord): boolean {
  const key = (e.key || '').toLowerCase()
  if (key !== chord.key) return false
  if (chord.mod) {
    if (!(e.ctrlKey || e.metaKey)) return false
  } else {
    if (e.ctrlKey !== chord.ctrl || e.metaKey !== chord.meta) return false
  }
  if (e.altKey !== chord.alt) return false
  // Shift is implied by symbol keys like '?', so it is only enforced when the
  // combo asks for it, or for letters (so Shift+N does not trigger 'n').
  if (chord.shift && !e.shiftKey) return false
  if (!chord.shift && /^[a-z]$/.test(chord.key) && e.shiftKey) return false
  return true
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== 'string') return false
  const el = target as HTMLElement
  const tag = el.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  return el.isContentEditable || el.getAttribute?.('contenteditable') === 'true'
}

export interface HotkeyOptions {
  enabled?: boolean
}

export function useHotkey(
  combo: string,
  handler: (e: KeyboardEvent) => void,
  opts: HotkeyOptions = {}
): void {
  const enabled = opts.enabled ?? true
  const handlerRef = useRef(handler)
  useEffect(() => {
    handlerRef.current = handler
  }, [handler])

  useEffect(() => {
    if (!enabled) return
    const chords = parseCombo(combo)
    if (chords.length === 0) return
    const allowInInputs = chords.every((c) => c.mod || c.ctrl || c.meta)
    let step = 0
    let lastAt = 0

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.repeat) return
      if (!allowInInputs && isEditableTarget(e.target)) return
      // Bare modifier presses don't advance or reset a sequence.
      if (['shift', 'control', 'alt', 'meta'].includes((e.key || '').toLowerCase())) return

      const now = Date.now()
      if (step > 0 && now - lastAt > CHORD_TIMEOUT_MS) step = 0

      if (matchesChord(e, chords[step])) {
        step += 1
        lastAt = now
        if (step === chords.length) {
          step = 0
          e.preventDefault()
          handlerRef.current(e)
        }
      } else {
        step = matchesChord(e, chords[0]) ? 1 : 0
        lastAt = now
        if (step === chords.length) {
          step = 0
          e.preventDefault()
          handlerRef.current(e)
        }
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [combo, enabled])
}
