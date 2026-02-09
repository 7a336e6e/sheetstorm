import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Fingerprint } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function HostIndicatorNode({ data, selected }: NodeProps<GraphNode>) {
  const d = data as GraphNodeData
  const { resolvedTheme } = useTheme()

  const isMalicious = !!(d.extra_data?.is_malicious)
  const isRemediated = !!(d.extra_data?.remediated)
  const artifactType = d.extra_data?.artifact_type
    ? String(d.extra_data.artifact_type)
    : null

  const statusColor = isRemediated
    ? 'bg-green-500'
    : isMalicious
      ? 'bg-red-500'
      : 'bg-orange-500'

  return (
    <div
      className={`relative w-[160px] bg-card rounded-lg shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : 'border-amber-500/30'
        }`}
    >
      {/* Amber gradient header strip */}
      <div className="h-1 rounded-t-lg bg-gradient-to-r from-amber-600 to-amber-400" />

      <div className="p-3">
        {/* Icon + status row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Fingerprint className="w-4 h-4 text-amber-400" />
            <span className="text-[10px] text-amber-400/80 uppercase tracking-wider font-semibold">
              {artifactType?.replace('_', ' ') || 'Indicator'}
            </span>
          </div>
          <div className={`w-2 h-2 rounded-full ${statusColor}`} />
        </div>

        {/* Label */}
        <p className="text-xs font-medium text-foreground truncate" title={d.label}>
          {d.label}
        </p>

        {/* Artifact value preview */}
        {!!d.extra_data?.artifact_value && (
          <p className="text-[9px] text-muted-foreground font-mono truncate mt-0.5" title={String(d.extra_data.artifact_value)}>
            {String(d.extra_data.artifact_value)}
          </p>
        )}

        {/* Notes preview */}
        {!!d.extra_data?.notes && (
          <p className="text-[9px] text-muted-foreground truncate mt-0.5" title={String(d.extra_data.notes)}>
            {String(d.extra_data.notes)}
          </p>
        )}

        {/* Badges */}
        <div className="flex gap-1 mt-1.5">
          {isMalicious && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
              Malicious
            </span>
          )}
          {isRemediated && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400 font-medium">
              Remediated
            </span>
          )}
        </div>
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-amber-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-amber-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(HostIndicatorNode)
