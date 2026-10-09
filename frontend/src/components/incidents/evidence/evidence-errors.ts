/**
 * Evidence-specific rejections that belong next to the form that caused them
 * (the dialog stays open so the user can fix the input). Anything else goes
 * through `notifyError`.
 *
 * Server codes (backend `evidence.py` / `custody_ledger.py`):
 *   400 recipient_no_access        the picked user cannot open this incident
 *   400 bad_request                validation (message names the field)
 *   409 legal_hold                 refused while a hold is in force
 *   409 invalid_custody_transition the item is not in a state that allows it
 *   409 no_reference_hash          nothing recorded to verify against
 *   410 gone                       recompute of a tombstoned (purged) file
 */
import { isApiError } from '@/lib/api'
import { notifyError } from '@/lib/errors'

export function evidenceFormError(err: unknown): string | null {
  if (!isApiError(err)) return null
  const message = err.message && err.message !== err.code ? err.message : undefined
  switch (err.code) {
    case 'recipient_no_access':
      return `${message ?? 'That user cannot access this incident.'} Add them to the incident first, or choose someone else.`
    case 'legal_hold':
      return `${message ?? 'This item is under legal hold.'} Release the hold first.`
    case 'invalid_custody_transition':
      return `${message ?? 'This item is not in a state that allows that.'} It may have just changed; close this dialog and review its current state.`
    case 'no_reference_hash':
      return message ?? 'There is no recorded hash of that type to compare against.'
    case 'bad_request':
    case 'validation_error':
      return message ?? 'The request was rejected.'
    default:
      break
  }
  if (err.status === 410) {
    return 'That file was deleted and its stored content was purged, so it cannot be recomputed.'
  }
  return null
}

/** Show the rejection inline when it is one of ours, otherwise toast it. */
export function reportEvidenceError(err: unknown, action: string, setInline: (message: string | null) => void): void {
  const inline = evidenceFormError(err)
  if (inline) setInline(inline)
  else notifyError(err, action)
}
