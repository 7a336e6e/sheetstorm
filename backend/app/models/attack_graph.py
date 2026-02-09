"""Attack graph visualization models"""
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class AttackGraphNode(BaseModel):
    """Attack graph node model."""
    __tablename__ = 'attack_graph_nodes'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    node_type = Column(String(50), nullable=False)
    label = Column(String(255), nullable=False)
    compromised_host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id'))
    compromised_account_id = Column(UUID(as_uuid=True), ForeignKey('compromised_accounts.id'))
    position_x = Column(Float, default=0)
    position_y = Column(Float, default=0)
    is_initial_access = Column(Boolean, default=False)
    is_objective = Column(Boolean, default=False)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='attack_graph_nodes')
    compromised_host = relationship('CompromisedHost', back_populates='graph_nodes')
    compromised_account = relationship('CompromisedAccount', back_populates='graph_nodes')
    creator = relationship('User')
    outgoing_edges = relationship('AttackGraphEdge', back_populates='source_node', foreign_keys='AttackGraphEdge.source_node_id', cascade='all, delete-orphan')
    incoming_edges = relationship('AttackGraphEdge', back_populates='target_node', foreign_keys='AttackGraphEdge.target_node_id', cascade='all, delete-orphan')

    NODE_TYPES = [
        'workstation', 'server', 'domain_controller', 'attacker', 'c2_server',
        'cloud_resource', 'user', 'service_account', 'external', 'unknown',
        'ip_address', 'malware', 'host_indicator', 'database', 'web_server', 'file_server'
    ]

    def __repr__(self):
        return f'<AttackGraphNode {self.node_type}: {self.label}>'

    def to_dict(self):
        """Convert to dictionary for Cytoscape.js."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None

        # Cytoscape.js format
        data['cytoscape'] = {
            'data': {
                'id': str(self.id),
                'label': self.label,
                'type': self.node_type,
                'isInitialAccess': self.is_initial_access,
                'isObjective': self.is_objective,
                'hasAdminCompromise': self.extra_data.get('has_admin_compromise', False) if self.extra_data else False,
                'containmentStatus': self.extra_data.get('containment_status') if self.extra_data else None,
                'compromisedHostId': str(self.compromised_host_id) if self.compromised_host_id else None,
                'compromisedAccountId': str(self.compromised_account_id) if self.compromised_account_id else None,
            },
            'position': {
                'x': self.position_x,
                'y': self.position_y
            }
        }

        return data


class AttackGraphEdge(BaseModel):
    """Attack graph edge model."""
    __tablename__ = 'attack_graph_edges'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey('attack_graph_nodes.id', ondelete='CASCADE'), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey('attack_graph_nodes.id', ondelete='CASCADE'), nullable=False)
    edge_type = Column(String(50), nullable=False)
    label = Column(String(255))
    mitre_tactic = Column(String(100))
    mitre_technique = Column(String(20))
    timestamp = Column(DateTime(timezone=True))
    description = Column(Text)
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='attack_graph_edges')
    source_node = relationship('AttackGraphNode', back_populates='outgoing_edges', foreign_keys=[source_node_id])
    target_node = relationship('AttackGraphNode', back_populates='incoming_edges', foreign_keys=[target_node_id])
    creator = relationship('User')

    EDGE_TYPES = [
        'lateral_movement', 'credential_theft', 'data_exfiltration', 'command_control',
        'initial_access', 'privilege_escalation', 'persistence', 'discovery',
        'execution', 'defense_evasion', 'collection', 'associated_with'
    ]

    def __repr__(self):
        return f'<AttackGraphEdge {self.edge_type}: {self.source_node_id} -> {self.target_node_id}>'

    def to_dict(self):
        """Convert to dictionary for Cytoscape.js."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None

        # Cytoscape.js format
        data['cytoscape'] = {
            'data': {
                'id': str(self.id),
                'source': str(self.source_node_id),
                'target': str(self.target_node_id),
                'label': self.label or self.edge_type,
                'type': self.edge_type,
                'mitreTactic': self.mitre_tactic,
                'mitreTechnique': self.mitre_technique,
            }
        }

        return data
