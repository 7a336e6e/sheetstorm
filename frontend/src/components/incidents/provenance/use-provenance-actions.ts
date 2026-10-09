"use client"

import { useCallback } from 'react'
import { ShieldCheck, ShieldOff } from 'lucide-react'
import type { RowAction } from '@/components/ui/data-table'
import { usePermissionCheck } from '@/components/auth/permission-gate'
import { provenanceApi } from '@/lib/endpoints/provenance'
import { notifyError, notifySuccess } from '@/lib/errors'
import { useAuthStore } from '@/lib/store'
import type { ProvenanceFields, ProvenanceRecordKind } from '@/types'
import { KIND_UPDATE_PERMISSION } from './provenance-form'

type VerifiableRow = ProvenanceFields & { id: string; version?: number; creator?: { id: string } | null }

/**
 * Row-menu entries "Verify provenance" / "Withdraw verification" for a table
 * of events or IOCs. The server enforces the rules (a different analyst than
 * the creator; only the verifier or an organization manager may withdraw);
 * the menu just hides what cannot succeed.
 */
export function useProvenanceRowActions(
  incidentId: string,
  kind: ProvenanceRecordKind,
  onChanged: () => void,
): (row: VerifiableRow) => RowAction[] {
  const userId = useAuthStore((s) => s.user?.id)
  const can = usePermissionCheck()
  const permission = KIND_UPDATE_PERMISSION[kind]

  return useCallback(
    (row) => {
      const level = row.provenance_level ?? 'none'
      if (level === 'none') return []
      if (level === 'verified') {
        const mayWithdraw = row.provenance_verifier?.id === userId || can('organizations:manage')
        if (!mayWithdraw) return []
        return [{
          label: 'Withdraw verification',
          icon: ShieldOff,
          permission,
          onSelect: () => {
            provenanceApi.unverify(incidentId, kind, row.id, row.version)
              .then(() => {
                notifySuccess('Verification withdrawn')
                onChanged()
              })
              .catch((err) => notifyError(err, 'withdraw the verification'))
          },
        }]
      }
      if (row.creator?.id && row.creator.id === userId) return []
      return [{
        label: 'Verify provenance',
        icon: ShieldCheck,
        permission,
        onSelect: () => {
          provenanceApi.verify(incidentId, kind, row.id, row.version)
            .then(() => {
              notifySuccess('Provenance verified')
              onChanged()
            })
            .catch((err) => notifyError(err, 'verify the provenance'))
        },
      }]
    },
    [incidentId, kind, onChanged, userId, can, permission],
  )
}
