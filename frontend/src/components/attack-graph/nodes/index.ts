export { default as HostNode } from './HostNode'
export { default as DomainControllerNode } from './DomainControllerNode'
export { default as AttackerNode } from './AttackerNode'
export { default as C2ServerNode } from './C2ServerNode'
export { default as AccountNode } from './AccountNode'
export { default as IPAddressNode } from './IPAddressNode'
export { default as MalwareNode } from './MalwareNode'
export { default as CloudNode } from './CloudNode'
export { default as DatabaseNode } from './DatabaseNode'
export { default as DefaultNode } from './DefaultNode'

export type { GraphNodeData, GraphNode } from './HostNode'

/**
 * Maps attack graph node types to their corresponding React Flow custom node components.
 * Use this object as the `nodeTypes` prop on `<ReactFlow />`.
 *
 * Example:
 *   import { nodeTypes } from './nodes'
 *   <ReactFlow nodeTypes={nodeTypes} ... />
 */
import HostNode from './HostNode'
import DomainControllerNode from './DomainControllerNode'
import AttackerNode from './AttackerNode'
import C2ServerNode from './C2ServerNode'
import AccountNode from './AccountNode'
import IPAddressNode from './IPAddressNode'
import MalwareNode from './MalwareNode'
import CloudNode from './CloudNode'
import DatabaseNode from './DatabaseNode'
import DefaultNode from './DefaultNode'

export const nodeTypes = {
  // Host types -> HostNode
  workstation: HostNode,
  server: HostNode,
  file_server: HostNode,
  web_server: HostNode,

  // Specialized nodes
  domain_controller: DomainControllerNode,
  attacker: AttackerNode,
  c2_server: C2ServerNode,
  user: AccountNode,
  service_account: AccountNode,
  ip_address: IPAddressNode,
  malware: MalwareNode,
  cloud_resource: CloudNode,
  database: DatabaseNode,

  // Fallback types -> DefaultNode
  unknown: DefaultNode,
  other: DefaultNode,
  external: DefaultNode,
  default: DefaultNode,
} as const
