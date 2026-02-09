"""AI service for generating incident reports and summaries using LLM providers."""
import json
from typing import Optional, Dict, Any, List
from flask import current_app
from app.services.encryption_service import EncryptionService


class AIService:
    """Service for AI-powered report generation using OpenAI or Google Gemini.

    Each report type uses a specialized system prompt to ensure the AI generates
    content matching the required format. Output is always Markdown which is then
    converted to HTML→PDF downstream.
    """

    # ── System Prompts ──────────────────────────────────────────────────
    SYSTEM_PROMPT_BASE = (
        "You are an expert cybersecurity incident response analyst working for a "
        "professional DFIR (Digital Forensics & Incident Response) team. You produce "
        "clear, accurate, evidence-based reports. Always output valid Markdown. "
        "Use tables, headings, bullet lists, and bold text for readability. "
        "Never fabricate data — only reference information provided to you. "
        "If data is missing, say so explicitly rather than inventing values."
    )

    REPORT_PROMPTS: Dict[str, str] = {
        "executive": """Generate a professional **Executive Summary Report** for the security incident below.

## Structure your report EXACTLY as follows (use these Markdown headings):

### 1. Incident Overview
- One-paragraph synopsis: what happened, when, and how severe it is.

### 2. Business Impact Assessment
- Which systems/services were affected
- Estimated downtime or data exposure
- Regulatory or compliance implications

### 3. Key Findings
- Bullet-point list of the most critical discoveries
- Initial access vector if identifiable
- Scope of compromise (number of hosts, accounts, etc.)

### 4. Current Status
- Incident phase and containment status
- Immediate actions already taken

### 5. Recommendations
- Prioritized list of next-step actions for leadership
- Resource requests if applicable

### 6. Risk Assessment
- Residual risk if recommendations are not followed
- Timeline for complete remediation

**IMPORTANT**: This report is for C-level executives and board members — avoid deep technical jargon. Use business language. Keep it concise (aim for 1–2 pages when rendered).""",

        "metrics": """Generate a detailed **Incident Metrics Report** with statistical analysis.

## Structure your report EXACTLY as follows:

### 1. Incident Summary Statistics
| Metric | Value |
|--------|-------|
| Total Timeline Events | (count) |
| Compromised Hosts | (count) |
| Compromised Accounts | (count) |
| Network IOCs | (count) |
| Host-Based IOCs | (count) |
| Malware/Tools Identified | (count) |

### 2. Timeline Analysis
- Time span of the incident (first event → last event)
- Peak activity periods
- Breakdown of events by phase/stage
- Events per host (table)

### 3. Attack Technique Coverage
- MITRE ATT&CK techniques observed (list as table with Tactic → Technique → Frequency)
- Coverage gaps in detection

### 4. Containment Metrics
- Number of hosts isolated vs. active vs. reimaged
- Account remediation status (active / disabled / reset / deleted)
- Percentage of IOCs addressed

### 5. Response Performance
- Time-to-detect
- Time-to-contain
- Current phase and progression

### 6. Trend Observations
- Patterns observed in attacker behavior
- Repeat indicators or techniques

**IMPORTANT**: This is a data-driven report. Use tables and concrete numbers wherever possible. Do not editorialize — present facts.""",

        "ioc": """Generate a comprehensive **Indicators of Compromise (IOC) Analysis Report**.

## Structure your report EXACTLY as follows:

### 1. IOC Executive Summary
- Total IOCs identified by category
- Overall threat assessment level

### 2. Network Indicators
For each network IOC, present in a table:
| DNS/IP | Protocol | Port | Direction | Description | Threat Level |
|--------|----------|------|-----------|-------------|--------------|

- Analysis of C2 infrastructure patterns
- Geo-IP observations (if inferable from IPs/domains)

### 3. Host-Based Indicators
For each host IOC, present in a table:
| Type | Value (truncated) | Host | Malicious | Remediated |
|------|-------------------|------|-----------|------------|

- Persistence mechanisms identified
- Registry/scheduled task/service analysis

### 4. Malware & Tools Analysis
For each malware/tool:
| File Name | SHA256 | Host | Family | Actor | Description |
|-----------|--------|------|--------|-------|-------------|

- Malware family analysis
- Tool usage patterns (legitimate tools used maliciously)

### 5. Compromised Accounts
| Account | Type | Domain | Privileged | Status | Host |
|---------|------|--------|------------|--------|------|

- Privileged account compromise assessment
- Lateral movement via credentials

### 6. Compromised Hosts
| Hostname | IP | OS | System Type | Containment | First Seen |
|----------|----|----|-------------|-------------|------------|

### 7. IOC Correlation Analysis
- Cross-reference between network IOCs and host IOCs
- Common patterns across compromised hosts
- Attack chain reconstruction from IOCs

### 8. Recommendations for IOC Monitoring
- Signatures to deploy
- Blocklist recommendations
- Detection rules suggestions

**IMPORTANT**: Be thorough. This report is for SOC analysts and threat hunters. Include ALL IOCs provided.""",

        "trends": """Generate a **Trend Analysis & Threat Intelligence Report** for this incident.

## Structure your report EXACTLY as follows:

### 1. Threat Landscape Summary
- Nature of the attack (classification, severity)
- Likely threat actor profile or category
- Known campaigns or APT groups that use similar techniques

### 2. Attack Pattern Analysis
- Full attack chain / kill chain mapping
- Initial access → persistence → lateral movement → objective
- MITRE ATT&CK technique timeline

### 3. Recurring Indicators
- IPs, domains, or hashes seen in multiple contexts
- Common infrastructure across IOCs
- Repeated attacker tooling

### 4. Vulnerability Assessment
- Attack vectors exploited
- System weaknesses that enabled the attack
- Configuration issues identified

### 5. Historical Context
- Similar incident patterns (if data suggests)
- Escalation trajectory

### 6. Predictive Analysis
- Likely next steps if attack continues
- Potential targets based on observed patterns
- Risk of data exfiltration or destruction

### 7. Strategic Recommendations
- Short-term (immediate actions, 24-72 hours)
- Medium-term (within 30 days)
- Long-term (architecture & process changes)

### 8. Detection & Monitoring Improvements
- New detection rules to implement
- Logging gaps to address
- Alerting improvements

**IMPORTANT**: Think strategically. This report is for security leadership and threat intelligence teams. Connect the dots between individual IOCs and the bigger picture.""",
    }

    # ── Legacy summary prompts (kept for backward compatibility) ──────
    EXECUTIVE_SUMMARY_PROMPT = """You are an expert incident response analyst. Generate a concise executive summary for the following security incident. The summary should:
1. Describe what happened in non-technical terms
2. Explain the business impact
3. Summarize key findings
4. Provide high-level recommendations

Incident Data:
{incident_data}

Timeline Events:
{timeline_events}

Compromised Assets:
{compromised_assets}

Indicators of Compromise:
{iocs}

Generate a professional executive summary suitable for C-level executives."""

    TECHNICAL_SUMMARY_PROMPT = """You are an expert incident response analyst. Generate a detailed technical summary for the following security incident. Include:
1. Attack vector and initial access method
2. Lateral movement techniques observed
3. MITRE ATT&CK techniques identified
4. Technical indicators of compromise
5. Detailed remediation steps

Incident Data:
{incident_data}

Timeline Events:
{timeline_events}

Compromised Assets:
{compromised_assets}

Indicators of Compromise:
{iocs}

Generate a detailed technical analysis suitable for security engineers."""

    RECOMMENDATIONS_PROMPT = """Based on the following security incident, provide specific, actionable recommendations for:
1. Immediate containment actions
2. Eradication steps
3. Recovery procedures
4. Long-term security improvements

Incident Data:
{incident_data}

Timeline Events:
{timeline_events}

Provide prioritized recommendations with specific technical steps."""

    def __init__(self):
        """Initialize AI service with lazy-loaded provider clients."""
        self._openai_client = None
        self._google_client = None
        self._resolved_openai_key = None
        self._resolved_google_key = None

    def _get_key_from_integration(self, integration_type: str) -> Optional[str]:
        """Resolve an API key from the integrations table (DB-first).

        Queries enabled integrations of the given type, decrypts the stored
        credentials, and returns the 'api_key' field.  Returns None when no
        matching integration exists or decryption fails.
        """
        try:
            from app.models.integration import Integration
            integration = (
                Integration.query
                .filter_by(type=integration_type, is_enabled=True)
                .first()
            )
            if integration and integration.credentials_encrypted:
                encryption_service = EncryptionService()
                decrypted = encryption_service.decrypt(integration.credentials_encrypted)
                if decrypted:
                    creds = json.loads(decrypted)
                    return creds.get('api_key')
        except Exception as e:
            current_app.logger.debug(f"Could not load {integration_type} key from DB: {e}")
        return None

    def _resolve_api_key(self, integration_type: str, env_config_key: str) -> Optional[str]:
        """Return an API key checking the DB integrations table first, then env."""
        # 1. Try DB integration
        db_key = self._get_key_from_integration(integration_type)
        if db_key:
            return db_key
        # 2. Fall back to env / Flask config
        env_key = current_app.config.get(env_config_key)
        return env_key if env_key else None

    @property
    def openai_api_key(self) -> Optional[str]:
        """Resolve OpenAI API key (DB integration first, then env)."""
        return self._resolve_api_key('openai', 'OPENAI_API_KEY')

    @property
    def google_api_key(self) -> Optional[str]:
        """Resolve Google AI API key (DB integration first, then env)."""
        return self._resolve_api_key('google_ai', 'GOOGLE_AI_API_KEY')

    @property
    def openai_client(self):
        """Get or create OpenAI client."""
        api_key = self.openai_api_key
        if api_key:
            # Recreate client if key changed
            if self._resolved_openai_key != api_key:
                import openai
                self._openai_client = openai.OpenAI(api_key=api_key)
                self._resolved_openai_key = api_key
        else:
            self._openai_client = None
            self._resolved_openai_key = None
        return self._openai_client

    @property
    def google_client(self):
        """Get or create Google Generative AI client."""
        api_key = self.google_api_key
        if api_key:
            if self._resolved_google_key != api_key:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._google_client = genai.GenerativeModel('gemini-pro')
                self._resolved_google_key = api_key
        else:
            self._google_client = None
            self._resolved_google_key = None
        return self._google_client

    def is_configured(self, provider: str = None) -> bool:
        """Check if AI service is configured (DB integrations checked first)."""
        if provider == 'openai':
            return bool(self.openai_api_key)
        elif provider == 'google':
            return bool(self.google_api_key)
        return self.is_configured('openai') or self.is_configured('google')

    def get_available_providers(self) -> list:
        """Get list of configured AI providers."""
        providers = []
        if self.is_configured('openai'):
            providers.append('openai')
        if self.is_configured('google'):
            providers.append('google')
        return providers

    # ── Report generation (new AI-powered pipeline) ──────────────────

    def generate_report(
        self,
        report_type: str,
        incident_data: Dict[str, Any],
        timeline_events: list,
        compromised_assets: Dict[str, list],
        iocs: Dict[str, list],
        provider: str = None
    ) -> Optional[str]:
        """Generate a full AI-powered report in Markdown format.

        Args:
            report_type: One of 'executive', 'metrics', 'ioc', 'trends'
            incident_data: Incident dict from model.to_dict()
            timeline_events: List of timeline event dicts
            compromised_assets: Dict with 'hosts' and 'accounts' lists
            iocs: Dict with 'network', 'host', 'malware' lists
            provider: 'openai' or 'google' (auto-detected if None)

        Returns:
            Markdown string or None on failure
        """
        if provider is None:
            providers = self.get_available_providers()
            if not providers:
                return None
            provider = providers[0]

        # Build the user prompt with all incident data
        user_prompt = self._build_report_user_prompt(
            incident_data, timeline_events, compromised_assets, iocs
        )

        # Get the report-type-specific instructions
        report_instructions = self.REPORT_PROMPTS.get(report_type, self.REPORT_PROMPTS['executive'])

        # Combine system prompt + report instructions
        system_prompt = f"{self.SYSTEM_PROMPT_BASE}\n\n{report_instructions}"

        if provider == 'openai':
            return self._generate_report_openai(system_prompt, user_prompt)
        elif provider == 'google':
            return self._generate_report_google(system_prompt, user_prompt)

        return None

    def _build_report_user_prompt(
        self,
        incident_data: Dict[str, Any],
        timeline_events: list,
        compromised_assets: Dict[str, list],
        iocs: Dict[str, list]
    ) -> str:
        """Build the user prompt containing all incident data."""
        sections = []
        sections.append("## Incident Information")
        sections.append(self._format_incident(incident_data))
        sections.append("\n## Timeline Events")
        sections.append(self._format_timeline(timeline_events))
        sections.append("\n## Compromised Assets")
        sections.append(self._format_assets(compromised_assets))
        sections.append("\n## Indicators of Compromise")
        sections.append(self._format_iocs(iocs))
        return "\n".join(sections)

    def _generate_report_openai(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Generate report using OpenAI."""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Generate the report based on the following incident data:\n\n{user_prompt}"}
                ],
                max_tokens=4000,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(f"OpenAI report generation error: {e}")
            return None

    def _generate_report_google(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Generate report using Google Gemini."""
        try:
            full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}\n\n---\n\nGenerate the report now."
            response = self.google_client.generate_content(full_prompt)
            return response.text
        except Exception as e:
            current_app.logger.error(f"Google AI report generation error: {e}")
            return None

    # ── Legacy summary generation (backward compatible) ──────────────

    async def generate_summary(
        self,
        incident_data: Dict[str, Any],
        timeline_events: list,
        compromised_assets: Dict[str, list],
        iocs: Dict[str, list],
        summary_type: str = 'executive',
        provider: str = None
    ) -> Optional[str]:
        """Generate an AI summary for an incident.

        Args:
            incident_data: Incident details
            timeline_events: List of timeline events
            compromised_assets: Dict with 'hosts' and 'accounts' lists
            iocs: Dict with 'network', 'host', and 'malware' lists
            summary_type: 'executive', 'technical', or 'recommendations'
            provider: 'openai' or 'google', or None for auto-select

        Returns:
            Generated summary text or None
        """
        # Select provider
        if provider is None:
            providers = self.get_available_providers()
            if not providers:
                return None
            provider = providers[0]

        # Select prompt template
        if summary_type == 'executive':
            prompt_template = self.EXECUTIVE_SUMMARY_PROMPT
        elif summary_type == 'technical':
            prompt_template = self.TECHNICAL_SUMMARY_PROMPT
        elif summary_type == 'recommendations':
            prompt_template = self.RECOMMENDATIONS_PROMPT
        else:
            prompt_template = self.EXECUTIVE_SUMMARY_PROMPT

        # Format prompt
        prompt = prompt_template.format(
            incident_data=self._format_incident(incident_data),
            timeline_events=self._format_timeline(timeline_events),
            compromised_assets=self._format_assets(compromised_assets),
            iocs=self._format_iocs(iocs)
        )

        # Generate with selected provider
        if provider == 'openai':
            return await self._generate_openai(prompt)
        elif provider == 'google':
            return await self._generate_google(prompt)

        return None

    def generate_summary_sync(
        self,
        incident_data: Dict[str, Any],
        timeline_events: list,
        compromised_assets: Dict[str, list],
        iocs: Dict[str, list],
        summary_type: str = 'executive',
        provider: str = None
    ) -> Optional[str]:
        """Synchronous version of generate_summary."""
        # Select provider
        if provider is None:
            providers = self.get_available_providers()
            if not providers:
                return None
            provider = providers[0]

        # Select prompt template
        if summary_type == 'executive':
            prompt_template = self.EXECUTIVE_SUMMARY_PROMPT
        elif summary_type == 'technical':
            prompt_template = self.TECHNICAL_SUMMARY_PROMPT
        elif summary_type == 'recommendations':
            prompt_template = self.RECOMMENDATIONS_PROMPT
        else:
            prompt_template = self.EXECUTIVE_SUMMARY_PROMPT

        # Format prompt
        prompt = prompt_template.format(
            incident_data=self._format_incident(incident_data),
            timeline_events=self._format_timeline(timeline_events),
            compromised_assets=self._format_assets(compromised_assets),
            iocs=self._format_iocs(iocs)
        )

        # Generate with selected provider
        if provider == 'openai':
            return self._generate_openai_sync(prompt)
        elif provider == 'google':
            return self._generate_google_sync(prompt)

        return None

    async def _generate_openai(self, prompt: str) -> Optional[str]:
        """Generate text using OpenAI."""
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are an expert cybersecurity incident response analyst."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(f"OpenAI generation error: {e}")
            return None

    def _generate_openai_sync(self, prompt: str) -> Optional[str]:
        """Generate text using OpenAI (sync)."""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are an expert cybersecurity incident response analyst."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(f"OpenAI generation error: {e}")
            return None

    async def _generate_google(self, prompt: str) -> Optional[str]:
        """Generate text using Google Gemini."""
        try:
            response = await self.google_client.generate_content_async(prompt)
            return response.text
        except Exception as e:
            current_app.logger.error(f"Google AI generation error: {e}")
            return None

    def _generate_google_sync(self, prompt: str) -> Optional[str]:
        """Generate text using Google Gemini (sync)."""
        try:
            response = self.google_client.generate_content(prompt)
            return response.text
        except Exception as e:
            current_app.logger.error(f"Google AI generation error: {e}")
            return None

    def _format_incident(self, incident: Dict[str, Any]) -> str:
        """Format incident data for prompt."""
        return f"""
Title: {incident.get('title', 'N/A')}
Incident Number: #{incident.get('incident_number', 'N/A')}
Severity: {incident.get('severity', 'N/A')}
Status: {incident.get('status', 'N/A')}
Classification: {incident.get('classification', 'N/A')}
Current Phase: {incident.get('phase_name', 'N/A')}
Description: {incident.get('description', 'N/A')}
Detected: {incident.get('detected_at', 'N/A')}
Contained At: {incident.get('contained_at', 'N/A')}
Eradicated At: {incident.get('eradicated_at', 'N/A')}
Executive Summary: {incident.get('executive_summary', 'N/A')}
Lessons Learned: {incident.get('lessons_learned', 'N/A')}
"""

    def _format_timeline(self, events: list) -> str:
        """Format timeline events for prompt."""
        if not events:
            return "No timeline events recorded."

        formatted = []
        for event in events[:100]:
            formatted.append(
                f"- [{event.get('timestamp', 'N/A')}] {event.get('hostname', 'N/A')}: "
                f"{event.get('activity', 'N/A')} "
                f"(Source: {event.get('source', 'N/A')}, "
                f"MITRE Tactic: {event.get('mitre_tactic', 'N/A')}, "
                f"Technique: {event.get('mitre_technique', 'N/A')}, "
                f"Key Event: {event.get('is_key_event', False)}, "
                f"IOC: {event.get('is_ioc', False)})"
            )
        total = len(events)
        if total > 100:
            formatted.append(f"\n... and {total - 100} more events (showing first 100)")
        return "\n".join(formatted)

    def _format_assets(self, assets: Dict[str, list]) -> str:
        """Format compromised assets for prompt."""
        formatted = []

        hosts = assets.get('hosts', [])
        if hosts:
            formatted.append("Compromised Hosts:")
            for host in hosts[:30]:
                formatted.append(
                    f"- {host.get('hostname', 'N/A')} (IP: {host.get('ip_address', 'N/A')}): "
                    f"Type={host.get('system_type', 'N/A')}, "
                    f"OS={host.get('os_version', 'N/A')}, "
                    f"Containment={host.get('containment_status', 'N/A')}, "
                    f"First Seen={host.get('first_seen', 'N/A')}"
                )

        accounts = assets.get('accounts', [])
        if accounts:
            formatted.append("\nCompromised Accounts:")
            for account in accounts[:30]:
                formatted.append(
                    f"- {account.get('account_name', 'N/A')} (Type: {account.get('account_type', 'N/A')}): "
                    f"Domain={account.get('domain', 'N/A')}, "
                    f"Host={account.get('host_system', 'N/A')}, "
                    f"Privileged={account.get('is_privileged', False)}, "
                    f"Status={account.get('status', 'N/A')}"
                )

        return "\n".join(formatted) if formatted else "No compromised assets recorded."

    def _format_iocs(self, iocs: Dict[str, list]) -> str:
        """Format IOCs for prompt."""
        formatted = []

        network = iocs.get('network', [])
        if network:
            formatted.append("Network Indicators:")
            for ioc in network[:30]:
                formatted.append(
                    f"- {ioc.get('dns_ip', 'N/A')} (Protocol: {ioc.get('protocol', 'N/A')}, "
                    f"Port: {ioc.get('port', 'N/A')}, "
                    f"Direction: {ioc.get('direction', 'N/A')}, "
                    f"Malicious: {ioc.get('is_malicious', False)}): "
                    f"{ioc.get('description', 'N/A')}"
                )

        host = iocs.get('host', [])
        if host:
            formatted.append("\nHost-Based Indicators:")
            for ioc in host[:30]:
                formatted.append(
                    f"- [{ioc.get('artifact_type', 'N/A')}] {ioc.get('artifact_value', 'N/A')[:200]} "
                    f"(Host: {ioc.get('host', 'N/A')}, "
                    f"Malicious: {ioc.get('is_malicious', False)}, "
                    f"Remediated: {ioc.get('remediated', False)})"
                )

        malware = iocs.get('malware', [])
        if malware:
            formatted.append("\nMalware/Tools:")
            for m in malware[:30]:
                formatted.append(
                    f"- {m.get('file_name', 'N/A')} "
                    f"(SHA256: {m.get('sha256', 'N/A')}, "
                    f"Family: {m.get('malware_family', 'N/A')}, "
                    f"Actor: {m.get('threat_actor', 'N/A')}, "
                    f"Is Tool: {m.get('is_tool', False)}): "
                    f"{m.get('description', 'N/A')}"
                )

        return "\n".join(formatted) if formatted else "No IOCs recorded."


# Singleton instance
ai_service = AIService()
