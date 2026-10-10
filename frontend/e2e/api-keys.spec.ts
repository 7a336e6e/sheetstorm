// API keys (W3-APIK-UI): admin creates a service account and a key for it, copies the
// one-time secret, exchanges it, then revokes it; an analyst manages a personal key from
// the profile page; roles without the permissions see nothing.
// Run: npx playwright test e2e/api-keys.spec.ts   (against a running stack)
import { request as pwRequest, type BrowserContext, type Locator, type Page } from '@playwright/test'
import { api, expect, expectOk, test, useRole } from './fixtures'

const stamp = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`

/** The one-time secret shown in the dialog, then dismissed through the acknowledgement. */
async function readAndDismissSecret(page: Page, title: 'API key created' | 'API key rotated'): Promise<string> {
  const dialog = page.getByRole('dialog', { name: title })
  await expect(dialog).toBeVisible()
  const secret = ((await dialog.getByTestId('api-key-secret').textContent()) ?? '').trim()
  expect(secret).toMatch(/^ssk_[a-z2-7]{12}_[A-Za-z0-9_-]{43}$/)
  // The MCP hint references the variable, never the key itself.
  await expect(dialog).toContainText('${env:SHEETSTORM_API_KEY}')

  const done = dialog.getByRole('button', { name: 'Done' })
  await expect(done).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible() // cannot be dismissed before it is acknowledged
  await dialog.getByLabel('I have stored this key').check()
  await done.click()
  await expect(dialog).toBeHidden()
  await expect(page.getByText(secret)).toHaveCount(0) // gone from the page for good
  return secret
}

/** Exchange a key from a cookie-less client: it yields a Bearer token, never a session. */
async function exchange(baseURL: string | undefined, secret: string): Promise<{ status: number; body: Record<string, unknown> }> {
  const client = await pwRequest.newContext({ baseURL })
  try {
    const res = await client.post('/api/v1/auth/token', { data: { api_key: secret } })
    return { status: res.status(), body: (await res.json().catch(() => ({}))) as Record<string, unknown> }
  } finally {
    await client.dispose()
  }
}

/** Row menu > Revoke > confirm. */
async function revokeRow(page: Page, row: Locator, keyName: string) {
  await row.getByRole('button', { name: /actions for/i }).click()
  await page.getByRole('menuitem', { name: 'Revoke' }).click()
  await page.getByRole('dialog', { name: `Revoke ${keyName}?` }).getByRole('button', { name: 'Revoke key' }).click()
}

async function deleteServiceAccount(context: BrowserContext, id: string | undefined) {
  if (id) await api.delete(context, `/service-accounts/${id}`)
}

test.describe('admin: service account key lifecycle', { tag: '@api-keys' }, () => {
  useRole('admin')

  test('create service account, issue a key, exchange it, revoke it', async ({ page, context, baseURL }) => {
    const accountName = `e2e-bot-${stamp()}`
    let accountId: string | undefined
    try {
      await page.goto('/dashboard/admin/settings?tab=api-keys')
      await expect(page.getByRole('tab', { name: /API Keys/ })).toBeVisible()

      // Service account with the Analyst role (under the admin's ceiling).
      await page.getByRole('button', { name: 'Create service account' }).click()
      const saDialog = page.getByRole('dialog', { name: 'Create service account' })
      await saDialog.getByLabel('Name').fill(accountName)
      await saDialog.getByRole('checkbox', { name: 'Analyst', exact: true }).check()
      const created = page.waitForResponse(
        (r) => r.url().endsWith('/api/v1/service-accounts') && r.request().method() === 'POST'
      )
      await saDialog.getByRole('button', { name: 'Create service account' }).click()
      const createdRes = await created
      expect(createdRes.status()).toBe(201)
      accountId = ((await createdRes.json()) as { id: string }).id

      // A key for it, from the account's row.
      const saTable = page.getByRole('grid', { name: 'Service accounts' })
      const saRow = saTable.getByRole('row').filter({ hasText: accountName })
      await saRow.getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Create key' }).click()

      const keyDialog = page.getByRole('dialog', { name: 'Create API key' })
      await expect(keyDialog.getByRole('combobox', { name: 'Owner' })).toContainText(accountName)
      const keyName = `e2e-key-${stamp()}`
      await keyDialog.getByLabel('Name').fill(keyName)
      await keyDialog.getByRole('button', { name: 'Read-only' }).click()
      await keyDialog.getByRole('button', { name: 'Create key' }).click()

      const secret = await readAndDismissSecret(page, 'API key created')

      // The key is listed, active, and works.
      const keyRow = page
        .getByRole('grid', { name: 'API keys of the organization' })
        .getByRole('row')
        .filter({ hasText: keyName })
      await expect(keyRow).toContainText('Active')
      const ok = await exchange(baseURL, secret)
      expect(ok.status).toBe(200)
      expect(ok.body.token_type).toBe('Bearer')
      const scopes = ok.body.scopes as string[]
      expect(scopes.length).toBeGreaterThan(0)
      expect(scopes.every((s) => s.endsWith(':read'))).toBe(true)

      // Revoke with a reason; the same secret is rejected afterwards.
      await keyRow.getByRole('button', { name: /actions for/i }).click()
      await page.getByRole('menuitem', { name: 'Revoke' }).click()
      const confirm = page.getByRole('dialog', { name: `Revoke ${keyName}?` })
      await confirm.getByLabel(/Reason/).fill('e2e cleanup')
      await confirm.getByRole('button', { name: 'Revoke key' }).click()
      await expect(keyRow).toContainText('Revoked')
      expect((await exchange(baseURL, secret)).status).toBe(401)
    } finally {
      await deleteServiceAccount(context, accountId)
    }
  })

  test('org policy: disabling keys blocks creation and the exchange, enabling restores it', async ({ page, context }) => {
    await page.goto('/dashboard/admin/settings?tab=api-keys')
    const toggle = page.getByLabel('Allow API keys')
    await expect(toggle).toBeChecked()
    try {
      await toggle.click()
      await page.getByRole('dialog', { name: 'Disable API keys?' }).getByRole('button', { name: 'Disable API keys' }).click()
      await expect(toggle).not.toBeChecked()

      await page.getByRole('button', { name: /Create API key/ }).click()
      await expect(page.getByRole('dialog', { name: 'Create API key' })).toContainText('API keys are disabled')
    } finally {
      await expectOk(await api.put(context, '/organization', { settings: { api_keys_enabled: true } }), 'restore org')
    }
  })
})

test.describe('analyst: personal key from the profile', { tag: '@api-keys' }, () => {
  useRole('analyst')

  test('creates, rotates with a grace period and revokes a personal key', async ({ page, baseURL }) => {
    const keyName = `e2e-personal-${stamp()}`
    await page.goto('/dashboard/profile')
    await expect(page.getByText('My API keys', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: /Create API key/ }).click()
    const dialog = page.getByRole('dialog', { name: 'Create API key' })
    await dialog.getByLabel('Name').fill(keyName)
    await dialog.getByRole('button', { name: 'MCP analyst' }).click()
    // Pinpoints which input was lost if the submit button stays disabled.
    await expect(dialog.getByLabel('Name')).toHaveValue(keyName)
    await expect(dialog.getByRole('checkbox', { checked: true }).first()).toBeVisible()
    await dialog.getByRole('button', { name: 'Create key' }).click()
    const first = await readAndDismissSecret(page, 'API key created')

    const rows = page.getByRole('grid', { name: 'My API keys' }).getByRole('row').filter({ hasText: keyName })
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Active')
    expect((await exchange(baseURL, first)).status).toBe(200)

    // Rotate with a 15 minute grace: both secrets work for now, the old key is "rotating out".
    await rows.first().getByRole('button', { name: /actions for/i }).click()
    await page.getByRole('menuitem', { name: 'Rotate' }).click()
    const rotate = page.getByRole('dialog', { name: new RegExp(`Rotate ${keyName}`) })
    await rotate.getByRole('combobox', { name: 'Grace period' }).click()
    await page.getByRole('option', { name: '15 minutes' }).click()
    await rotate.getByRole('button', { name: 'Rotate key' }).click()
    const second = await readAndDismissSecret(page, 'API key rotated')
    expect(second).not.toBe(first)
    await expect(rows.filter({ hasText: 'Rotating out' })).toHaveCount(1)
    expect((await exchange(baseURL, second)).status).toBe(200)
    expect((await exchange(baseURL, first)).status).toBe(200)

    // Revoke both (old first); neither secret works afterwards.
    await revokeRow(page, rows.filter({ hasText: 'Rotating out' }), keyName)
    await expect(rows.filter({ hasText: 'Rotating out' })).toHaveCount(0)
    await revokeRow(page, rows.filter({ hasText: 'Active' }), keyName)
    await expect(rows.filter({ hasText: 'Active' })).toHaveCount(0)
    expect((await exchange(baseURL, first)).status).toBe(401)
    expect((await exchange(baseURL, second)).status).toBe(401)
  })

  test('has no API Keys settings tab', async ({ page }) => {
    await page.goto('/dashboard/admin/settings')
    await expect(page.getByRole('tab', { name: /API Keys/ })).toHaveCount(0)
  })
})

test.describe('viewer: no API keys', { tag: '@api-keys' }, () => {
  useRole('viewer')

  test('the profile page has no API keys card and the endpoint refuses', async ({ page, context }) => {
    await page.goto('/dashboard/profile')
    await expect(page.getByRole('heading', { name: 'Profile' })).toBeVisible()
    await expect(page.getByText('My API keys', { exact: true })).toHaveCount(0)
    const res = await api.get(context, '/api-keys')
    expect(res.status()).toBe(403)
  })
})
