"""Windows Event IDs reference data for incident response.

Comprehensive catalogue of security-relevant Windows Event IDs across
Security, Sysmon, PowerShell, WMI, AppLocker, Defender, and system logs.
"""

WINDOWS_EVENT_IDS = [
    # === Authentication & Logon ===
    {"event_id": 4624, "description": "Successful logon", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4625, "description": "Failed logon attempt", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4634, "description": "Account logoff", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4647, "description": "User-initiated logoff", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4648, "description": "Logon attempted using explicit credentials (runas)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4768, "description": "Kerberos TGT requested (AS-REQ)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4769, "description": "Kerberos service ticket requested (TGS-REQ)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4770, "description": "Kerberos service ticket was renewed", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4771, "description": "Kerberos pre-authentication failed", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4776, "description": "NTLM authentication attempted (credential validation)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4778, "description": "Session reconnected (RDP session reconnect)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4779, "description": "Session disconnected (RDP session disconnect)", "category": "Authentication", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},

    # === Account Management ===
    {"event_id": 4720, "description": "User account created", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4722, "description": "User account enabled", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4723, "description": "Password change attempted", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4724, "description": "Password reset attempted", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4725, "description": "User account disabled", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4726, "description": "User account deleted", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4728, "description": "Member added to security-enabled global group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4729, "description": "Member removed from security-enabled global group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4732, "description": "Member added to security-enabled local group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4733, "description": "Member removed from security-enabled local group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4735, "description": "Security-enabled local group changed", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4737, "description": "Security-enabled global group was changed", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4738, "description": "User account was changed", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4740, "description": "User account was locked out", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4741, "description": "Computer account was created", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4742, "description": "Computer account was changed", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4743, "description": "Computer account was deleted", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4756, "description": "Member added to security-enabled universal group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4757, "description": "Member removed from security-enabled universal group", "category": "Account Management", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},

    # === Privilege Use ===
    {"event_id": 4672, "description": "Special privileges assigned to new logon (admin logon)", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4673, "description": "Privileged service was called", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4674, "description": "Operation attempted on privileged object", "category": "Privilege Use", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},

    # === Process Tracking ===
    {"event_id": 4688, "description": "New process created (with command line if enabled)", "category": "Process Tracking", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4689, "description": "Process exited/terminated", "category": "Process Tracking", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4696, "description": "Primary token assigned to process (token manipulation)", "category": "Process Tracking", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},

    # === Object Access ===
    {"event_id": 4656, "description": "Handle to an object was requested", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4657, "description": "Registry value was modified", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4658, "description": "Handle to an object was closed", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4660, "description": "Object was deleted", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4663, "description": "Attempt to access object (file/registry/kernel)", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4670, "description": "Permissions on object were changed", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4985, "description": "State of a transaction changed (transactional NTFS)", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 5140, "description": "Network share was accessed", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 5142, "description": "Network share was added", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 5145, "description": "Network share object was checked for access (detailed share access)", "category": "Object Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},

    # === Policy & Audit Changes ===
    {"event_id": 1102, "description": "Audit log was cleared", "category": "Policy Change", "provider": "Microsoft-Windows-Eventlog", "severity": "critical"},
    {"event_id": 4697, "description": "Service was installed (service creation)", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4698, "description": "Scheduled task was created", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4699, "description": "Scheduled task was deleted", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4700, "description": "Scheduled task was enabled", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4701, "description": "Scheduled task was disabled", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4702, "description": "Scheduled task was updated", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4706, "description": "New trust was created to a domain", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4707, "description": "Trust to a domain was removed", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4713, "description": "Kerberos policy was changed", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4719, "description": "System audit policy was changed", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4739, "description": "Domain policy was changed", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4946, "description": "Windows Firewall exception list rule was added", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4947, "description": "Windows Firewall exception list rule was modified", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4948, "description": "Windows Firewall exception list rule was deleted", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4950, "description": "Windows Firewall setting was changed", "category": "Policy Change", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},

    # === System Events ===
    {"event_id": 7034, "description": "Service crashed unexpectedly", "category": "System", "provider": "Service Control Manager", "severity": "warning"},
    {"event_id": 7036, "description": "Service entered running/stopped state", "category": "System", "provider": "Service Control Manager", "severity": "info"},
    {"event_id": 7040, "description": "Service start type changed (e.g., auto to disabled)", "category": "System", "provider": "Service Control Manager", "severity": "warning"},
    {"event_id": 7045, "description": "New service was installed in the system", "category": "System", "provider": "Service Control Manager", "severity": "critical"},
    {"event_id": 6005, "description": "Event Log service was started (system boot)", "category": "System", "provider": "EventLog", "severity": "info"},
    {"event_id": 6006, "description": "Event Log service was stopped (system shutdown)", "category": "System", "provider": "EventLog", "severity": "info"},
    {"event_id": 6008, "description": "Previous system shutdown was unexpected (crash/BSOD)", "category": "System", "provider": "EventLog", "severity": "warning"},
    {"event_id": 1074, "description": "System shutdown/restart initiated by process", "category": "System", "provider": "USER32", "severity": "info"},

    # === Sysmon Events ===
    {"event_id": 1, "description": "Process creation with full command line, hashes, parent process", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 2, "description": "File creation time changed (timestomping)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 3, "description": "Network connection established (source/dest IP:port)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 4, "description": "Sysmon service state changed", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 5, "description": "Process terminated", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 6, "description": "Driver loaded (with signature status)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 7, "description": "Image/DLL loaded by process (with hash and signature)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 8, "description": "CreateRemoteThread detected (code injection)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 9, "description": "RawAccessRead detected (direct disk access, e.g., Mimikatz SAM dump)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 10, "description": "ProcessAccess (e.g., LSASS memory access for credential dumping)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 11, "description": "File created or overwritten", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 12, "description": "Registry object added or deleted", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 13, "description": "Registry value set", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 14, "description": "Registry key/value renamed", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 15, "description": "FileCreateStreamHash (alternate data stream created)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 16, "description": "Sysmon configuration changed", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 17, "description": "Named pipe created", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 18, "description": "Named pipe connected", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 19, "description": "WMI Event Filter registered", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 20, "description": "WMI Event Consumer registered", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 21, "description": "WMI Event ConsumerToFilter activity (binding)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 22, "description": "DNS query event with query name and results", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 23, "description": "File deleted (with archived copy)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 24, "description": "Clipboard content captured", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 25, "description": "Process tampering detected (process hollowing/herpaderping)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "critical"},
    {"event_id": 26, "description": "File delete logged (without archiving)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},
    {"event_id": 27, "description": "File block executable (blocked by Sysmon policy)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 28, "description": "File block shredding (blocked by Sysmon policy)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "warning"},
    {"event_id": 29, "description": "File executable detected (creation of PE on disk)", "category": "Sysmon", "provider": "Microsoft-Windows-Sysmon", "severity": "info"},

    # === PowerShell ===
    {"event_id": 4103, "description": "PowerShell Module Logging — records pipeline execution details", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 4104, "description": "PowerShell Script Block Logging — captures full script content", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "warning"},
    {"event_id": 4105, "description": "PowerShell script block invocation started", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 4106, "description": "PowerShell script block invocation completed", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 40961, "description": "PowerShell console started (engine lifecycle)", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 40962, "description": "PowerShell console ready for user input", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "info"},
    {"event_id": 53504, "description": "PowerShell remoting session established (WinRM)", "category": "PowerShell", "provider": "Microsoft-Windows-PowerShell", "severity": "warning"},
    {"event_id": 400, "description": "PowerShell engine started (legacy, Windows PowerShell log)", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},
    {"event_id": 403, "description": "PowerShell engine stopped (legacy, Windows PowerShell log)", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},
    {"event_id": 800, "description": "PowerShell pipeline executed (legacy, includes partial command)", "category": "PowerShell", "provider": "PowerShell", "severity": "info"},

    # === WMI ===
    {"event_id": 5857, "description": "WMI Activity provider started — indicates WMI provider load", "category": "WMI", "provider": "Microsoft-Windows-WMI-Activity", "severity": "info"},
    {"event_id": 5858, "description": "WMI Activity query error — failed WMI operation", "category": "WMI", "provider": "Microsoft-Windows-WMI-Activity", "severity": "warning"},
    {"event_id": 5859, "description": "WMI Event subscription — permanent event registered", "category": "WMI", "provider": "Microsoft-Windows-WMI-Activity", "severity": "critical"},
    {"event_id": 5860, "description": "WMI temporary event subscription registered", "category": "WMI", "provider": "Microsoft-Windows-WMI-Activity", "severity": "warning"},
    {"event_id": 5861, "description": "WMI permanent subscription activated (persistence mechanism)", "category": "WMI", "provider": "Microsoft-Windows-WMI-Activity", "severity": "critical"},

    # === Windows Defender ===
    {"event_id": 1006, "description": "Defender found malware or unwanted software", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},
    {"event_id": 1007, "description": "Defender took action against malware", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "warning"},
    {"event_id": 1008, "description": "Defender failed to take action against malware", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},
    {"event_id": 1013, "description": "Defender deleted history of malware (evidence destruction)", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "warning"},
    {"event_id": 1116, "description": "Defender detected malware or unwanted software (detection)", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},
    {"event_id": 1117, "description": "Defender took action on malware (remediation)", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "warning"},
    {"event_id": 5001, "description": "Defender real-time protection was disabled", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},
    {"event_id": 5004, "description": "Defender real-time protection configuration changed", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "warning"},
    {"event_id": 5007, "description": "Defender Antimalware platform configuration changed", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "warning"},
    {"event_id": 5010, "description": "Defender scanning for malware disabled", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},
    {"event_id": 5012, "description": "Defender scanning for viruses disabled", "category": "Windows Defender", "provider": "Microsoft-Windows-Windows Defender", "severity": "critical"},

    # === AppLocker ===
    {"event_id": 8003, "description": "AppLocker allowed execution of a packaged app", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "info"},
    {"event_id": 8004, "description": "AppLocker allowed execution of a packaged app installer", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "info"},
    {"event_id": 8006, "description": "AppLocker would have blocked a packaged app (audit mode)", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "warning"},
    {"event_id": 8007, "description": "AppLocker would have blocked a packaged app installer (audit)", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "warning"},
    {"event_id": 8002, "description": "AppLocker blocked execution of a file (enforcement mode)", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "critical"},
    {"event_id": 8005, "description": "AppLocker allowed execution of a script/MSI", "category": "AppLocker", "provider": "Microsoft-Windows-AppLocker", "severity": "info"},

    # === BITS (Background Intelligent Transfer Service) ===
    {"event_id": 3, "description": "BITS service created a new transfer job", "category": "BITS", "provider": "Microsoft-Windows-Bits-Client", "severity": "info"},
    {"event_id": 59, "description": "BITS transfer initiated (includes URL and file path)", "category": "BITS", "provider": "Microsoft-Windows-Bits-Client", "severity": "warning"},
    {"event_id": 60, "description": "BITS transfer completed", "category": "BITS", "provider": "Microsoft-Windows-Bits-Client", "severity": "info"},
    {"event_id": 61, "description": "BITS transfer stopped/cancelled", "category": "BITS", "provider": "Microsoft-Windows-Bits-Client", "severity": "info"},

    # === Remote Desktop / Terminal Services ===
    {"event_id": 21, "description": "Remote Desktop Services session logon succeeded", "category": "Remote Desktop", "provider": "Microsoft-Windows-TerminalServices-LocalSessionManager", "severity": "info"},
    {"event_id": 22, "description": "Remote Desktop Services shell started", "category": "Remote Desktop", "provider": "Microsoft-Windows-TerminalServices-LocalSessionManager", "severity": "info"},
    {"event_id": 24, "description": "Remote Desktop session disconnected", "category": "Remote Desktop", "provider": "Microsoft-Windows-TerminalServices-LocalSessionManager", "severity": "info"},
    {"event_id": 25, "description": "Remote Desktop session reconnected", "category": "Remote Desktop", "provider": "Microsoft-Windows-TerminalServices-LocalSessionManager", "severity": "info"},
    {"event_id": 1149, "description": "Remote Desktop connection authentication succeeded", "category": "Remote Desktop", "provider": "Microsoft-Windows-TerminalServices-RemoteConnectionManager", "severity": "info"},

    # === Credential Access ===
    {"event_id": 4964, "description": "Special groups assigned to a new logon (custom security groups)", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 4782, "description": "Password hash of account was accessed", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 4798, "description": "User's local group membership was enumerated", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},
    {"event_id": 4799, "description": "Security-enabled local group membership enumerated", "category": "Credential Access", "provider": "Microsoft-Windows-Security-Auditing", "severity": "info"},

    # === Group Policy ===
    {"event_id": 4739, "description": "Domain policy was changed", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},
    {"event_id": 5136, "description": "Directory service object was modified", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 5137, "description": "Directory service object was created", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 5138, "description": "Directory service object was undeleted", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 5139, "description": "Directory service object was moved", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "warning"},
    {"event_id": 5141, "description": "Directory service object was deleted", "category": "Group Policy", "provider": "Microsoft-Windows-Security-Auditing", "severity": "critical"},

    # === Task Scheduler ===
    {"event_id": 106, "description": "Task Scheduler — scheduled task registered", "category": "Task Scheduler", "provider": "Microsoft-Windows-TaskScheduler", "severity": "warning"},
    {"event_id": 140, "description": "Task Scheduler — scheduled task updated", "category": "Task Scheduler", "provider": "Microsoft-Windows-TaskScheduler", "severity": "info"},
    {"event_id": 141, "description": "Task Scheduler — scheduled task removed", "category": "Task Scheduler", "provider": "Microsoft-Windows-TaskScheduler", "severity": "info"},
    {"event_id": 200, "description": "Task Scheduler — task action started", "category": "Task Scheduler", "provider": "Microsoft-Windows-TaskScheduler", "severity": "info"},
    {"event_id": 201, "description": "Task Scheduler — task action completed", "category": "Task Scheduler", "provider": "Microsoft-Windows-TaskScheduler", "severity": "info"},

    # === Windows Remote Management (WinRM) ===
    {"event_id": 6, "description": "WinRM session created (inbound remote shell)", "category": "WinRM", "provider": "Microsoft-Windows-WinRM", "severity": "warning"},
    {"event_id": 91, "description": "WinRM session opened (inbound PS remoting)", "category": "WinRM", "provider": "Microsoft-Windows-WinRM", "severity": "warning"},
    {"event_id": 168, "description": "WinRM authentication succeeded", "category": "WinRM", "provider": "Microsoft-Windows-WinRM", "severity": "info"},
]

EVENT_CATEGORIES = sorted(set(e["category"] for e in WINDOWS_EVENT_IDS))
EVENT_SEVERITIES = ['info', 'warning', 'critical']
