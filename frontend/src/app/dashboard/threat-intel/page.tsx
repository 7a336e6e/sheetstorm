/**
 * UI must follow DESIGN_CONSTRAINTS.md strictly.
 * Goal: production-quality, restrained, non-AI-looking UI.
 */

"use client"

import { useState } from 'react'
import { cn } from '@/lib/utils'
import api from '@/lib/api'
import type {
  CVEResult,
  IPReputationResult,
  DomainReputationResult,
  EmailReputationResult,
  RansomwareVictimResult,
  VirusTotalResult,
  DefangResult,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Search,
  Globe,
  Mail,
  Hash,
  ShieldAlert,
  Bug,
  Skull,
  ShieldOff,
  Loader2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Info,
  Copy,
  Check,
  ExternalLink,
} from 'lucide-react'

type LookupTab = 'cve' | 'ip' | 'domain' | 'email' | 'hash' | 'ransomware' | 'defang'

const TABS: { id: LookupTab; label: string; icon: React.ElementType; placeholder: string }[] = [
  { id: 'cve', label: 'CVE Lookup', icon: Bug, placeholder: 'CVE-2024-1234' },
  { id: 'ip', label: 'IP Reputation', icon: Globe, placeholder: '8.8.8.8' },
  { id: 'domain', label: 'Domain', icon: Search, placeholder: 'example.com' },
  { id: 'email', label: 'Email', icon: Mail, placeholder: 'user@example.com' },
  { id: 'hash', label: 'File Hash', icon: Hash, placeholder: 'SHA256 / MD5 / SHA1' },
  { id: 'ransomware', label: 'Ransomware', icon: Skull, placeholder: 'Company name' },
  { id: 'defang', label: 'Defang IOC', icon: ShieldOff, placeholder: 'evil.com or http://evil.com/path' },
]

type LookupResult = CVEResult | IPReputationResult | DomainReputationResult | EmailReputationResult | RansomwareVictimResult | VirusTotalResult | DefangResult

export default function ThreatIntelPage() {
  const [activeTab, setActiveTab] = useState<LookupTab>('cve')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<LookupResult | null>(null)
  const [copied, setCopied] = useState(false)

  const currentTab = TABS.find(t => t.id === activeTab)!

  const handleLookup = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError('')
    setResult(null)

    try {
      let data: LookupResult | undefined
      switch (activeTab) {
        case 'cve':
          data = await api.post<CVEResult>('/threat-intel/cve/lookup', { cve_id: query.trim() })
          break
        case 'ip':
          data = await api.post<IPReputationResult>('/threat-intel/ip/lookup', { ip: query.trim() })
          break
        case 'domain':
          data = await api.post<DomainReputationResult>('/threat-intel/domain/lookup', { domain: query.trim() })
          break
        case 'email':
          data = await api.post<EmailReputationResult>('/threat-intel/email/lookup', { email: query.trim() })
          break
        case 'hash':
          data = await api.post<VirusTotalResult>('/threat-intel/virustotal/lookup', { type: 'hash', value: query.trim() })
          break
        case 'ransomware':
          data = await api.post<RansomwareVictimResult>('/threat-intel/ransomware/lookup', { query: query.trim() })
          break
        case 'defang':
          data = await api.post<DefangResult>('/tools/defang', { values: [query.trim()] })
          break
      }
      if (data) setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Lookup failed')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Threat Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Look up IOCs, CVEs, and reputation data across multiple sources
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-1 border-b border-border pb-px">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); setResult(null); setError(''); setQuery(''); }}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-md transition-colors',
              activeTab === tab.id
                ? 'bg-card text-foreground border border-border border-b-transparent -mb-px'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search Input */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLookup()}
            placeholder={currentTab.placeholder}
            className="w-full pl-9 pr-4 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <Button onClick={handleLookup} disabled={loading || !query.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Search className="h-4 w-4 mr-1" />}
          Lookup
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 text-destructive text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="border border-border rounded-lg bg-card">
          {activeTab === 'cve' && <CVEResultCard data={result as CVEResult} />}
          {activeTab === 'ip' && <IPResultCard data={result as IPReputationResult} />}
          {activeTab === 'domain' && <DomainResultCard data={result as DomainReputationResult} />}
          {activeTab === 'email' && <EmailResultCard data={result as EmailReputationResult} />}
          {activeTab === 'hash' && <HashResultCard data={result as VirusTotalResult} />}
          {activeTab === 'ransomware' && <RansomwareResultCard data={result as RansomwareVictimResult} />}
          {activeTab === 'defang' && <DefangResultCard data={result as DefangResult} onCopy={copyToClipboard} copied={copied} />}
        </div>
      )}

      {/* No-integration hint */}
      {result && !loading && (
        <div className="flex items-start gap-2 p-3 rounded-md bg-muted/50 text-xs text-muted-foreground">
          <Info className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            Some lookups require configured integrations (VirusTotal, AbuseIPDB, Have I Been Pwned).
            Configure them in <strong>Admin → Settings</strong> to unlock all enrichment sources.
            CVE and Ransomware lookups use free public APIs and work without configuration.
          </span>
        </div>
      )}
    </div>
  )
}

