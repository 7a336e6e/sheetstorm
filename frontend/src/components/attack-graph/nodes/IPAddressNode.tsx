import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Globe } from 'lucide-react'
import type { GraphNodeData, GraphNode } from './HostNode'
import { useTheme } from '@/components/providers/theme-provider'

function IPAddressNode({ data, selected }: NodeProps<GraphNode>) {
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
      className={`relative w-[160px] bg-card rounded-md shadow-lg border ${
        selected ? 'border-cyan-500/50' : 'border-border'
      }`}
    >
      {/* Gradient header strip */}
      <div className="h-1 rounded-t-md bg-gradient-to-r from-slate-400 to-slate-500" />

      <div className="px-2.5 py-1.5">
        {/* Compact chip layout */}
        <div className="flex items-center gap-1.5">
          <Globe className="w-3 h-3 text-muted-foreground shrink-0" />
          <p
            className="text-xs font-medium text-white font-mono truncate"
            title={d.label}
          >
            {d.label}
          </p>
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColor}`} />
        </div>

        {/* Extra info row: protocol/port + direction */}
        <div className="flex items-center gap-1 mt-0.5 ml-[18px]">
          {!!(d.extra_data?.protocol || d.extra_data?.port) && (
            <span className="text-[9px] text-slate-500 font-mono">
              {!!d.extra_data?.protocol && String(d.extra_data.protocol)}
              {!!d.extra_data?.port && `:${String(d.extra_data.port)}`}
            </span>
          )}
          {!!d.extra_data?.direction && (
            <span className={`text-[9px] px-1 py-0.5 rounded-full font-medium ${
              d.extra_data.direction === 'inbound'
                ? 'bg-blue-500/20 text-blue-400'
                : d.extra_data.direction === 'outbound'
                  ? 'bg-orange-500/20 text-orange-400'
                  : 'bg-slate-500/20 text-slate-400'
            }`}>
              {String(d.extra_data.direction)}
            </span>
          )}
          {!!d.extra_data?.is_malicious && (
            <span className="text-[9px] px-1 py-0.5 rounded-full bg-red-500/20 text-red-400 font-medium">
              malicious
            </span>
          )}
        </div>

        {/* Description */}
        {!!d.extra_data?.description && (
          <p className="text-[9px] text-muted-foreground truncate mt-0.5 ml-[18px]" title={String(d.extra_data.description)}>
            {String(d.extra_data.description)}
          </p>
        )}

        {/* Destination host */}
        {!!d.extra_data?.destination_host && (
          <p className="text-[9px] text-slate-500 font-mono truncate mt-0.5 ml-[18px]" title={String(d.extra_data.destination_host)}>
            → {String(d.extra_data.destination_host)}
          </p>
        )}

        {/* Correlation badges */}
        {hasCorrelation && (
          <div className="flex flex-wrap gap-1 mt-1 ml-[18px]">
            {d.correlation!.network_iocs > 0 && (
              <span className="text-[9px] px-1 py-0.5 rounded-full bg-muted text-muted-foreground">
                {d.correlation!.network_iocs} net
              </span>
            )}
            {d.correlation!.timeline_events > 0 && (
              <span className="text-[9px] px-1 py-0.5 rounded-full bg-muted text-muted-foreground">
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
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-background !border-2"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-background !border-2"
      />
    </div>
  )
}

export default memo(IPAddressNode)
