import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ShieldCheck } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function DomainControllerNode({ data, selected }: NodeProps<GraphNode>) {
  const { resolvedTheme } = useTheme()
  const d = data as GraphNodeData

  const statusColor =
    d.containmentStatus === 'active'
      ? 'bg-red-500'
      : d.containmentStatus === 'isolated'
        ? 'bg-orange-500'
        : 'bg-green-500'

  const isAdminCompromise = !!(d.compromisedAccountId || d.extra_data?.admin_compromise)
  const hasCorrelation = d.correlation && Object.values(d.correlation).some((v) => v > 0)

  return (
    <div
      className={`relative w-[180px] bg-card rounded-lg shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : isAdminCompromise ? 'border-amber-500/40' : 'border-border'
        }`}
    >
      {/* Gradient header strip */}
      <div
        className={`h-1 rounded-t-lg ${isAdminCompromise
            ? 'bg-gradient-to-r from-amber-500 to-indigo-500'
            : 'bg-gradient-to-r from-indigo-500 to-indigo-400'
          }`}
      />

      <div className="p-3">
        {/* Icon + status row */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <ShieldCheck
              className={`w-4 h-4 ${isAdminCompromise ? 'text-amber-400' : 'text-indigo-400'}`}
            />
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Domain Controller
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

        {/* Admin compromise warning */}
        {isAdminCompromise && (
          <div className="mt-1.5 flex items-center gap-1">
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 font-semibold">
              Admin Compromised
            </span>
          </div>
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
        className="!w-2 !h-2 !bg-indigo-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-indigo-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(DomainControllerNode)
