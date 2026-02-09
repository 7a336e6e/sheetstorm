import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { Monitor } from 'lucide-react'
import { useTheme } from '@/components/providers/theme-provider'

export interface GraphNodeData {
  label: string
  nodeType: string
  containmentStatus?: string
  isInitialAccess?: boolean
  isObjective?: boolean
  ipAddress?: string
  compromisedHostId?: string
  compromisedAccountId?: string
  correlation?: {
    accounts: number
    malware: number
    network_iocs: number
    host_iocs: number
    timeline_events: number
  }
  extra_data?: Record<string, unknown>
  [key: string]: unknown
}

export type GraphNode = Node<GraphNodeData>

function HostNode({ data, selected }: NodeProps<GraphNode>) {
  const d = data as GraphNodeData
  const { resolvedTheme } = useTheme()

  const statusColor =
    d.containmentStatus === 'active'
      ? 'bg-red-500'
      : d.containmentStatus === 'isolated'
        ? 'bg-orange-500'
        : 'bg-green-500'

  const hasCorrelation = d.correlation && Object.values(d.correlation).some((v) => v > 0)

  return (
    <div
      className={`relative w-[160px] bg-card rounded-lg shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : 'border-border'
        }`}
    >
      {/* Gradient header strip */}
      <div className="h-1 rounded-t-lg bg-gradient-to-r from-blue-500 to-blue-400" />

      <div className="p-3">
        {/* Icon + status row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Monitor className="w-4 h-4 text-blue-400 dark:text-blue-400" />
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              {d.nodeType?.replace('_', ' ') || 'host'}
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
        className="!w-2 !h-2 !bg-blue-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-blue-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(HostNode)
