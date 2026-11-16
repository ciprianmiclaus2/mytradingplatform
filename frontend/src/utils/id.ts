/**
 * Unique pane id. Also used as the backend strategy `instance_id`, so it only
 * contains letters, digits and '-' and is at most 64 characters.
 */
export function newPaneId(): string {
  const uuid =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
  return `pane-${uuid}`
}

/** Unique tab-group (grid tile) id. */
export function newGroupId(): string {
  return newPaneId().replace(/^pane-/, 'group-')
}
