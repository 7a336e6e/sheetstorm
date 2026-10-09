import { afterEach, describe, expect, it, jest } from '@jest/globals'
import { cleanup, fireEvent, renderHook } from '@testing-library/react'
import { CHORD_TIMEOUT_MS, matchesChord, parseCombo, useHotkey } from './use-hotkeys'

afterEach(() => {
  cleanup()
  jest.useRealTimers()
})

const ev = (key: string, mods: Partial<Record<'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey', boolean>> = {}) => ({
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...mods,
})

describe('parseCombo', () => {
  it('parses modifiers, sequences and aliases', () => {
    expect(parseCombo('mod+k')).toEqual([
      { key: 'k', mod: true, ctrl: false, meta: false, alt: false, shift: false },
    ])
    expect(parseCombo('g i').map((c) => c.key)).toEqual(['g', 'i'])
    expect(parseCombo('shift+F10')[0]).toMatchObject({ key: 'f10', shift: true })
    expect(parseCombo('esc')[0].key).toBe('escape')
    expect(parseCombo('?')[0].key).toBe('?')
  })
})

describe('matchesChord', () => {
  const modK = parseCombo('mod+k')[0]
  const n = parseCombo('n')[0]
  const help = parseCombo('?')[0]

  it('mod accepts Ctrl or Cmd', () => {
    expect(matchesChord(ev('k', { ctrlKey: true }), modK)).toBe(true)
    expect(matchesChord(ev('k', { metaKey: true }), modK)).toBe(true)
    expect(matchesChord(ev('k'), modK)).toBe(false)
  })

  it('plain keys reject extra modifiers', () => {
    expect(matchesChord(ev('n'), n)).toBe(true)
    expect(matchesChord(ev('n', { ctrlKey: true }), n)).toBe(false)
    expect(matchesChord(ev('N', { shiftKey: true }), n)).toBe(false)
  })

  it('symbol keys tolerate the implied shift', () => {
    expect(matchesChord(ev('?', { shiftKey: true }), help)).toBe(true)
  })
})

describe('useHotkey', () => {
  it('fires on a single key and ignores typing in inputs', () => {
    const handler = jest.fn()
    renderHook(() => useHotkey('n', handler))
    fireEvent.keyDown(document, { key: 'n' })
    expect(handler).toHaveBeenCalledTimes(1)

    const input = document.createElement('input')
    document.body.appendChild(input)
    fireEvent.keyDown(input, { key: 'n' })
    expect(handler).toHaveBeenCalledTimes(1)
    input.remove()
  })

  it('mod combos fire inside inputs', () => {
    const handler = jest.fn()
    renderHook(() => useHotkey('mod+k', handler))
    const input = document.createElement('input')
    document.body.appendChild(input)
    fireEvent.keyDown(input, { key: 'k', metaKey: true })
    expect(handler).toHaveBeenCalledTimes(1)
    input.remove()
  })

  it('handles sequences with a timeout', () => {
    jest.useFakeTimers()
    const handler = jest.fn()
    renderHook(() => useHotkey('g i', handler))
    fireEvent.keyDown(document, { key: 'g' })
    fireEvent.keyDown(document, { key: 'i' })
    expect(handler).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: 'g' })
    jest.advanceTimersByTime(CHORD_TIMEOUT_MS + 1)
    fireEvent.keyDown(document, { key: 'i' })
    expect(handler).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(document, { key: 'x' })
    fireEvent.keyDown(document, { key: 'g' })
    fireEvent.keyDown(document, { key: 'i' })
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it('respects enabled=false and handled events', () => {
    const handler = jest.fn()
    const { rerender } = renderHook(({ enabled }) => useHotkey('n', handler, { enabled }), {
      initialProps: { enabled: false },
    })
    fireEvent.keyDown(document, { key: 'n' })
    expect(handler).not.toHaveBeenCalled()
    rerender({ enabled: true })
    const prevented = new KeyboardEvent('keydown', { key: 'n', cancelable: true, bubbles: true })
    prevented.preventDefault()
    document.dispatchEvent(prevented)
    expect(handler).not.toHaveBeenCalled()
  })
})