/* ────────────────── Result Cards ────────────────── */

function SectionHeader({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold text-foreground mb-2">{children}</h3>
}

function KV({ label, value, badge, badgeVariant }: { label: string; value?: string | number | null; badge?: boolean; badgeVariant?: 'default' | 'destructive' | 'outline' }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="flex justify-between py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      {badge ? (
        <Badge variant={badgeVariant || 'default'}>{String(value)}</Badge>
      ) : (
        <span className="font-medium text-foreground max-w-[60%] text-right truncate">{String(value)}</span>
      )}
    </div>
  )
}

function ThreatScore({ score, max, label }: { score: number; max: number; label: string }) {
  const pct = Math.round((score / Math.max(max, 1)) * 100)
  const color = pct >= 70 ? 'bg-red-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{score}/{max}</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/* -- CVE -- */
function CVEResultCard({ data }: { data: CVEResult }) {
  const severityColor = (s?: string | null) => {
    if (!s) return 'default'
    const sl = s.toLowerCase()
    if (sl === 'critical' || sl === 'high') return 'destructive' as const
    if (sl === 'medium') return 'default' as const
    return 'default' as const
  }

  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bug className="h-5 w-5 text-muted-foreground" />
          <span className="font-semibold">{data.cve_id}</span>
          {!data.found && <Badge variant="default">Not Found</Badge>}
        </div>
        {data.nvd?.cvss_score != null && (
          <Badge variant={severityColor(data.nvd.cvss_severity)}>
            CVSS {data.nvd.cvss_score} — {data.nvd.cvss_severity}
          </Badge>
        )}
      </div>

      {data.nvd && (
        <div className="p-4 space-y-3">
          <SectionHeader>NVD Details</SectionHeader>
          <p className="text-sm text-muted-foreground leading-relaxed">{data.nvd.description}</p>
          <div className="grid grid-cols-2 gap-x-8">
            <KV label="Published" value={data.nvd.published?.split('T')[0]} />
            <KV label="Last Modified" value={data.nvd.last_modified?.split('T')[0]} />
            <KV label="CVSS Vector" value={data.nvd.cvss_vector} />
          </div>
          {data.nvd.cwes.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {data.nvd.cwes.map(c => <Badge key={c} variant="outline">{c}</Badge>)}
            </div>
          )}
          {data.nvd.references.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">References</p>
              {data.nvd.references.slice(0, 5).map(r => (
                <a key={r} href={r} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline truncate">
                  <ExternalLink className="h-3 w-3 shrink-0" />{r}
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {data.kev && (
        <div className="p-4 space-y-3">
          <SectionHeader>
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="h-4 w-4 text-red-500" />
              CISA Known Exploited Vulnerability
            </span>
          </SectionHeader>
          <div className="grid grid-cols-2 gap-x-8">
            <KV label="Vendor" value={data.kev.vendor} />
            <KV label="Product" value={data.kev.product} />
            <KV label="Date Added to KEV" value={data.kev.date_added} />
            <KV label="Remediation Due" value={data.kev.due_date} />
            <KV label="Ransomware Use" value={data.kev.known_ransomware_use} badge badgeVariant={data.kev.known_ransomware_use === 'Known' ? 'destructive' : 'default'} />
          </div>
          <p className="text-sm text-muted-foreground">{data.kev.short_description}</p>
          {data.kev.required_action && (
            <div className="text-xs p-2 bg-yellow-50 dark:bg-yellow-950/30 rounded border border-yellow-200 dark:border-yellow-900">
              <strong>Required Action:</strong> {data.kev.required_action}
            </div>
          )}
        </div>
      )}

      {data.nvd_error && (
        <div className="p-4 text-xs text-muted-foreground">NVD: {data.nvd_error}</div>
      )}
    </div>
  )
}

/* -- IP -- */
function IPResultCard({ data }: { data: IPReputationResult }) {
  const abuse = data.sources.abuseipdb
  const vt = data.sources.virustotal
  const geo = data.sources.geo

  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-muted-foreground" />
          <span className="font-mono font-semibold">{data.ip}</span>
        </div>
        {!data.enriched && <Badge variant="default">No enrichment sources configured</Badge>}
      </div>

      {geo && (
        <div className="p-4 space-y-2">
          <SectionHeader>Geolocation</SectionHeader>
          <div className="grid grid-cols-2 gap-x-8">
            <KV label="Country" value={geo.country} />
            <KV label="Region" value={geo.region} />
            <KV label="City" value={geo.city} />
            <KV label="ISP" value={geo.isp} />
            <KV label="Organization" value={geo.org} />
            <KV label="AS" value={geo.as} />
          </div>
        </div>
      )}

      {abuse && (
        <div className="p-4 space-y-2">
          <SectionHeader>AbuseIPDB</SectionHeader>
          <ThreatScore score={abuse.abuse_confidence_score} max={100} label="Abuse Confidence" />
          <div className="grid grid-cols-2 gap-x-8 mt-2">
            <KV label="Total Reports" value={abuse.total_reports} />
            <KV label="ISP" value={abuse.isp} />
            <KV label="Domain" value={abuse.domain} />
            <KV label="Tor Node" value={abuse.is_tor ? 'Yes' : 'No'} badge badgeVariant={abuse.is_tor ? 'destructive' : 'default'} />
            <KV label="Usage" value={abuse.usage_type} />
          </div>
        </div>
      )}

      {vt && (
        <div className="p-4 space-y-2">
          <SectionHeader>VirusTotal</SectionHeader>
          <ThreatScore score={vt.malicious} max={vt.malicious + vt.suspicious + vt.harmless + vt.undetected} label="Malicious Detections" />
          <div className="grid grid-cols-2 gap-x-8 mt-2">
            <KV label="Reputation" value={vt.reputation} />
            <KV label="AS Owner" value={vt.as_owner} />
            <KV label="Country" value={vt.country} />
          </div>
        </div>
      )}
    </div>
  )
}

/* -- Domain -- */
function DomainResultCard({ data }: { data: DomainReputationResult }) {
  const vt = data.sources.virustotal

  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Search className="h-5 w-5 text-muted-foreground" />
          <span className="font-mono font-semibold">{data.domain}</span>
        </div>
        {!data.enriched && <Badge variant="default">VirusTotal not configured</Badge>}
      </div>

      {vt && (
        <div className="p-4 space-y-2">
          <SectionHeader>VirusTotal</SectionHeader>
          <ThreatScore score={vt.malicious} max={vt.malicious + vt.suspicious + vt.harmless + vt.undetected} label="Malicious Detections" />
          <div className="grid grid-cols-2 gap-x-8 mt-2">
            <KV label="Reputation" value={vt.reputation} />
            <KV label="Registrar" value={vt.registrar} />
          </div>
          {vt.categories && Object.keys(vt.categories).length > 0 && (
            <div className="flex gap-1 flex-wrap mt-2">
              {Object.values(vt.categories).map((cat, i) => (
                <Badge key={i} variant="outline">{cat}</Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* -- Email -- */
function EmailResultCard({ data }: { data: EmailReputationResult }) {
  const hibp = data.sources.hibp

  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mail className="h-5 w-5 text-muted-foreground" />
          <span className="font-mono font-semibold">{data.email}</span>
        </div>
        {!data.enriched && <Badge variant="default">HIBP not configured</Badge>}
      </div>

      {hibp && (
        <div className="p-4 space-y-3">
          <SectionHeader>Have I Been Pwned</SectionHeader>
          {hibp.breach_count === 0 ? (
            <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
              <CheckCircle className="h-4 w-4" /> No breaches found
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                <XCircle className="h-4 w-4" /> Found in {hibp.breach_count} breach(es)
              </div>
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {hibp.breaches.map(b => (
                  <div key={b.name} className="p-3 bg-muted/50 rounded-md space-y-1">
                    <div className="flex justify-between">
                      <span className="text-sm font-medium">{b.name}</span>
                      <span className="text-xs text-muted-foreground">{b.breach_date}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {b.pwn_count?.toLocaleString()} accounts · {b.domain}
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {b.data_classes.slice(0, 6).map(dc => (
                        <Badge key={dc} variant="outline" className="text-[10px] py-0">{dc}</Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* -- Hash -- */
function HashResultCard({ data }: { data: VirusTotalResult }) {
  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Hash className="h-5 w-5 text-muted-foreground" />
          <span className="font-mono text-sm font-semibold truncate max-w-md">{data.value}</span>
        </div>
        {data.found ? (
          <Badge variant={data.malicious && data.malicious > 0 ? 'destructive' : 'default'}>
            {data.detection_ratio || 'Clean'}
          </Badge>
        ) : (
          <Badge variant="default">{data.message || 'Not Found'}</Badge>
        )}
      </div>

      {data.found && (
        <div className="p-4 space-y-3">
          {data.total_engines && data.malicious !== undefined && (
            <ThreatScore score={data.malicious} max={data.total_engines} label="Malicious Detections" />
          )}
          <div className="grid grid-cols-2 gap-x-8 mt-2">
            <KV label="File Name" value={data.file_name} />
            <KV label="File Type" value={data.file_type} />
            <KV label="SHA256" value={data.sha256} />
            <KV label="MD5" value={data.md5} />
          </div>
          {data.tags && data.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {data.tags.map(t => <Badge key={t} variant="outline">{t}</Badge>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* -- Ransomware -- */
function RansomwareResultCard({ data }: { data: RansomwareVictimResult }) {
  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skull className="h-5 w-5 text-muted-foreground" />
          <span className="font-semibold">Ransomware Search: &ldquo;{data.query}&rdquo;</span>
        </div>
        <Badge variant={data.found ? 'destructive' : 'default'}>
          {data.total} result{data.total !== 1 ? 's' : ''}
        </Badge>
      </div>

      {data.found ? (
        <div className="divide-y divide-border max-h-96 overflow-y-auto">
          {data.items.map((v, i) => (
            <div key={i} className="p-4 space-y-1">
              <div className="flex justify-between items-start">
                <span className="font-medium text-sm">{v.victim}</span>
                <Badge variant="destructive">{v.group}</Badge>
              </div>
              <div className="text-xs text-muted-foreground space-x-3">
                {v.discovered && <span>Discovered: {v.discovered}</span>}
                {v.country && <span>Country: {v.country}</span>}
              </div>
              {v.domain && <div className="text-xs text-muted-foreground">Domain: {v.domain}</div>}
              {v.description && <p className="text-xs text-muted-foreground mt-1">{v.description}</p>}
            </div>
          ))}
        </div>
      ) : (
        <div className="p-4 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
          <CheckCircle className="h-4 w-4" /> No ransomware victim postings found
        </div>
      )}
    </div>
  )
}

/* -- Defang -- */
function DefangResultCard({ data, onCopy, copied }: { data: DefangResult; onCopy: (s: string) => void; copied: boolean }) {
  const items = data.items || (data.defanged ? [{ original: data.original || '', defanged: data.defanged }] : [])

  return (
    <div className="divide-y divide-border">
      <div className="p-4 flex items-center gap-2">
        <ShieldOff className="h-5 w-5 text-muted-foreground" />
        <span className="font-semibold">Defanged IOC</span>
      </div>
      {items.map((item, i) => (
        <div key={i} className="p-4 space-y-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Original</p>
              <code className="text-sm bg-muted px-2 py-1 rounded break-all">{item.original}</code>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Defanged</p>
              <div className="flex items-center gap-2">
                <code className="text-sm bg-muted px-2 py-1 rounded break-all flex-1">{item.defanged}</code>
                <Button variant="ghost" size="icon-sm" onClick={() => onCopy(item.defanged)}>
                  {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
