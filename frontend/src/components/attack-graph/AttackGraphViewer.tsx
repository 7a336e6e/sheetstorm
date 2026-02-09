"use client"

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  Panel,
  useReactFlow,
  ReactFlowProvider,
  addEdge,
  Connection,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { Button } from '@/components/ui/button'
import {
  ZoomIn,
  ZoomOut,
  Maximize,
  Download,
  RefreshCw,
  Loader2,
  GitBranch,
  LayoutGrid,
  X,
  Plus,
  Trash2,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import type { AttackGraphNode, AttackGraphEdge as GraphEdgeType, CompromisedHost, TimelineEvent } from '@/types'
import { useTheme } from '@/components/providers/theme-provider'
import { Textarea } from '@/components/ui/textarea'

// Custom nodes
import HostNode from './nodes/HostNode'
import DomainControllerNode from './nodes/DomainControllerNode'
import AttackerNode from './nodes/AttackerNode'
import C2ServerNode from './nodes/C2ServerNode'
import AccountNode from './nodes/AccountNode'
import IPAddressNode from './nodes/IPAddressNode'
import MalwareNode from './nodes/MalwareNode'
import CloudNode from './nodes/CloudNode'
import DatabaseNode from './nodes/DatabaseNode'
import DefaultNode from './nodes/DefaultNode'
import HostIndicatorNode from './nodes/HostIndicatorNode'

// Custom edge
import AttackEdge from './edges/AttackEdge'

interface AttackGraphViewerProps {
  incidentId: string
  hosts?: CompromisedHost[]
  timeline?: TimelineEvent[]
}

// Map node_type to React Flow node type
function getNodeType(nodeType: string): string {
  switch (nodeType) {
    case 'workstation':
    case 'server':
    case 'file_server':
    case 'web_server':
      return 'host'
    case 'domain_controller':
      return 'domainController'
    case 'attacker':
      return 'attacker'
    case 'c2_server':
      return 'c2Server'
    case 'user':
    case 'service_account':
      return 'account'
    case 'ip_address':
      return 'ipAddress'
    case 'malware':
      return 'malware'
    case 'host_indicator':
      return 'hostIndicator'
    case 'cloud_resource':
      return 'cloud'
    case 'database':
      return 'database'
    default:
      return 'default'
  }
}

const nodeTypes: NodeTypes = {
  host: HostNode,
  domainController: DomainControllerNode,
  attacker: AttackerNode,
  c2Server: C2ServerNode,
  account: AccountNode,
  ipAddress: IPAddressNode,
  malware: MalwareNode,
  hostIndicator: HostIndicatorNode,
  cloud: CloudNode,
  database: DatabaseNode,
  default: DefaultNode,
}

const edgeTypes: EdgeTypes = {
  attack: AttackEdge,
}

// Node style colors for legend
const legendItems = [
  { type: 'workstation', label: 'Workstation', color: '#3b82f6' },
  { type: 'server', label: 'Server', color: '#8b5cf6' },
  { type: 'domain_controller', label: 'DC', color: '#6366f1' },
  { type: 'attacker', label: 'Attacker', color: '#ef4444' },
  { type: 'c2_server', label: 'C2 Server', color: '#f97316' },
  { type: 'ip_address', label: 'IP Address', color: '#94a3b8' },
  { type: 'malware', label: 'Malware', color: '#f43f5e' },
  { type: 'user', label: 'Account', color: '#10b981' },
  { type: 'host_indicator', label: 'Host IOC', color: '#f59e0b' },
  { type: 'cloud_resource', label: 'Cloud', color: '#06b6d4' },
  { type: 'database', label: 'Database', color: '#0891b2' },
]

const edgeLegend = [
  { type: 'Lateral Movement', color: '#f97316', style: 'dashed' },
  { type: 'Association', color: '#64748b', style: 'dotted' },
  { type: 'C2 / Exfil', color: '#ef4444', style: 'solid' },
]

function transformToReactFlowData(
  apiNodes: AttackGraphNode[],
  apiEdges: GraphEdgeType[]
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = apiNodes.map((n) => ({
    id: n.id,
    type: getNodeType(n.node_type),
    position: { x: n.position_x, y: n.position_y },
    data: {
      label: n.label,
      nodeType: n.node_type,
      containmentStatus: n.extra_data?.containment_status || n.cytoscape?.data?.containmentStatus,
      isInitialAccess: n.is_initial_access,
      isObjective: n.is_objective,
      ipAddress: n.extra_data?.ip_address,
      compromisedHostId: n.compromised_host_id,
      compromisedAccountId: n.compromised_account_id,
      correlation: n.correlation,
      extra_data: n.extra_data,
    },
  }))

  const edges: Edge[] = apiEdges.map((e) => ({
    id: e.id,
    source: e.source_node_id,
    target: e.target_node_id,
    type: 'attack',
    data: {
      type: e.edge_type,
      label: e.label,
      mitreTactic: e.mitre_tactic,
      mitreTechnique: e.mitre_technique,
    },
  }))

  return { nodes, edges }
}

function GraphInner({ incidentId }: { incidentId: string }) {
  const { toast } = useToast()
  const { resolvedTheme } = useTheme()
  const { fitView, zoomIn, zoomOut } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [selectedElement, setSelectedElement] = useState<{ type: 'node' | 'edge'; data: Record<string, unknown> } | null>(null)
  const [isEmpty, setIsEmpty] = useState(false)

  // Draw mode
  const [isDrawMode, setIsDrawMode] = useState(false)
  const [sourceNodeId, setSourceNodeId] = useState<string | null>(null)
  const [isEdgeModalOpen, setIsEdgeModalOpen] = useState(false)
  const [edgeFormData, setEdgeFormData] = useState({
    targetId: '',
    type: 'lateral_movement',
    label: '',
    description: '',
    timeline_event_id: '',
  })
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([])
  const [isLoadingEvents, setIsLoadingEvents] = useState(false)

  // Manual Node Creation
  const [isAddNodeModalOpen, setIsAddNodeModalOpen] = useState(false)
  const [newNodeFormData, setNewNodeFormData] = useState({
    type: 'attacker',
    label: '',
    description: '',
  })

  const fetchGraph = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await api.get<{
        nodes: AttackGraphNode[]
        edges: GraphEdgeType[]
      }>(`/incidents/${incidentId}/attack-graph`)

      if (response.nodes && response.nodes.length > 0) {
        const { nodes: rfNodes, edges: rfEdges } = transformToReactFlowData(
          response.nodes,
          response.edges || []
        )
        setNodes(rfNodes)
        setEdges(rfEdges)
        setIsEmpty(false)
      } else {
        setNodes([])
        setEdges([])
        setIsEmpty(true)
      }
    } catch (error) {
      console.error('Failed to fetch attack graph:', error)
      toast({
        title: 'Error fetching graph',
        description: 'Could not load attack graph data',
        variant: 'destructive',
      })
      setIsEmpty(true)
    } finally {
      setIsLoading(false)
    }
  }, [incidentId, toast, setNodes, setEdges])

  const onNodesDelete = useCallback(
    async (nodesToDelete: Node[]) => {
      // Optimistically update state
      const nodesToDeleteIds = new Set(nodesToDelete.map(n => n.id))
      setNodes((nodes) => nodes.filter(n => !nodesToDeleteIds.has(n.id)))
      setEdges((edges) => edges.filter(e => !nodesToDeleteIds.has(e.source) && !nodesToDeleteIds.has(e.target)))

      // Call API
      for (const node of nodesToDelete) {
        try {
          await api.delete(`/incidents/${incidentId}/attack-graph/nodes/${node.id}`)
        } catch (error) {
          console.error(`Failed to delete node ${node.id}:`, error)
          toast({ title: 'Error', description: `Failed to delete node ${node.data.label}`, variant: 'destructive' })
        }
      }
    },
    [incidentId, setNodes, setEdges, toast]
  )

  const onEdgesDelete = useCallback(
    async (edgesToDelete: Edge[]) => {
      // Optimistically update
      const edgesToDeleteIds = new Set(edgesToDelete.map(e => e.id))
      setEdges((edges) => edges.filter(e => !edgesToDeleteIds.has(e.id)))

      // Call API
      for (const edge of edgesToDelete) {
        try {
          await api.delete(`/incidents/${incidentId}/attack-graph/edges/${edge.id}`)
        } catch (error) {
          console.error(`Failed to delete edge ${edge.id}:`, error)
        }
      }
    },
    [incidentId, setEdges]
  )

  const onConnect = useCallback(
    async (params: Connection) => {
      if (!params.source || !params.target) return

      // Optimistic update
      setEdges((eds) => addEdge({ ...params, type: 'attack', animated: true }, eds))

      try {
        const newEdge = await api.post<GraphEdgeType>(`/incidents/${incidentId}/attack-graph/edges`, {
          source_node_id: params.source,
          target_node_id: params.target,
          edge_type: 'associated_with', // Default type, user can edit later if we add edit feature
          label: 'Associated',
        })

        // Update with real ID from backend
        setEdges((eds) => eds.map(e => {
          if (e.source === params.source && e.target === params.target && !e.id) {
            return { ...e, id: newEdge.id }
          }
          return e
        }))

      } catch (error) {
        console.error('Failed to create connection:', error)
        toast({ title: 'Connection Failed', description: 'Could not create link', variant: 'destructive' })
        // Revert optimistic update? For now let's just refresh
        fetchGraph()
      }
    },
    [incidentId, setEdges, toast, fetchGraph]
  )

  const handleCreateNode = async () => {
    if (!newNodeFormData.label) {
      toast({ title: 'Error', description: 'Label is required', variant: 'destructive' })
      return
    }

    try {
      // Default position center of view or 0,0
      // We can use project function from useReactFlow if we want exact center, but 0,0 with autolayout or just visible area is fine.
      // Let's create it at a random offset from center of visualization roughly
      const position = { x: Math.random() * 500, y: Math.random() * 500 }

      const newNode = await api.post<AttackGraphNode>(`/incidents/${incidentId}/attack-graph/nodes`, {
        node_type: newNodeFormData.type,
        label: newNodeFormData.label,
        extra_data: { description: newNodeFormData.description },
        position_x: position.x,
        position_y: position.y,
      })

      // Add to state
      setNodes((nodes) => [
        ...nodes,
        {
          id: newNode.id,
          type: getNodeType(newNode.node_type),
          position: { x: newNode.position_x, y: newNode.position_y },
          data: {
            label: newNode.label,
            nodeType: newNode.node_type,
            extra_data: newNode.extra_data,
          }
        }
      ])

      toast({ title: 'Node Created', description: `${newNodeFormData.label} added to graph` })
      setIsAddNodeModalOpen(false)
      setNewNodeFormData({ type: 'attacker', label: '', description: '' })

    } catch (error) {
      console.error('Failed to create node:', error)
      toast({ title: 'Error', description: 'Failed to create node', variant: 'destructive' })
    }
  }



  /* Auto-generate graph if empty on load */
  const hasAutoGenerated = useRef(false)
  useEffect(() => {
    if (!isLoading && isEmpty && !hasAutoGenerated.current) {
      hasAutoGenerated.current = true
      handleRegenerate()
    }
  }, [isLoading, isEmpty])

  const handleRegenerate = async () => {
    // Native confirm removed as per user request
    setIsRegenerating(true)
    try {
      await api.post(`/incidents/${incidentId}/attack-graph/auto-generate`, { clear_existing: true })
      toast({ title: 'Graph Regenerated', description: 'Attack graph has been rebuilt from incident data' })
      fetchGraph()
    } catch (error) {
      console.error('Failed to regenerate graph:', error)
      toast({ title: 'Regeneration Failed', description: 'Could not auto-generate graph', variant: 'destructive' })
    } finally {
      setIsRegenerating(false)
    }
  }

  const handleCreateEdge = async () => {
    if (!sourceNodeId || !edgeFormData.targetId) return
    try {
      await api.post(`/incidents/${incidentId}/attack-graph/edges`, {
        source_node_id: sourceNodeId,
        target_node_id: edgeFormData.targetId,
        edge_type: edgeFormData.type,
        label: edgeFormData.label || edgeFormData.type.replace(/_/g, ' '),
        description: edgeFormData.description || undefined,
        timeline_event_id: edgeFormData.timeline_event_id || undefined,
      })
      toast({ title: 'Edge Created', description: 'Manual edge added to graph' })
      setIsEdgeModalOpen(false)
      setSourceNodeId(null)
      setEdgeFormData({ targetId: '', type: 'lateral_movement', label: '', description: '', timeline_event_id: '' })
      setTimelineEvents([])
      fetchGraph()
    } catch (error) {
      console.error('Failed to create edge:', error)
      toast({ title: 'Error', description: 'Failed to create edge', variant: 'destructive' })
    }
  }

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (isDrawMode) {
        if (!sourceNodeId) {
          setSourceNodeId(node.id)
          toast({ title: 'Source Selected', description: `Now click a target node to link from ${node.data.label}` })
        } else {
          if (sourceNodeId === node.id) {
            setSourceNodeId(null)
            return
          }
          setEdgeFormData((prev) => ({ ...prev, targetId: node.id }))
          // Fetch timeline events for the incident so user can select one
          setIsLoadingEvents(true)
          api.get<{ items: TimelineEvent[] }>(`/incidents/${incidentId}/timeline`)
            .then((res) => setTimelineEvents(res.items || []))
            .catch(() => setTimelineEvents([]))
            .finally(() => setIsLoadingEvents(false))
          setIsEdgeModalOpen(true)
        }
      } else {
        setSelectedElement({ type: 'node', data: node.data as Record<string, unknown> })
      }
    },
    [isDrawMode, sourceNodeId, toast]
  )

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      if (!isDrawMode) {
        setSelectedElement({ type: 'edge', data: (edge.data || {}) as Record<string, unknown> })
      }
    },
    [isDrawMode]
  )

  const handlePaneClick = useCallback(() => {
    setSelectedElement(null)
  }, [])

  const handleNodeDragStop = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      try {
        await api.put(`/incidents/${incidentId}/attack-graph/nodes/${node.id}`, {
          position_x: node.position.x,
          position_y: node.position.y,
        })
      } catch { /* ignore position save errors */ }
    },
    [incidentId]
  )

  const handleAutoLayout = useCallback(async () => {
    if (nodes.length === 0) return
    // Simple hierarchical layout
    const sorted = [...nodes].sort((a, b) => {
      if (a.data.isInitialAccess) return -1
      if (b.data.isInitialAccess) return 1
      return 0
    })

    const hostNodeTypes = ['host', 'domainController']
    const hostNodes = sorted.filter(n => hostNodeTypes.includes(n.type || ''))
    const otherNodes = sorted.filter(n => !hostNodeTypes.includes(n.type || ''))

    const updatedNodes = nodes.map(n => {
      const hostIdx = hostNodes.findIndex(h => h.id === n.id)
      if (hostIdx >= 0) {
        return {
          ...n,
          position: {
            x: 300 + (hostIdx % 4) * 350,
            y: 200 + Math.floor(hostIdx / 4) * 350,
          },
        }
      }

      const otherIdx = otherNodes.findIndex(o => o.id === n.id)
      if (otherIdx >= 0) {
        // Find connected host and position nearby
        const connectedEdge = edges.find(
          e => e.source === n.id || e.target === n.id
        )
        const connectedHostId = connectedEdge
          ? connectedEdge.source === n.id
            ? connectedEdge.target
            : connectedEdge.source
          : null
        const host = connectedHostId ? nodes.find(h => h.id === connectedHostId) : null

        if (host) {
          const angle = (otherIdx * 0.8) + Math.random() * 0.3
          return {
            ...n,
            position: {
              x: host.position.x + Math.cos(angle) * 180,
              y: host.position.y + Math.sin(angle) * 180,
            },
          }
        }

        return {
          ...n,
          position: {
            x: 100 + (otherIdx % 6) * 200,
            y: 600 + Math.floor(otherIdx / 6) * 150,
          },
        }
      }

      return n
    })

    setNodes(updatedNodes)
    setTimeout(() => fitView({ padding: 0.2, duration: 500 }), 100)
  }, [nodes, edges, setNodes, fitView])

  const handleExportPng = useCallback(() => {
    // Use the React Flow viewport to export
    const el = document.querySelector('.react-flow__viewport') as HTMLElement
    if (!el) return

    import('html-to-image' as string).then((mod: { toPng: (el: HTMLElement, opts: Record<string, unknown>) => Promise<string> }) => {
      mod.toPng(el, {
        backgroundColor: resolvedTheme === 'dark' ? '#0f172a' : '#ffffff',
        width: el.scrollWidth,
        height: el.scrollHeight,
      }).then((dataUrl: string) => {
        const link = document.createElement('a')
        link.download = `attack-graph-${incidentId}.png`
        link.href = dataUrl
        link.click()
      }).catch(() => {
        toast({ title: 'Export Failed', description: 'Could not export graph as PNG', variant: 'destructive' })
      })
    }).catch(() => {
      toast({ title: 'Export Unavailable', description: 'PNG export requires html-to-image package', variant: 'destructive' })
    })
  }, [incidentId, toast])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  useEffect(() => {
    if (!isLoading && nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 200)
    }
  }, [isLoading, nodes.length, fitView])

  if (isEmpty && !isLoading) {
    return (
      <div className="h-[600px] flex flex-col items-center justify-center bg-muted/50 rounded-lg border border-border">
        <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
          <svg className="h-8 w-8 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <p className="text-muted-foreground text-center mb-2">No graph data found</p>
        <p className="text-muted-foreground/60 text-sm text-center max-w-md mb-6">
          Generate an attack graph from incident data to visualize the attack path.
        </p>
        <Button onClick={handleRegenerate} disabled={isRegenerating}>
          {isRegenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Generate Graph
        </Button>
      </div>
    )
  }

  // Node types options
  const nodeTypeOptions = [
    { value: 'attacker', label: 'Attacker' },
    { value: 'c2_server', label: 'C2 Server' },
    { value: 'malware', label: 'Malware' },
    { value: 'ip_address', label: 'IP Address' },
    { value: 'user', label: 'Account' },
    { value: 'host_indicator', label: 'Host Indicator' },
    { value: 'cloud_resource', label: 'Cloud Resource' },
    { value: 'database', label: 'Database' },
    { value: 'workstation', label: 'Workstation' },
    { value: 'server', label: 'Server' },
    { value: 'domain_controller', label: 'Domain Controller' },
  ]

  return (
    <div className="relative h-[600px] rounded-lg border border-white/10 overflow-hidden">
      {/* Edge creation modal */}
      <Dialog
        open={isEdgeModalOpen}
        onOpenChange={(open) => {
          setIsEdgeModalOpen(open)
          if (!open) {
            setSourceNodeId(null)
            setTimelineEvents([])
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Connection</DialogTitle>
            <DialogDescription>Link two nodes with an edge type and optional timeline event</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Type</Label>
              <Select value={edgeFormData.type} onValueChange={(v) => setEdgeFormData({ ...edgeFormData, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="lateral_movement">Lateral Movement</SelectItem>
                  <SelectItem value="command_control">Command &amp; Control</SelectItem>
                  <SelectItem value="data_exfiltration">Data Exfiltration</SelectItem>
                  <SelectItem value="credential_theft">Credential Theft</SelectItem>
                  <SelectItem value="privilege_escalation">Privilege Escalation</SelectItem>
                  <SelectItem value="initial_access">Initial Access</SelectItem>
                  <SelectItem value="persistence">Persistence</SelectItem>
                  <SelectItem value="discovery">Discovery</SelectItem>
                  <SelectItem value="execution">Execution</SelectItem>
                  <SelectItem value="defense_evasion">Defense Evasion</SelectItem>
                  <SelectItem value="collection">Collection</SelectItem>
                  <SelectItem value="associated_with">Associated With</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Label (Optional)</Label>
              <Input
                value={edgeFormData.label}
                onChange={(e) => setEdgeFormData({ ...edgeFormData, label: e.target.value })}
                placeholder="e.g. RDP Access"
              />
            </div>
            <div className="grid gap-2">
              <Label>Linked Timeline Event (Optional)</Label>
              {isLoadingEvents ? (
                <div className="flex items-center gap-2 text-muted-foreground text-sm py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading events...
                </div>
              ) : (
                <Select
                  value={edgeFormData.timeline_event_id}
                  onValueChange={(v) => {
                    setEdgeFormData({ ...edgeFormData, timeline_event_id: v })
                    // Auto-fill label from event activity if label is empty
                    if (!edgeFormData.label) {
                      const event = timelineEvents.find(e => e.id === v)
                      if (event) {
                        setEdgeFormData(prev => ({
                          ...prev,
                          timeline_event_id: v,
                          label: event.activity?.slice(0, 80) || prev.label,
                        }))
                      }
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select an event..." />
                  </SelectTrigger>
                  <SelectContent className="max-h-[200px]">
                    <SelectItem value="none">None</SelectItem>
                    {timelineEvents.map((evt) => (
                      <SelectItem key={evt.id} value={evt.id}>
                        <div className="flex flex-col">
                          <span className="text-xs truncate max-w-[350px]">
                            {evt.activity?.slice(0, 80)}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {evt.hostname && `${evt.hostname} • `}
                            {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : ''}
                            {evt.mitre_tactic && ` • ${evt.mitre_tactic}`}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="grid gap-2">
              <Label>Description (Optional)</Label>
              <Textarea
                value={edgeFormData.description}
                onChange={(e) => setEdgeFormData({ ...edgeFormData, description: e.target.value })}
                placeholder="Describe why these nodes are linked..."
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleCreateEdge}>Create Link</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Node Modal */}
      <Dialog open={isAddNodeModalOpen} onOpenChange={setIsAddNodeModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Manual Node</DialogTitle>
            <DialogDescription>Create a new node in the attack graph</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Node Type</Label>
              <Select
                value={newNodeFormData.type}
                onValueChange={(v) => setNewNodeFormData({ ...newNodeFormData, type: v })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {nodeTypeOptions.map(opt => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Label</Label>
              <Input
                value={newNodeFormData.label}
                onChange={(e) => setNewNodeFormData({ ...newNodeFormData, label: e.target.value })}
                placeholder="e.g. Malicious Actor"
              />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Input
                value={newNodeFormData.description}
                onChange={(e) => setNewNodeFormData({ ...newNodeFormData, description: e.target.value })}
                placeholder="Optional description"
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleCreateNode}>Create Node</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {isLoading && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Loading graph...</span>
          </div>
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        onNodeDragStop={handleNodeDragStop}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: 'attack' }}
        fitView
        minZoom={0.2}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
        className={resolvedTheme === 'dark' ? 'bg-slate-950' : 'bg-slate-50'}
      >
        {/* SVG Arrow Marker Definitions */}
        <svg style={{ position: 'absolute', width: 0, height: 0 }}>
          <defs>
            {Object.entries({
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
            }).map(([type, color]) => (
              <marker
                key={type}
                id={`arrow-${type}`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
              </marker>
            ))}
            <marker
              id="arrow-selected"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#22d3ee" />
            </marker>
          </defs>
        </svg>

        <Background variant={BackgroundVariant.Dots} gap={20} size={1} className="[&amp;>*]:!stroke-border" />

        <MiniMap
          nodeColor={(n) => {
            const colors: Record<string, string> = {
              host: '#3b82f6',
              domainController: '#6366f1',
              attacker: '#ef4444',
              c2Server: '#f97316',
              account: '#10b981',
              ipAddress: '#94a3b8',
              malware: '#f43f5e',
              hostIndicator: '#f59e0b',
              cloud: '#06b6d4',
              database: '#0891b2',
              default: '#9ca3af',
            }
            return colors[n.type || 'default'] || '#9ca3af'
          }}
          maskColor={resolvedTheme === 'dark' ? 'rgba(15, 23, 42, 0.8)' : 'rgba(248, 250, 252, 0.8)'}
          style={{
            backgroundColor: resolvedTheme === 'dark' ? '#0f172a' : '#f8fafc',
            border: '1px solid',
            borderColor: resolvedTheme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
            borderRadius: '8px'
          }}
          pannable
          zoomable
        />

        {/* Toolbar */}
        <Panel position="top-left">
          <div className="flex gap-1 bg-card/90 backdrop-blur-sm rounded-lg shadow-lg p-1.5 border border-border">
            <Button variant="ghost" size="icon" onClick={() => zoomIn()} title="Zoom In" className="h-8 w-8">
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => zoomOut()} title="Zoom Out" className="h-8 w-8">
              <ZoomOut className="h-4 w-4" />
            </Button>
            <div className="w-px bg-white/10 mx-1" />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsAddNodeModalOpen(true)}
              title="Add Node"
              className="h-8 w-8 text-cyan-400 hover:text-cyan-300"
            >
              <Plus className="h-4 w-4" />
            </Button>
            <div className="w-px bg-white/10 mx-1" />
            <Button variant="ghost" size="icon" onClick={() => fitView({ padding: 0.2, duration: 300 })} title="Fit to Screen" className="h-8 w-8">
              <Maximize className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={handleAutoLayout} title="Auto Layout" className="h-8 w-8">
              <LayoutGrid className="h-4 w-4" />
            </Button>
            <div className="w-px bg-white/10 mx-1" />
            <Button
              variant={isDrawMode ? 'default' : 'ghost'}
              size="icon"
              onClick={() => {
                setIsDrawMode(!isDrawMode)
                setSourceNodeId(null)
              }}
              title={isDrawMode ? 'Cancel Drawing' : 'Draw Connection'}
              className={`h-8 w-8 ${isDrawMode ? 'bg-amber-600 hover:bg-amber-700 text-white' : ''}`}
            >
              <GitBranch className="h-4 w-4" />
            </Button>
            <div className="w-px bg-white/10 mx-1" />
            <Button variant="ghost" size="icon" onClick={handleExportPng} title="Export PNG" className="h-8 w-8">
              <Download className="h-4 w-4" />
            </Button>
            <div className="w-px bg-white/10 mx-1" />
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRegenerate}
              disabled={isRegenerating}
              title="Regenerate Graph"
              className="h-8 w-8 text-amber-400 hover:text-amber-300"
            >
              <RefreshCw className={`h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
            </Button>
          </div>
          {isDrawMode && (
            <div className="mt-2 bg-amber-900/80 backdrop-blur-sm text-amber-200 text-xs px-3 py-1.5 rounded border border-amber-700/50">
              {sourceNodeId ? 'Click a target node...' : 'Click a source node...'}
            </div>
          )}
        </Panel>

        {/* Legend */}
        <Panel position="top-right">
          <div className="bg-card/90 backdrop-blur-sm rounded-lg shadow-lg p-3 text-xs border border-border max-w-[180px]">
            <p className="font-medium mb-2 text-foreground border-b border-border pb-1">Legend</p>
            <div className="space-y-2">
              <div>
                <p className="text-[10px] text-muted-foreground uppercase mb-1">Nodes</p>
                <div className="grid grid-cols-1 gap-1">
                  {legendItems.map(({ type, label, color }) => (
                    <div key={type} className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
                      <span className="text-muted-foreground truncate">{label}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="pt-1">
                <p className="text-[10px] text-muted-foreground uppercase mb-1">Edges</p>
                <div className="space-y-1">
                  {edgeLegend.map(({ type, color, style }) => (
                    <div key={type} className="flex items-center gap-2">
                      <div
                        className="w-4 h-0"
                        style={{
                          borderTop: `2px ${style} ${color}`,
                        }}
                      />
                      <span className="text-muted-foreground">{type}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </ReactFlow>

      {/* Selected Element Details */}
      {selectedElement && (
        <div className="absolute bottom-4 left-4 right-4 z-10 bg-card/95 backdrop-blur-sm rounded-lg shadow-lg p-4 border border-border">
          <div className="flex justify-between items-start">
            <div className="flex-1 min-w-0">
              <p className="text-xs text-muted-foreground uppercase tracking-wider">
                {selectedElement.type === 'node' ? (selectedElement.data.nodeType as string)?.replace(/_/g, ' ') || 'Node' : 'Connection'}
              </p>
              <p className="font-medium text-foreground text-lg truncate">{selectedElement.data.label as string}</p>

              {selectedElement.type === 'node' && (() => {
                const nodeType = selectedElement.data.nodeType as string
                const extra = (selectedElement.data.extra_data || {}) as Record<string, unknown>

                return (
                  <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
                    {/* Host nodes */}
                    {!!selectedElement.data.ipAddress && (
                      <>
                        <span className="text-muted-foreground">IP Address:</span>
                        <span className="text-foreground font-mono">{String(selectedElement.data.ipAddress)}</span>
                      </>
                    )}
                    <span className="text-muted-foreground">Type:</span>
                    <span className="text-foreground capitalize">{nodeType?.replace(/_/g, ' ')}</span>

                    {/* IP Address nodes */}
                    {nodeType === 'ip_address' && (
                      <>
                        {!!extra.direction && (
                          <>
                            <span className="text-muted-foreground">Direction:</span>
                            <span className="text-foreground capitalize">{String(extra.direction)}</span>
                          </>
                        )}
                        {!!extra.protocol && (
                          <>
                            <span className="text-muted-foreground">Protocol/Port:</span>
                            <span className="text-foreground font-mono">
                              {String(extra.protocol)}{extra.port ? `:${String(extra.port)}` : ''}
                            </span>
                          </>
                        )}
                        {!!extra.description && (
                          <>
                            <span className="text-muted-foreground">Description:</span>
                            <span className="text-foreground">{String(extra.description)}</span>
                          </>
                        )}
                        {!!extra.threat_intel_source && (
                          <>
                            <span className="text-muted-foreground">Threat Intel:</span>
                            <span className="text-foreground">{String(extra.threat_intel_source)}</span>
                          </>
                        )}
                        <span className="text-muted-foreground">Malicious:</span>
                        <span className={extra.is_malicious ? 'text-red-400 font-medium' : 'text-green-400'}>
                          {extra.is_malicious ? 'Yes' : 'No'}
                        </span>
                      </>
                    )}

                    {/* Malware nodes */}
                    {nodeType === 'malware' && (
                      <>
                        {!!extra.file_path && (
                          <>
                            <span className="text-muted-foreground">Path:</span>
                            <span className="text-foreground font-mono text-xs truncate">{String(extra.file_path)}</span>
                          </>
                        )}
                        {!!extra.malware_family && (
                          <>
                            <span className="text-muted-foreground">Family:</span>
                            <span className="text-foreground">{String(extra.malware_family)}</span>
                          </>
                        )}
                        {!!extra.threat_actor && (
                          <>
                            <span className="text-muted-foreground">Threat Actor:</span>
                            <span className="text-foreground">{String(extra.threat_actor)}</span>
                          </>
                        )}
                        {(!!extra.sha256 || !!extra.md5) && (
                          <>
                            <span className="text-muted-foreground">Hash:</span>
                            <span className="text-foreground font-mono text-xs truncate">
                              {extra.sha256 ? `SHA256: ${String(extra.sha256).slice(0, 16)}...` : `MD5: ${String(extra.md5)}`}
                            </span>
                          </>
                        )}
                        {!!extra.host_system && (
                          <>
                            <span className="text-muted-foreground">Host:</span>
                            <span className="text-foreground">{String(extra.host_system)}</span>
                          </>
                        )}
                      </>
                    )}

                    {/* Account nodes */}
                    {(nodeType === 'user' || nodeType === 'service_account') && (
                      <>
                        {!!extra.account_type && (
                          <>
                            <span className="text-muted-foreground">Account Type:</span>
                            <span className="text-foreground capitalize">{String(extra.account_type)}</span>
                          </>
                        )}
                        {!!extra.domain && (
                          <>
                            <span className="text-muted-foreground">Domain:</span>
                            <span className="text-foreground font-mono">{String(extra.domain)}</span>
                          </>
                        )}
                        {!!extra.sid && (
                          <>
                            <span className="text-muted-foreground">SID:</span>
                            <span className="text-foreground font-mono text-xs">{String(extra.sid)}</span>
                          </>
                        )}
                        <span className="text-muted-foreground">Privileged:</span>
                        <span className={extra.is_privileged ? 'text-amber-400 font-medium' : 'text-muted-foreground'}>
                          {extra.is_privileged ? 'Yes' : 'No'}
                        </span>
                        {!!extra.host_system && (
                          <>
                            <span className="text-muted-foreground">Host:</span>
                            <span className="text-foreground">{String(extra.host_system)}</span>
                          </>
                        )}
                        {!!extra.status && (
                          <>
                            <span className="text-muted-foreground">Status:</span>
                            <span className="text-foreground capitalize">{String(extra.status)}</span>
                          </>
                        )}
                      </>
                    )}

                    {/* Host indicator nodes */}
                    {nodeType === 'host_indicator' && (
                      <>
                        {!!extra.artifact_type && (
                          <>
                            <span className="text-muted-foreground">Artifact Type:</span>
                            <span className="text-foreground capitalize">{String(extra.artifact_type).replace(/_/g, ' ')}</span>
                          </>
                        )}
                        {!!extra.artifact_value && (
                          <>
                            <span className="text-muted-foreground">Value:</span>
                            <span className="text-foreground font-mono text-xs truncate">{String(extra.artifact_value)}</span>
                          </>
                        )}
                        {!!extra.notes && (
                          <>
                            <span className="text-muted-foreground">Notes:</span>
                            <span className="text-foreground text-xs">{String(extra.notes)}</span>
                          </>
                        )}
                        {!!extra.host_system && (
                          <>
                            <span className="text-muted-foreground">Host:</span>
                            <span className="text-foreground">{String(extra.host_system)}</span>
                          </>
                        )}
                        <span className="text-muted-foreground">Status:</span>
                        <span className={extra.remediated ? 'text-green-400' : extra.is_malicious ? 'text-red-400' : 'text-orange-400'}>
                          {extra.remediated ? 'Remediated' : extra.is_malicious ? 'Malicious' : 'Suspicious'}
                        </span>
                      </>
                    )}

                    {/* Containment status for host-type nodes */}
                    {(nodeType === 'workstation' || nodeType === 'server' || nodeType === 'domain_controller' || nodeType === 'web_server' || nodeType === 'file_server') && (
                      <>
                        <span className="text-muted-foreground">Status:</span>
                        <span
                          className={`font-medium ${selectedElement.data.containmentStatus === 'active'
                            ? 'text-red-400'
                            : selectedElement.data.containmentStatus === 'isolated'
                              ? 'text-orange-400'
                              : 'text-green-400'
                            }`}
                        >
                          {String(selectedElement.data.containmentStatus || 'Unknown')}
                        </span>
                      </>
                    )}

                    {!!selectedElement.data.correlation && (
                      <>
                        <span className="text-muted-foreground">Correlated:</span>
                        <div className="flex gap-1 flex-wrap">
                          {Object.entries(selectedElement.data.correlation as Record<string, number>)
                            .filter(([, v]) => v > 0)
                            .map(([k, v]) => (
                              <span key={k} className="text-xs bg-white/10 px-1.5 py-0.5 rounded">
                                {v} {k.replace(/_/g, ' ')}
                              </span>
                            ))}
                        </div>
                      </>
                    )}
                  </div>
                )
              })()}

              {selectedElement.type === 'edge' && (
                <div className="mt-2 space-y-1 text-sm">
                  <p className="text-muted-foreground capitalize">
                    Type: {(selectedElement.data.type as string)?.replace(/_/g, ' ')}
                  </p>
                  {!!selectedElement.data.mitreTactic && (
                    <p className="text-purple-400">
                      MITRE: {String(selectedElement.data.mitreTactic)}
                      {!!selectedElement.data.mitreTechnique && ` (${String(selectedElement.data.mitreTechnique)})`}
                    </p>
                  )}
                  {!!(selectedElement.data as Record<string, unknown>).timeline_event_activity && (
                    <p className="text-muted-foreground text-xs mt-1">
                      <span className="text-foreground font-medium">Linked Event: </span>
                      {String((selectedElement.data as Record<string, unknown>).timeline_event_activity)}
                    </p>
                  )}
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedElement(null)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export function AttackGraphViewer({ incidentId }: AttackGraphViewerProps) {
  return (
    <ReactFlowProvider>
      <GraphInner incidentId={incidentId} />
    </ReactFlowProvider>
  )
}

export default AttackGraphViewer
