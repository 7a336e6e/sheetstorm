"""Timeline event model"""
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class TimelineEvent(BaseModel):
    """Timeline event model for incident chronology."""
    __tablename__ = 'timeline_events'

    incident_id = Column(UUID(as_uuid=True), ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    # Host correlation - both FK and string for backwards compatibility
    host_id = Column(UUID(as_uuid=True), ForeignKey('compromised_hosts.id', ondelete='SET NULL'), nullable=True)
    hostname = Column(String(255))  # Keep for backwards compatibility / display
    activity = Column(Text, nullable=False)
    source = Column(String(255))
    mitre_tactic = Column(String(100))
    mitre_technique = Column(String(20))
    phase = Column(Integer)
    is_key_event = Column(Boolean, default=False)
    is_ioc = Column(Boolean, default=False)  # Flag if marked as IOC
    extra_data = Column(JSONB, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    incident = relationship('Incident', back_populates='timeline_events')
    host = relationship('CompromisedHost', back_populates='timeline_events', foreign_keys=[host_id])
    creator = relationship('User')
    host_indicators = relationship('HostBasedIndicator', back_populates='source_event', lazy='dynamic')

    # MITRE ATT&CK tactics
    MITRE_TACTICS = [
        'reconnaissance',
        'resource-development',
        'initial-access',
        'execution',
        'persistence',
        'privilege-escalation',
        'defense-evasion',
        'credential-access',
        'discovery',
        'lateral-movement',
        'collection',
        'command-and-control',
        'exfiltration',
        'impact'
    ]

    # MITRE ATT&CK techniques by tactic
    MITRE_TECHNIQUES = {
        'reconnaissance': [
            ('T1595', 'Active Scanning'),
            ('T1592', 'Gather Victim Host Information'),
            ('T1589', 'Gather Victim Identity Information'),
            ('T1590', 'Gather Victim Network Information'),
            ('T1591', 'Gather Victim Org Information'),
            ('T1598', 'Phishing for Information'),
            ('T1597', 'Search Closed Sources'),
            ('T1596', 'Search Open Technical Databases'),
            ('T1593', 'Search Open Websites/Domains'),
            ('T1594', 'Search Victim-Owned Websites'),
        ],
        'resource-development': [
            ('T1583', 'Acquire Infrastructure'),
            ('T1586', 'Compromise Accounts'),
            ('T1584', 'Compromise Infrastructure'),
            ('T1587', 'Develop Capabilities'),
            ('T1585', 'Establish Accounts'),
            ('T1588', 'Obtain Capabilities'),
            ('T1608', 'Stage Capabilities'),
        ],
        'initial-access': [
            ('T1189', 'Drive-by Compromise'),
            ('T1190', 'Exploit Public-Facing Application'),
            ('T1133', 'External Remote Services'),
            ('T1200', 'Hardware Additions'),
            ('T1566', 'Phishing'),
            ('T1091', 'Replication Through Removable Media'),
            ('T1195', 'Supply Chain Compromise'),
            ('T1199', 'Trusted Relationship'),
            ('T1078', 'Valid Accounts'),
        ],
        'execution': [
            ('T1059', 'Command and Scripting Interpreter'),
            ('T1609', 'Container Administration Command'),
            ('T1610', 'Deploy Container'),
            ('T1203', 'Exploitation for Client Execution'),
            ('T1559', 'Inter-Process Communication'),
            ('T1106', 'Native API'),
            ('T1053', 'Scheduled Task/Job'),
            ('T1129', 'Shared Modules'),
            ('T1072', 'Software Deployment Tools'),
            ('T1569', 'System Services'),
            ('T1204', 'User Execution'),
            ('T1047', 'Windows Management Instrumentation'),
        ],
        'persistence': [
            ('T1098', 'Account Manipulation'),
            ('T1197', 'BITS Jobs'),
            ('T1547', 'Boot or Logon Autostart Execution'),
            ('T1037', 'Boot or Logon Initialization Scripts'),
            ('T1176', 'Browser Extensions'),
            ('T1554', 'Compromise Client Software Binary'),
            ('T1136', 'Create Account'),
            ('T1543', 'Create or Modify System Process'),
            ('T1546', 'Event Triggered Execution'),
            ('T1133', 'External Remote Services'),
            ('T1574', 'Hijack Execution Flow'),
            ('T1525', 'Implant Internal Image'),
            ('T1556', 'Modify Authentication Process'),
            ('T1137', 'Office Application Startup'),
            ('T1542', 'Pre-OS Boot'),
            ('T1053', 'Scheduled Task/Job'),
            ('T1505', 'Server Software Component'),
            ('T1205', 'Traffic Signaling'),
            ('T1078', 'Valid Accounts'),
        ],
        'privilege-escalation': [
            ('T1548', 'Abuse Elevation Control Mechanism'),
            ('T1134', 'Access Token Manipulation'),
            ('T1547', 'Boot or Logon Autostart Execution'),
            ('T1037', 'Boot or Logon Initialization Scripts'),
            ('T1543', 'Create or Modify System Process'),
            ('T1484', 'Domain Policy Modification'),
            ('T1611', 'Escape to Host'),
            ('T1546', 'Event Triggered Execution'),
            ('T1068', 'Exploitation for Privilege Escalation'),
            ('T1574', 'Hijack Execution Flow'),
            ('T1055', 'Process Injection'),
            ('T1053', 'Scheduled Task/Job'),
            ('T1078', 'Valid Accounts'),
        ],
        'defense-evasion': [
            ('T1548', 'Abuse Elevation Control Mechanism'),
            ('T1134', 'Access Token Manipulation'),
            ('T1197', 'BITS Jobs'),
            ('T1612', 'Build Image on Host'),
            ('T1140', 'Deobfuscate/Decode Files'),
            ('T1610', 'Deploy Container'),
            ('T1006', 'Direct Volume Access'),
            ('T1484', 'Domain Policy Modification'),
            ('T1480', 'Execution Guardrails'),
            ('T1211', 'Exploitation for Defense Evasion'),
            ('T1222', 'File and Directory Permissions Modification'),
            ('T1564', 'Hide Artifacts'),
            ('T1574', 'Hijack Execution Flow'),
            ('T1562', 'Impair Defenses'),
            ('T1070', 'Indicator Removal'),
            ('T1202', 'Indirect Command Execution'),
            ('T1036', 'Masquerading'),
            ('T1556', 'Modify Authentication Process'),
            ('T1578', 'Modify Cloud Compute Infrastructure'),
            ('T1112', 'Modify Registry'),
            ('T1601', 'Modify System Image'),
            ('T1599', 'Network Boundary Bridging'),
            ('T1027', 'Obfuscated Files or Information'),
            ('T1542', 'Pre-OS Boot'),
            ('T1055', 'Process Injection'),
            ('T1207', 'Rogue Domain Controller'),
            ('T1014', 'Rootkit'),
            ('T1218', 'System Binary Proxy Execution'),
            ('T1216', 'System Script Proxy Execution'),
            ('T1221', 'Template Injection'),
            ('T1205', 'Traffic Signaling'),
            ('T1127', 'Trusted Developer Utilities'),
            ('T1535', 'Unused/Unsupported Cloud Regions'),
            ('T1550', 'Use Alternate Authentication Material'),
            ('T1078', 'Valid Accounts'),
            ('T1497', 'Virtualization/Sandbox Evasion'),
            ('T1600', 'Weaken Encryption'),
            ('T1220', 'XSL Script Processing'),
        ],
        'credential-access': [
            ('T1557', 'Adversary-in-the-Middle'),
            ('T1110', 'Brute Force'),
            ('T1555', 'Credentials from Password Stores'),
            ('T1212', 'Exploitation for Credential Access'),
            ('T1187', 'Forced Authentication'),
            ('T1606', 'Forge Web Credentials'),
            ('T1056', 'Input Capture'),
            ('T1556', 'Modify Authentication Process'),
            ('T1111', 'Multi-Factor Authentication Interception'),
            ('T1621', 'Multi-Factor Authentication Request Generation'),
            ('T1040', 'Network Sniffing'),
            ('T1003', 'OS Credential Dumping'),
            ('T1528', 'Steal Application Access Token'),
            ('T1558', 'Steal or Forge Kerberos Tickets'),
            ('T1539', 'Steal Web Session Cookie'),
            ('T1552', 'Unsecured Credentials'),
        ],
        'discovery': [
            ('T1087', 'Account Discovery'),
            ('T1010', 'Application Window Discovery'),
            ('T1217', 'Browser Information Discovery'),
            ('T1580', 'Cloud Infrastructure Discovery'),
            ('T1538', 'Cloud Service Dashboard'),
            ('T1526', 'Cloud Service Discovery'),
            ('T1613', 'Container and Resource Discovery'),
            ('T1482', 'Domain Trust Discovery'),
            ('T1083', 'File and Directory Discovery'),
            ('T1615', 'Group Policy Discovery'),
            ('T1046', 'Network Service Discovery'),
            ('T1135', 'Network Share Discovery'),
            ('T1040', 'Network Sniffing'),
            ('T1201', 'Password Policy Discovery'),
            ('T1120', 'Peripheral Device Discovery'),
            ('T1069', 'Permission Groups Discovery'),
            ('T1057', 'Process Discovery'),
            ('T1012', 'Query Registry'),
            ('T1018', 'Remote System Discovery'),
            ('T1518', 'Software Discovery'),
            ('T1082', 'System Information Discovery'),
            ('T1614', 'System Location Discovery'),
            ('T1016', 'System Network Configuration Discovery'),
            ('T1049', 'System Network Connections Discovery'),
            ('T1033', 'System Owner/User Discovery'),
            ('T1007', 'System Service Discovery'),
            ('T1124', 'System Time Discovery'),
            ('T1497', 'Virtualization/Sandbox Evasion'),
        ],
        'lateral-movement': [
            ('T1210', 'Exploitation of Remote Services'),
            ('T1534', 'Internal Spearphishing'),
            ('T1570', 'Lateral Tool Transfer'),
            ('T1563', 'Remote Service Session Hijacking'),
            ('T1021', 'Remote Services'),
            ('T1091', 'Replication Through Removable Media'),
            ('T1072', 'Software Deployment Tools'),
            ('T1080', 'Taint Shared Content'),
            ('T1550', 'Use Alternate Authentication Material'),
        ],
        'collection': [
            ('T1557', 'Adversary-in-the-Middle'),
            ('T1560', 'Archive Collected Data'),
            ('T1123', 'Audio Capture'),
            ('T1119', 'Automated Collection'),
            ('T1185', 'Browser Session Hijacking'),
            ('T1115', 'Clipboard Data'),
            ('T1530', 'Data from Cloud Storage'),
            ('T1602', 'Data from Configuration Repository'),
            ('T1213', 'Data from Information Repositories'),
            ('T1005', 'Data from Local System'),
            ('T1039', 'Data from Network Shared Drive'),
            ('T1025', 'Data from Removable Media'),
            ('T1074', 'Data Staged'),
            ('T1114', 'Email Collection'),
            ('T1056', 'Input Capture'),
            ('T1113', 'Screen Capture'),
            ('T1125', 'Video Capture'),
        ],
        'command-and-control': [
            ('T1071', 'Application Layer Protocol'),
            ('T1092', 'Communication Through Removable Media'),
            ('T1132', 'Data Encoding'),
            ('T1001', 'Data Obfuscation'),
            ('T1568', 'Dynamic Resolution'),
            ('T1573', 'Encrypted Channel'),
            ('T1008', 'Fallback Channels'),
            ('T1105', 'Ingress Tool Transfer'),
            ('T1104', 'Multi-Stage Channels'),
            ('T1095', 'Non-Application Layer Protocol'),
            ('T1571', 'Non-Standard Port'),
            ('T1572', 'Protocol Tunneling'),
            ('T1090', 'Proxy'),
            ('T1219', 'Remote Access Software'),
            ('T1205', 'Traffic Signaling'),
            ('T1102', 'Web Service'),
        ],
        'exfiltration': [
            ('T1020', 'Automated Exfiltration'),
            ('T1030', 'Data Transfer Size Limits'),
            ('T1048', 'Exfiltration Over Alternative Protocol'),
            ('T1041', 'Exfiltration Over C2 Channel'),
            ('T1011', 'Exfiltration Over Other Network Medium'),
            ('T1052', 'Exfiltration Over Physical Medium'),
            ('T1567', 'Exfiltration Over Web Service'),
            ('T1029', 'Scheduled Transfer'),
            ('T1537', 'Transfer Data to Cloud Account'),
        ],
        'impact': [
            ('T1531', 'Account Access Removal'),
            ('T1485', 'Data Destruction'),
            ('T1486', 'Data Encrypted for Impact'),
            ('T1565', 'Data Manipulation'),
            ('T1491', 'Defacement'),
            ('T1561', 'Disk Wipe'),
            ('T1499', 'Endpoint Denial of Service'),
            ('T1495', 'Firmware Corruption'),
            ('T1490', 'Inhibit System Recovery'),
            ('T1498', 'Network Denial of Service'),
            ('T1496', 'Resource Hijacking'),
            ('T1489', 'Service Stop'),
            ('T1529', 'System Shutdown/Reboot'),
        ],
    }

    def __repr__(self):
        return f'<TimelineEvent {self.timestamp}: {self.activity[:50]}>'

    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['creator'] = {'id': str(self.creator.id), 'name': self.creator.name} if self.creator else None
        data['host'] = self.host.to_dict() if self.host else None
        # Keep hostname for backwards compatibility
        if not data.get('hostname') and self.host:
            data['hostname'] = self.host.hostname
        return data
