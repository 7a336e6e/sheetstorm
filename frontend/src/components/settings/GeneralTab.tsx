/**
 * General tab in Settings — Organization name, timezone, registration toggle, members table.
 * Consolidated from the old /admin/organization page + the old "General" tab.
 */

"use client"

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Settings, Loader2, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Organization {
  id: string
  name: string
  allow_registration: boolean
  settings: {
    timezone?: string
  }
  members?: { id: string; name: string; email: string; roles: string[]; is_active: boolean }[]
}

export function GeneralTab() {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [organization, setOrganization] = useState<Organization | null>(null)
  const [orgForm, setOrgForm] = useState({
    name: '',
    timezone: 'UTC',
    allow_registration: false,
  })

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const orgRes = await api.get<Organization>('/organization')
      setOrganization(orgRes)
      setOrgForm({
        name: orgRes.name,
        timezone: orgRes.settings?.timezone || 'UTC',
        allow_registration: orgRes.allow_registration ?? false,
      })
    } catch {
      toast({ title: 'Error', description: 'Failed to load organization settings', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put('/organization', {
        name: orgForm.name,
        allow_registration: orgForm.allow_registration,
        settings: { timezone: orgForm.timezone },
      })
      toast({ title: 'Saved', description: 'Organization settings updated' })
      loadData()
    } catch {
      toast({ title: 'Error', description: 'Failed to save settings', variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings className="h-5 w-5" />
            Organization Settings
          </CardTitle>
          <CardDescription>Basic system configuration</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="org-name">Organization Name</Label>
            <Input
              id="org-name"
              value={orgForm.name}
              onChange={e => setOrgForm({ ...orgForm, name: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="timezone">Timezone</Label>
            <Select
              value={orgForm.timezone}
              onValueChange={v => setOrgForm({ ...orgForm, timezone: v })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="UTC">UTC</SelectItem>
                <SelectItem value="America/New_York">Eastern Time (ET)</SelectItem>
                <SelectItem value="America/Chicago">Central Time (CT)</SelectItem>
                <SelectItem value="America/Denver">Mountain Time (MT)</SelectItem>
                <SelectItem value="America/Los_Angeles">Pacific Time (PT)</SelectItem>
                <SelectItem value="Europe/London">London (GMT)</SelectItem>
                <SelectItem value="Europe/Paris">Central European (CET)</SelectItem>
                <SelectItem value="Europe/Helsinki">Eastern European (EET)</SelectItem>
                <SelectItem value="Asia/Tokyo">Japan (JST)</SelectItem>
                <SelectItem value="Asia/Shanghai">China (CST)</SelectItem>
                <SelectItem value="Australia/Sydney">Sydney (AEDT)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center space-x-3 pt-2">
            <Switch
              id="allow-reg"
              checked={orgForm.allow_registration}
              onCheckedChange={c => setOrgForm({ ...orgForm, allow_registration: c })}
            />
            <Label htmlFor="allow-reg">Allow user self-registration</Label>
          </div>
          <div className="pt-2">
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Changes
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Members table */}
      {organization?.members && organization.members.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-5 w-5" />
              Members
            </CardTitle>
            <CardDescription>{organization.members.length} users in this organization</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {organization.members.map(m => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">{m.name}</TableCell>
                    <TableCell className="text-muted-foreground">{m.email}</TableCell>
                    <TableCell>
                      {m.roles?.map(r => (
                        <Badge key={r} variant="outline" className="mr-1 text-xs">{r}</Badge>
                      ))}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={m.is_active ? 'text-green-400 border-green-500/30' : 'text-muted-foreground'}>
                        {m.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
