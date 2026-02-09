import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Radio } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function C2ServerNode({ data, selected }: NodeProps<GraphNode>) {
  const { resolvedTheme } = useTheme()
  const d = data as GraphNodeData

  const statusColor =
    d.containmentStatus === 'active'
      ? 'bg-red-500'
      : d.containmentStatus === 'isolated'
        ? 'bg-orange-500'
        : 'bg-green-500'

  const hasCorrelation = d.correlation && Object.values(d.correlation).some((v) => v > 0)

  return (
    <div
      className={`relative w-[160px] bg-card rounded-lg shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : 'border-orange-500/30'
        }`}
    >
      {/* Orange gradient header strip */}
      <div className="h-1 rounded-t-lg bg-gradient-to-r from-orange-500 to-orange-400" />

      {/* Pulse animation ring */}
      {d.containmentStatus === 'active' && (
        <div className="absolute -top-1 -right-1 w-3 h-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-orange-500" />
        </div>
      )}

      <div className="p-3">
        {/* Icon + status row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Radio className="w-4 h-4 text-orange-400" />
            <span className="text-[10px] text-orange-400/80 uppercase tracking-wider font-semibold">
              C2 Server
            </span>
          </div>
          <div className={`w-2 h-2 rounded-full ${statusColor}`} />
        </div>

        {/* Label */}
        <p className="text-sm font-medium text-foreground truncate" title={d.label}>
          {d.label}
        </p>

        {/* IP subtitle */}
        {d.ipAddress && (
          <p className="text-[10px] text-muted-foreground font-mono truncate mt-0.5">
            {d.ipAddress}
          </p>
        )}

        {/* C2 framework info */}
        {!!d.extra_data?.c2_framework && (
          <p className="text-[10px] text-orange-400/70 truncate mt-0.5">
            Framework: {String(d.extra_data.c2_framework)}
          </p>
        )}

        {/* Initial Access / Objective badges */}
        {(d.isInitialAccess || d.isObjective) && (
          <div className="flex gap-1 mt-1.5">
            {d.isInitialAccess && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
                Initial Access
              </span>
            )}
            {d.isObjective && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 font-medium">
                Objective
              </span>
            )}
          </div>
        )}

        {/* Correlation badges */}
        {hasCorrelation && (
          <div className="flex flex-wrap gap-1 mt-2">
            {d.correlation!.accounts > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.accounts} acct
              </span>
            )}
            {d.correlation!.malware > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.malware} mal
              </span>
            )}
            {d.correlation!.network_iocs > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.network_iocs} net
              </span>
            )}
            {d.correlation!.host_iocs > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.host_iocs} ioc
              </span>
            )}
            {d.correlation!.timeline_events > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.timeline_events} evt
              </span>
            )}
          </div>
        )}
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-orange-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-orange-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(C2ServerNode)
