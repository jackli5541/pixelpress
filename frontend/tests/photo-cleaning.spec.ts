import { expect, test, type Page, type Route } from '@playwright/test'

type Decision = 'keep' | 'remove' | null

function photo(id: string, decision: Decision = null) {
  return {
    id,
    filename: `${id}.jpg`,
    size: 120_000,
    url: `/api/v1/photos/${id}/file`,
    width: 1600,
    height: 1200,
    quality_score: 7.5,
    cleaning_issues: decision === null ? ['closed_eyes_suspected'] : [],
    cleaning: {
      suggestion: decision === null ? 'review' : 'keep',
      review_status: decision === 'remove' ? 'removed' : decision === 'keep' ? 'kept' : 'pending_review',
      confidence: 0.75,
      decision,
      decision_source: decision === null ? null : 'user',
      excluded: decision === 'remove',
      analysis_version: 'b2-local-v3',
      features: {
        sharpness: { score: 0.75, severity: 'ok', hard_reject: false },
        exposure: { score: 0.8, severity: 'ok' },
        resolution: { score: 0.75, width: 1600, height: 1200 },
        composition: { orientation: 'landscape', aspect_ratio: 1.333 },
        faces: { available: true, detected_count: 1, aggregate: { closed_eye_suspected_count: 1 } },
      },
    },
  }
}

function envelope(data: unknown) {
  return { code: 0, message: 'ok', request_id: 'test-request', data }
}

function summary(items: ReturnType<typeof photo>[], pendingReview: number) {
  const removed = items.filter((item) => item.cleaning.excluded).length
  return {
    total: items.length,
    retained: items.length - removed,
    keep: items.length - pendingReview,
    review: pendingReview,
    remove: 0,
    excluded: removed,
    pending_review: pendingReview,
    included: 0,
    kept: items.filter((item) => item.cleaning.decision === 'keep').length,
    removed,
    duplicate_groups: 0,
    analysis_failures: 0,
  }
}

async function mockCleaningApi(page: Page, options: { duplicate?: boolean; failPatch?: boolean; pending?: boolean } = {}) {
  let revision = 3
  let items = options.duplicate ? [photo('photo-1'), photo('photo-2')] : [photo('photo-1', options.pending === false ? 'keep' : null)]
  let queue = options.pending === false ? [] : options.duplicate
    ? [{
        id: 'group:group-1',
        kind: 'duplicate_group',
        photo_ids: ['photo-1', 'photo-2'],
        group_id: 'group-1',
        preferred_photo_id: 'photo-1',
        reason_codes: ['duplicate_burst', 'closed_eyes_suspected'],
        priority: 80,
        suggested_action: 'accept_preferred',
        policy_version: 'cleaning-policy-v3',
      }]
    : [{
        id: 'photo:photo-1',
        kind: 'single_photo',
        photo_ids: ['photo-1'],
        group_id: null,
        preferred_photo_id: null,
        reason_codes: ['closed_eyes_suspected'],
        priority: 80,
        suggested_action: 'keep',
        policy_version: 'cleaning-policy-v3',
      }]

  const results = () => ({
    album_id: 'album-1',
    analysis_version: 'b2-local-v3',
    review_session_id: 'review-session-1',
    content_revision: revision,
    summary: summary(items, queue.length),
    review_queue: queue,
    groups: [],
    items,
  })

  await page.addInitScript(() => window.localStorage.setItem('pixpress1_access_token', 'test-token'))
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/users/me') {
      return route.fulfill({ json: envelope({ authenticated: true, id: 'user-1', username: 'tester', role: 'user' }) })
    }
    if (path === '/api/v1/albums/album-1') {
      return route.fulfill({ json: envelope({ id: 'album-1', name: '测试相册', status: 'cleaned', content_revision: revision }) })
    }
    if (path === '/api/v1/albums/album-1/tasks') {
      return route.fulfill({ json: envelope([]) })
    }
    if (path === '/api/v1/albums/album-1/clean/results') {
      return route.fulfill({ json: envelope(results()) })
    }
    if (path === '/api/v1/albums/album-1/clean/decisions' && request.method() === 'PATCH') {
      if (options.failPatch) return route.fulfill({ status: 500, json: { detail: 'forced failure' } })
      const body = request.postDataJSON() as { photo_ids: string[]; decision: Exclude<Decision, null> }
      items = items.map((item) => body.photo_ids.includes(item.id)
        ? {
            ...item,
            cleaning: {
              ...item.cleaning,
              decision: body.decision,
              decision_source: 'user',
              review_status: body.decision === 'remove' ? 'removed' : 'kept',
              excluded: body.decision === 'remove',
            },
          }
        : item)
      revision += 1
      return route.fulfill({ json: envelope({
        changed_items: items.filter((item) => body.photo_ids.includes(item.id)),
        summary: summary(items, queue.length),
        content_revision: revision,
        remaining_review_count: queue.length,
      }) })
    }
    if (path === '/api/v1/albums/album-1/clean/review/resolve' && request.method() === 'POST') {
      const body = request.postDataJSON() as { action: string }
      items = items.map((item, index) => {
        const decision: Exclude<Decision, null> = options.duplicate
          ? body.action === 'keep_all' || index === 0 ? 'keep' : 'remove'
          : body.action === 'remove' ? 'remove' : 'keep'
        return {
          ...item,
          cleaning: {
            ...item.cleaning,
            decision,
            decision_source: 'user',
            review_status: decision === 'remove' ? 'removed' : 'kept',
            excluded: decision === 'remove',
          },
        }
      })
      queue = []
      revision += 1
      return route.fulfill({ json: envelope({
        changed_items: items,
        summary: summary(items, 0),
        content_revision: revision,
        remaining_review_count: 0,
      }) })
    }
    if (path === '/api/v1/albums/album-1/clean/review/resolve-remaining' && request.method() === 'POST') {
      const resolvedReviewCount = queue.length
      items = items.map((item, index) => {
        const decision: Exclude<Decision, null> = options.duplicate && index > 0 ? 'remove' : 'keep'
        return {
          ...item,
          cleaning: {
            ...item.cleaning,
            decision,
            decision_source: 'user_delegated',
            review_status: decision === 'remove' ? 'removed' : 'kept',
            excluded: decision === 'remove',
          },
        }
      })
      queue = []
      revision += 1
      return route.fulfill({ json: envelope({
        resolved_review_count: resolvedReviewCount,
        changed_items: items,
        summary: summary(items, 0),
        content_revision: revision,
        remaining_review_count: 0,
      }) })
    }
    if (path.startsWith('/api/v1/photos/')) {
      return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="12"><rect width="16" height="12" fill="#b8a995"/></svg>' })
    }
    return route.fulfill({ status: 404, json: { detail: `unmocked ${path}` } })
  })
}

