/**
 * Guided tours: one short walkthrough per page, shown once (then replayable
 * from the sidebar's "Page tour" button). Admins switch tours on/off per user
 * on the Users page (`user.tours_enabled`); the user's finished/skipped tours
 * are kept in `preferences.tours_seen`.
 *
 * Steps point at `[data-tour="…"]` anchors. A step whose anchor is not on
 * the page (permission-gated button, empty state) is skipped, so one tour
 * fits every role.
 */
export interface TourStep {
  /** `data-tour` value of the element to highlight; omit for a centred card. */
  target?: string
  title: string
  body: string
}

export interface TourDef {
  id: string
  title: string
  /** Pathname test for the page the tour belongs to. */
  match: (pathname: string) => boolean
  steps: TourStep[]
}

const exact = (path: string) => (p: string) => p === path
const INCIDENT_DETAIL = /^\/dashboard\/incidents\/[0-9a-f-]{36}$/

export const TOURS: TourDef[] = [
  {
    id: 'dashboard',
    title: 'Welcome to SheetStorm',
    match: exact('/dashboard'),
    steps: [
      { title: 'Welcome to SheetStorm', body: 'A two-minute tour of each page shows up the first time you open it. You can skip any tour and replay it later from "Page tour" in the sidebar.' },
      { target: 'nav-main', title: 'Navigation', body: 'Incidents, threat intel, the knowledge base, reports and response metrics. Admin pages appear below when your role allows them.' },
      { target: 'search', title: 'Search everything', body: 'Press Ctrl/⌘ + K to search incidents, hosts, IOCs and tasks, or to jump to any page. Press ? for keyboard shortcuts.' },
      { target: 'new-incident', title: 'Open an incident', body: 'Start a new investigation. A case template can pre-fill the investigative questions, leads, playbook and custom fields.' },
      { target: 'dashboard-stats', title: 'At a glance', body: 'Counts across every incident you can access: active work, severity, TLP and the open investigation queue.' },
      { target: 'notifications', title: 'Notifications', body: 'Assignments, mentions and due reminders land here.' },
    ],
  },
  {
    id: 'incidents',
    title: 'Incidents',
    match: exact('/dashboard/incidents'),
    steps: [
      { target: 'incidents-table', title: 'Your incidents', body: 'Search, sort and filter on the server: all incidents are reachable, and the filters live in the URL so you can share a view.' },
      { title: 'Open one', body: 'Click an incident to work it. The "New incident" button (or the n key) creates one; pick a case template to seed questions, leads and a playbook.' },
    ],
  },
  {
    id: 'incident-detail',
    title: 'Working an incident',
    match: (p) => INCIDENT_DETAIL.test(p),
    steps: [
      { target: 'incident-header', title: 'The incident', body: 'Severity, status, IR phase and TLP. The TLP decides what may leave the platform (enrichment, AI, exports).' },
      { target: 'incident-live', title: 'Live collaboration', body: 'Changes by colleagues appear instantly; the avatars show who else is on this incident. If two people edit the same item, you get a "changed by someone else" choice instead of a silent overwrite.' },
      { target: 'incident-actions', title: 'Actions', body: 'Export CSV/STIX, generate a report, import logs, edit the incident or move it to the next status.' },
      { target: 'incident-tabs', title: 'Everything in one place', body: 'Timeline events, hosts, questions, tasks, the playbook, attack graph, IOCs, evidence with chain of custody, notes, decisions and the post-incident review each have a tab.' },
      { target: 'tab-questions', title: 'Investigative questions', body: 'What the investigation must answer. Add them from the library or a case template, then record answers with a confidence level.' },
      { target: 'tab-evidence', title: 'Evidence and custody', body: 'Register evidence, record hashes, check items in and out, and export a custody bundle anyone can verify offline.' },
      { target: 'tab-decisions', title: 'Decisions and actions', body: 'Who decided what and why, and every response action from request to verification. Each change is signed and kept.' },
    ],
  },
  {
    id: 'admin-users',
    title: 'Managing users',
    match: exact('/dashboard/admin/users'),
    steps: [
      { target: 'users-actions', title: 'Add or invite', body: 'Create an account directly or send a one-time invitation link.' },
      { target: 'users-stats', title: 'Account health', body: 'Disabled, locked and MFA numbers for your organization.' },
      { target: 'users-table', title: 'Account actions', body: 'Each row\'s menu disables or re-enables an account, resets a password or MFA, forces a sign-out, unlocks, and switches guided tours on or off.' },
      { target: 'users-tours', title: 'Guided tours', body: 'Turn these tours on or off for everyone, or replay them from the start.' },
    ],
  },
  {
    id: 'admin-settings',
    title: 'Settings',
    match: exact('/dashboard/admin/settings'),
    steps: [
      { target: 'settings-tabs', title: 'Organization settings', body: 'General (including the data-egress policy for AI and enrichment by TLP), Security (passwords, MFA, sessions, rate limits), integrations, API keys and audit retention.' },
    ],
  },
  {
    id: 'activity',
    title: 'Activity log',
    match: exact('/dashboard/activity'),
    steps: [
      { target: 'activity-filters', title: 'Find anything', body: 'Filter the tamper-evident audit log by user, event, resource, IP or date; the filters are kept in the URL.' },
      { target: 'activity-export', title: 'Export', body: 'Download the filtered log as CSV or JSON Lines (needs the audit export permission).' },
    ],
  },
  {
    id: 'admin-templates',
    title: 'Case templates',
    match: exact('/dashboard/admin/templates'),
    steps: [
      { target: 'templates-table', title: 'Templates', body: 'Built-in templates stay as shipped: use the pencil to customize your own copy, and the power button to hide templates you don\'t use.' },
      { target: 'templates-new', title: 'Write your own', body: 'The editor has a format reference and an example to start from.' },
      { target: 'templates-dfiq', title: 'More questions', body: 'Import Google\'s DFIQ question library with one click; the archive is checked against a pinned fingerprint.' },
    ],
  },
]

export function tourForPath(pathname: string | null | undefined): TourDef | null {
  if (!pathname) return null
  return TOURS.find((t) => t.match(pathname)) ?? null
}

/** Steps whose anchor is present in `root` (centred steps always count). */
export function visibleSteps(tour: TourDef, root: ParentNode = document): TourStep[] {
  return tour.steps.filter((s) => !s.target || root.querySelector(`[data-tour="${s.target}"]`))
}
