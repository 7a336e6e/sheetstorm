import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Crosshair } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function AttackerNode({ data, selected }: NodeProps<GraphNode>) {
  const { resolvedTheme } = useTheme()
  const d = data as GraphNodeData

  const hasCorrelation = d.correlation && Object.values(d.correlation).some((v) => v > 0)

  return (
    <div
      className={`relative w-[160px] bg-card rounded-lg shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : 'border-red-500/30'
        }`}
    >
      {/* Red gradient header strip */}
      <div className="h-1 rounded-t-lg bg-gradient-to-r from-red-600 to-red-400" />

      <div className="p-3">
        {/* Icon row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Crosshair className="w-4 h-4 text-red-400" />
            <span className="text-[10px] text-red-400/80 uppercase tracking-wider font-semibold">
              Attacker
            </span>
          </div>
          <div className="w-2 h-2 rounded-full bg-red-500" />
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

        {/* Threat actor info from extra_data */}
        {!!d.extra_data?.threat_actor && (
          <p className="text-[10px] text-red-400/70 truncate mt-0.5">
            TA: {String(d.extra_data.threat_actor)}
          </p>
        )}

        {/* Initial Access badge */}
        {d.isInitialAccess && (
          <div className="mt-1.5">
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
              Initial Access
            </span>
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
        className="!w-2 !h-2 !bg-red-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-red-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(AttackerNode)