test('opens review once and moves a photo between the two pools without reload', async ({ page }) => {
  await mockCleaningApi(page)
  await page.goto('/albums/album-1/cleaning')

  await expect(page.getByRole('dialog', { name: '照片复核' })).toBeVisible()
  await page.getByRole('button', { name: '剩余全部交给系统' }).click()
  await expect(page.getByText('将从当前项开始')).toBeVisible()
  await page.getByRole('button', { name: '确认全部交给系统' }).click()
  await expect(page.getByRole('dialog', { name: '照片复核' })).toBeHidden()
  await expect(page.getByRole('button', { name: '保留（1）' })).toBeVisible()

  await page.getByRole('button', { name: '移除照片', exact: true }).click()
  await expect(page.getByRole('button', { name: '保留（0）' })).toBeVisible()
  await page.getByRole('button', { name: '已移除（1）' }).click()
  await expect(page.getByRole('button', { name: '恢复保留' })).toBeVisible()
  await page.getByRole('button', { name: '恢复保留' }).click()
  await expect(page.getByRole('button', { name: '已移除（0）' })).toBeVisible()
})

test('keeps the photo pool at a fixed internal scroll height', async ({ page }) => {
  await mockCleaningApi(page, { pending: false })
  await page.goto('/albums/album-1/cleaning')

  const pool = page.locator('[aria-label="照片池"]')
  await expect(pool).toBeVisible()
  const style = await pool.evaluate((element) => {
    const computed = window.getComputedStyle(element)
    return { height: Number.parseFloat(computed.height), overflowY: computed.overflowY }
  })
  expect(style.height).toBeGreaterThanOrEqual(360)
  expect(style.overflowY).toBe('auto')
})

test('resolves a duplicate group atomically', async ({ page }) => {
  await mockCleaningApi(page, { duplicate: true })
  await page.goto('/albums/album-1/cleaning')

  await expect(page.getByText('相似照片选择')).toBeVisible()
  await page.getByRole('button', { name: '采用首选' }).click()
  await expect(page.getByRole('dialog', { name: '照片复核' })).toBeHidden()
  await expect(page.getByRole('button', { name: '保留（1）' })).toBeVisible()
  await expect(page.getByRole('button', { name: '已移除（1）' })).toBeVisible()
})

test('rolls back an optimistic move when the decision request fails', async ({ page }) => {
  await mockCleaningApi(page, { pending: false, failPatch: true })
  await page.goto('/albums/album-1/cleaning')

  await page.getByRole('button', { name: '移除照片', exact: true }).click()
  await expect(page.getByText('forced failure')).toBeVisible()
  await expect(page.getByRole('button', { name: '保留（1）' })).toBeVisible()
  await expect(page.getByRole('button', { name: '移除照片', exact: true })).toBeVisible()
})
