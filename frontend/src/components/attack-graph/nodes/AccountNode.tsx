import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { User, KeyRound } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function AccountNode({ data, selected }: NodeProps<GraphNode>) {
  const d = data as GraphNodeData
  const { resolvedTheme } = useTheme()

  const isServiceAccount = d.nodeType === 'service_account'
  const Icon = isServiceAccount ? KeyRound : User

  const statusColor =
    d.containmentStatus === 'active'
      ? 'bg-red-500'
      : d.containmentStatus === 'isolated'
        ? 'bg-orange-500'
        : 'bg-green-500'

  const isPrivileged = !!(d.extra_data?.is_privileged)
  const hasCorrelation = d.correlation && Object.values(d.correlation).some((v) => v > 0)

  return (
    <div
      className={`relative w-[140px] bg-card rounded-full shadow-lg border overflow-hidden ${selected ? 'border-cyan-500/50' : 'border-border'
        }`}
    >
      {/* Gradient header strip - thin top line for pill shape */}
      <div className="h-1 rounded-t-full bg-gradient-to-r from-emerald-500 to-emerald-400" />

      <div className="px-3 py-2">
        {/* Icon + label row */}
        <div className="flex items-center gap-1.5">
          <Icon className="w-3.5 h-3.5 text-emerald-400 dark:text-emerald-400 shrink-0" />
          <p className="text-sm font-medium text-foreground truncate flex-1" title={d.label}>
            {d.label}
          </p>
          <div className={`w-2 h-2 rounded-full shrink-0 ${statusColor}`} />
        </div>

        {/* Type + privilege row */}
        <div className="flex items-center gap-1 mt-1 ml-5">
          <span className="text-[10px] text-muted-foreground">
            {isServiceAccount ? 'Service' : 'User'}
          </span>
          {isPrivileged && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 font-semibold">
              Priv
            </span>
          )}
        </div>

        {/* Domain info */}
        {!!d.extra_data?.domain && (
          <p className="text-[10px] text-muted-foreground font-mono truncate mt-0.5 ml-5">
            {String(d.extra_data.domain)}
          </p>
        )}

        {/* Status badge */}
        {!!d.extra_data?.status && String(d.extra_data.status) !== 'unknown' && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ml-5 inline-block mt-0.5 ${
            d.extra_data.status === 'compromised'
              ? 'bg-red-500/20 text-red-400'
              : d.extra_data.status === 'disabled'
                ? 'bg-slate-500/20 text-slate-400'
                : 'bg-blue-500/20 text-blue-400'
          }`}>
            {String(d.extra_data.status)}
          </span>
        )}

        {/* Correlation badges */}
        {hasCorrelation && (
          <div className="flex flex-wrap gap-1 mt-1.5 ml-5">
            {d.correlation!.malware > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.malware} mal
              </span>
            )}
            {d.correlation!.timeline_events > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.timeline_events} evt
              </span>
            )}
            {d.correlation!.host_iocs > 0 && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.host_iocs} ioc
              </span>
            )}
          </div>
        )}
      </div>

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-emerald-500 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-emerald-500 !border-background !border-2"
      />
    </div>
  )
}

export default memo(AccountNode)
