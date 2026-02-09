
export interface ParsedSheet {
    name: string
    headers: string[]
    rows: Record<string, any>[]
}

export interface ParseResponse {
    sheets: ParsedSheet[]
}

export type EntityType = 'timeline_events' | 'hosts' | 'accounts' | 'network_iocs' | 'host_iocs' | 'malware'

export interface ColumnMapping {
    [sheetName: string]: {
        targetEntity: EntityType
        fieldMapping: Record<string, string> // excelHeader -> dbField
    }
}

export const ENTITY_FIELDS: Record<EntityType, { value: string; label: string; required?: boolean }[]> = {
    timeline_events: [
        { value: 'timestamp', label: 'Timestamp' },
        { value: 'activity', label: 'Activity/Description', required: true },
        { value: 'hostname', label: 'Hostname' },
        { value: 'source', label: 'Source' },
        { value: 'mitre_tactic', label: 'MITRE Tactic' },
        { value: 'mitre_technique', label: 'MITRE Technique' },
    ],
    hosts: [
        { value: 'hostname', label: 'Hostname', required: true },
        { value: 'ip_address', label: 'IP Address' },
        { value: 'system_type', label: 'System Type' },
        { value: 'os_version', label: 'OS Version' },
        { value: 'evidence', label: 'Evidence' },
        { value: 'first_seen', label: 'First Seen' },
        { value: 'containment_status', label: 'Containment Status' },
    ],
    accounts: [
        { value: 'account_name', label: 'Account Name', required: true },
        { value: 'sid', label: 'SID' },
        { value: 'password', label: 'Password' },
        { value: 'datetime_seen', label: 'Time Seen' },
        { value: 'host_system', label: 'Host System' },
        { value: 'account_type', label: 'Account Type' },
        { value: 'is_privileged', label: 'Is Privileged' },
    ],
    network_iocs: [
        { value: 'dns_ip', label: 'Value (IP/Domain)', required: true },
        { value: 'timestamp', label: 'Timestamp' },
        { value: 'protocol', label: 'Protocol' },
        { value: 'source_host', label: 'Source Host' },
        { value: 'port', label: 'Port' },
        { value: 'direction', label: 'Direction' },
        { value: 'description', label: 'Description' },
    ],
    malware: [
        { value: 'file_name', label: 'File Name', required: true },
        { value: 'hash', label: 'Hash' },
        { value: 'path', label: 'Path' },
        { value: 'file_size', label: 'Size (Bytes)' },
        { value: 'creation_time', label: 'Creation Time' },
        { value: 'modification_time', label: 'Modification Time' },
        { value: 'host', label: 'Host' },
        { value: 'is_tool', label: 'Is Tool (True/False)' },
        { value: 'description', label: 'Description' },
    ],
    host_iocs: [
        { value: 'value', label: 'Artifact Value', required: true },
        { value: 'datetime', label: 'Timestamp' },
        { value: 'type', label: 'Artifact Type' },
        { value: 'host', label: 'Hostname' },
        { value: 'notes', label: 'Notes' },
    ]
}
