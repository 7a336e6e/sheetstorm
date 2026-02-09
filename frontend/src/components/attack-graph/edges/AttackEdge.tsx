import { memo } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react'

const edgeColors: Record<string, string> = {
  lateral_movement: '#f97316',
  credential_theft: '#eab308',
  data_exfiltration: '#ec4899',
  command_control: '#ef4444',
  initial_access: '#ef4444',
  privilege_escalation: '#a855f7',
  persistence: '#6366f1',
  discovery: '#3b82f6',
  execution: '#f43f5e',
  defense_evasion: '#8b5cf6',
  collection: '#14b8a6',
  associated_with: '#64748b',
}

function AttackEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const edgeType = (data?.type as string) || 'associated_with'
  const label = data?.label as string
  const mitreTactic = data?.mitreTactic as string
  const isAssociation = edgeType === 'associated_with'

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const color = edgeColors[edgeType] || edgeColors.associated_with
  const strokeWidth = selected ? 3 : isAssociation ? 1 : 2
  const opacity = isAssociation ? 0.5 : 1
  const dashArray = isAssociation ? '6 3' : edgeType === 'lateral_movement' ? '8 4' : undefined

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? '#22d3ee' : color,
          strokeWidth,
          opacity,
          strokeDasharray: dashArray,
        }}
        markerEnd={`url(#arrow-${selected ? 'selected' : edgeType})`}
      />
      {label && !isAssociation && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <div className="bg-card/90 backdrop-blur-sm text-[9px] text-muted-foreground px-1.5 py-0.5 rounded border border-border max-w-[120px] truncate">
              {label}
              {mitreTactic && (
                <span className="ml-1 text-purple-400">
                  [{mitreTactic}]
                </span>
              )}
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

export default memo(AttackEdge)
