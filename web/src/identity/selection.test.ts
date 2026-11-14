import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getSelectedFieldId, setSelectedFieldId, subscribeToSelection } from './selection'

describe('selection store', () => {
  beforeEach(() => {
    setSelectedFieldId(null)
  })

  it('starts with nothing selected', () => {
    expect(getSelectedFieldId()).toBe(null)
  })

  it('stores the selected field id and clears it with null', () => {
    setSelectedFieldId('example-field-1')
    expect(getSelectedFieldId()).toBe('example-field-1')
    setSelectedFieldId(null)
    expect(getSelectedFieldId()).toBe(null)
  })

  it('notifies every subscriber on change and stops on unsubscribe', () => {
    const first = vi.fn()
    const second = vi.fn()
    const unsubscribeFirst = subscribeToSelection(first)
    subscribeToSelection(second)

    setSelectedFieldId('example-field-2')
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    unsubscribeFirst()
    setSelectedFieldId(null)
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(2)
  })
})
