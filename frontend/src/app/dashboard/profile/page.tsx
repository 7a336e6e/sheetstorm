"use client"

import { useState, useEffect, useCallback } from 'react'
import { useAuthStore } from '@/lib/store'
import api from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  User as UserIcon,
  Mail,
  Shield,
  Clock,
  Key,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Building,
  UsersRound,
} from 'lucide-react'
import type { User } from '@/types'

export default function ProfilePage() {
  const { user: authUser } = useAuthStore()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // Change password state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [passwordLoading, setPasswordLoading] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState('')

  const fetchProfile = useCallback(async () => {
    try {
      const data = await api.get<User>('/auth/me')
      setUser(data)
    } catch {
      // user info available from auth store as fallback
      if (authUser) setUser(authUser as User)
    } finally {
      setLoading(false)
    }
  }, [authUser])

  useEffect(() => {
    fetchProfile()
  }, [fetchProfile])

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')
    setPasswordSuccess('')

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match')
      return
    }

    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters')
      return
    }

    setPasswordLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      setPasswordSuccess('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      setPasswordError(err?.message || 'Failed to change password')
    } finally {
      setPasswordLoading(false)
    }
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-8 w-48 bg-muted animate-pulse rounded" />
        <div className="grid gap-6 md:grid-cols-2">
          <div className="h-64 bg-muted animate-pulse rounded-lg" />
          <div className="h-64 bg-muted animate-pulse rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground mt-1">
          View your account details and change your password
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Account Information */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account Information</CardTitle>
            <CardDescription>Your personal and organizational details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center text-2xl font-medium">
                {user?.name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <div>
                <p className="font-medium text-lg">{user?.name}</p>
                <p className="text-sm text-muted-foreground">{user?.email}</p>
              </div>
            </div>

            <div className="border-t border-border" />

            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Email</span>
                <span className="font-medium">{user?.email}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <UserIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Name</span>
                <span className="font-medium">{user?.name}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Shield className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Roles</span>
                <div className="flex flex-wrap gap-1">
                  {user?.roles?.map((role) => (
                    <Badge key={role} variant="secondary" className="text-xs">
                      {role}
                    </Badge>
                  ))}
                </div>
              </div>
              {user?.organizational_role && (
                <div className="flex items-center gap-3 text-sm">
                  <Building className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Org Role</span>
                  <span className="font-medium">{user.organizational_role}</span>
                </div>
              )}
              {user?.teams && user.teams.length > 0 && (
                <div className="flex items-center gap-3 text-sm">
                  <UsersRound className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Teams</span>
                  <div className="flex flex-wrap gap-1">
                    {user.teams.map((team) => (
                      <Badge key={team.id} variant="outline" className="text-xs">
                        {team.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {user?.auth_provider && (
                <div className="flex items-center gap-3 text-sm">
                  <Key className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-muted-foreground w-24">Auth</span>
                  <Badge variant="outline" className="text-xs capitalize">
                    {user.auth_provider}
                  </Badge>
                </div>
              )}
              <div className="flex items-center gap-3 text-sm">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Last Login</span>
                <span className="text-muted-foreground text-xs">
                  {formatDate(user?.last_login)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Clock className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground w-24">Member Since</span>
                <span className="text-muted-foreground text-xs">
                  {formatDate(user?.created_at)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Change Password */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Change Password</CardTitle>
            <CardDescription>
              Update your password to keep your account secure
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="current-password">Current Password</Label>
                <div className="relative">
                  <Input
                    id="current-password"
                    type={showCurrentPassword ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Enter current password"
                    required
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  >
                    {showCurrentPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password"
                    required
                    minLength={8}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                  >
                    {showNewPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm New Password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  required
                  minLength={8}
                />
              </div>

              {passwordError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {passwordError}
                </div>
              )}

              {passwordSuccess && (
                <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                  <Check className="h-4 w-4 shrink-0" />
                  {passwordSuccess}
                </div>
              )}

              <Button
                type="submit"
                disabled={passwordLoading || !currentPassword || !newPassword || !confirmPassword}
                className="w-full"
              >
                {passwordLoading ? 'Changing...' : 'Change Password'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
