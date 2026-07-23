import { expect, test, type Page, type Route } from '@playwright/test'

test.describe.configure({ mode: 'serial', timeout: 60_000 })

type ThemeDecision = 'keep' | 'review' | 'exclude'

interface MockOptions {
  phase: 'needs_analysis' | 'review_theme_photos' | 'ready_to_cluster'
  photos: ReturnType<typeof photo>[]
  assessments?: ReturnType<typeof assessment>[]
  chapters?: ReturnType<typeof chapter>[]
}

function photo(id: string) {
  return {
    id,
    filename: `${id}.jpg`,
    size: 120_000,
    url: `/api/v1/albums/album-1/photos/${id}/content`,
  }
}

function assessment(id: string, decision: ThemeDecision) {
  return {
    photo: photo(id),
    relevance_score: decision === 'keep' ? 0.9 : decision === 'review' ? 0.5 : 0.1,
    relevance_label: decision === 'keep' ? 'relevant' : decision === 'review' ? 'uncertain' : 'off_theme',
    suggested_decision: decision,
    user_decision: null,
    effective_decision: decision,
    reasons: [decision === 'keep' ? 'cross_modal_match' : decision === 'review' ? 'cross_modal_uncertain' : 'cross_modal_mismatch'],
    relevance_evidence: { calibrated: true },
    scoring_version: 'test-v1',
  }
}

function chapter(id: string, name: string, photoIds: string[]) {
  return {
    id,
    name,
    description: `${name}描述`,
    order: 1,
    photo_ids: photoIds,
    segments: photoIds.length ? [
      {
        id: `${id}-segment-a`,
        name: '活动阶段 1',
        description: '前半段',
        order: 1,
        segment_type: 'activity',
        time_range: null,
        photo_ids: photoIds.slice(0, 30),
      },
      {
        id: `${id}-segment-b`,
        name: '活动阶段 2',
        description: '后半段',
        order: 2,
        segment_type: 'activity',
        time_range: null,
        photo_ids: photoIds.slice(30),
      },
    ] : [],
  }
}

function envelope(data: unknown) {
  return { code: 0, message: 'ok', request_id: 'test-request', data }
}

async function mockChapterApi(page: Page, options: MockOptions) {
  let assessments = [...(options.assessments || [])]
  let chapters = [...(options.chapters || [])]
  const imageRequests: string[] = []
  const moves: Array<{ photoIds: string[]; targetChapterId: string }> = []

  function themeWorkspace() {
    const kept = assessments.filter((item) => item.effective_decision === 'keep').length
    const review = assessments.filter((item) => item.effective_decision === 'review').length
    const excluded = assessments.filter((item) => item.effective_decision === 'exclude').length
    return {
      enabled: true,
      phase: options.phase,
      strategies: ['balanced', 'activity_first', 'time_first', 'location_first'],
      profile: options.phase === 'needs_analysis' ? null : {
        id: 'profile-1',
        status: options.phase === 'ready_to_cluster' ? 'confirmed' : 'review_pending',
        title: '完整记录',
        candidates: [],
        chapter_strategy: 'balanced',
        fallback_used: false,
      },
      assessments,
      calibration: {
        status: 'ready',
        auto_decision_enabled: true,
        decision_mode: 'calibrated',
        provisional_threshold: null,
        version: 'test-v1',
        provider: 'test',
        model: 'test',
        dimension: 3,
        query_version: 'test-v1',
        scoring_version: 'test-v1',
      },
      summary: {
        total: assessments.length,
        kept,
        suggested_exclude: excluded,
        uncertain: review,
        review,
        excluded,
      },
    }
  }

  await page.addInitScript(() => window.localStorage.setItem('pixpress1_access_token', 'test-token'))
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/v1/users/me') {
      return route.fulfill({ json: envelope({ authenticated: true, id: 'user-1', username: 'tester', role: 'user' }) })
    }
    if (path === '/api/v1/albums/album-1') {
      return route.fulfill({ json: envelope({ id: 'album-1', name: '测试相册', status: 'cleaned' }) })
    }
    if (path === '/api/v1/albums/album-1/tasks') {
      return route.fulfill({ json: envelope([]) })
    }
    if (path === '/api/v1/albums/album-1/photos' && request.method() === 'GET') {
      return route.fulfill({ json: envelope({ album_id: 'album-1', count: options.photos.length, items: options.photos }) })
    }
    if (path === '/api/v1/albums/album-1/chapters' && request.method() === 'GET') {
      return route.fulfill({ json: envelope(chapters) })
    }
    if (path === '/api/v1/albums/album-1/theme-workspace') {
      return route.fulfill({ json: envelope(themeWorkspace()) })
    }
    if (path === '/api/v1/albums/album-1/theme-review/decisions' && request.method() === 'PATCH') {
      const body = request.postDataJSON() as { photo_ids: string[]; decision: 'keep' | 'exclude' | null }
      assessments = assessments.map((item) => body.photo_ids.includes(item.photo.id)
        ? {
            ...item,
            user_decision: body.decision,
            effective_decision: body.decision || item.suggested_decision,
          }
        : item)
      return route.fulfill({ json: envelope({ updated_count: body.photo_ids.length }) })
    }
    if (path === '/api/v1/albums/album-1/chapters/move-photos' && request.method() === 'POST') {
      const body = request.postDataJSON() as { photo_ids: string[]; target_chapter_id: string }
      moves.push({ photoIds: body.photo_ids, targetChapterId: body.target_chapter_id })
      chapters = chapters.map((item) => {
        const remainingIds = item.photo_ids.filter((id) => !body.photo_ids.includes(id))
        const targetIds = item.id === body.target_chapter_id ? [...remainingIds, ...body.photo_ids] : remainingIds
        return { ...item, photo_ids: targetIds }
      })
      return route.fulfill({ json: envelope({ moved: body.photo_ids.length }) })
    }
    if (path.endsWith('/content')) {
      imageRequests.push(path)
      return route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="12"><rect width="16" height="12" fill="#b8a995"/></svg>',
      })
    }
    return route.fulfill({ status: 404, json: { detail: `unmocked ${request.method()} ${path}` } })
  })

  return { imageRequests, moves }
}

async function expectFixedPool(pool: ReturnType<Page['locator']>) {
  await expect(pool).toBeVisible()
  const style = await pool.evaluate((element) => {
    const computed = window.getComputedStyle(element)
    return { height: Number.parseFloat(computed.height), overflowY: computed.overflowY }
  })
  expect(style.height).toBeGreaterThanOrEqual(360)
  expect(style.overflowY).toBe('auto')
}

test('renders the pending archive pool in batches of 24', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  const photos = Array.from({ length: 60 }, (_, index) => photo(`pending-${String(index + 1).padStart(3, '0')}`))
  const state = await mockChapterApi(page, { phase: 'needs_analysis', photos })
  await page.goto('/albums/album-1/chapters', { waitUntil: 'domcontentloaded' })

  const pool = page.getByRole('region', { name: '待归档镜头照片池' })
  await expectFixedPool(pool)
  await expect(pool.locator('[data-photo-id]')).toHaveCount(24)
  await expect.poll(() => state.imageRequests.length).toBe(24)

  await pool.evaluate((element) => element.scrollTo({ top: element.scrollHeight }))
  await expect.poll(() => pool.locator('[data-photo-id]').count()).toBeGreaterThan(24)
})

test('resets theme pools on tab changes and keeps decisions functional', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  const kept = Array.from({ length: 60 }, (_, index) => assessment(`kept-${String(index + 1).padStart(3, '0')}`, 'keep'))
  const removed = Array.from({ length: 60 }, (_, index) => assessment(`removed-${String(index + 1).padStart(3, '0')}`, 'exclude'))
  const photos = [...kept, ...removed].map((item) => item.photo)
  await mockChapterApi(page, { phase: 'review_theme_photos', photos, assessments: [...kept, ...removed] })
  await page.goto('/albums/album-1/chapters', { waitUntil: 'domcontentloaded' })

  const keptPool = page.getByRole('region', { name: '已保留照片池' })
  await expectFixedPool(keptPool)
  await expect(keptPool.locator('[data-photo-id]')).toHaveCount(24)
  await keptPool.evaluate((element) => element.scrollTo({ top: element.scrollHeight }))
  await expect.poll(() => keptPool.locator('[data-photo-id]').count()).toBeGreaterThan(24)

  await keptPool.locator('input[type="checkbox"]').first().check()
  await expect(page.getByText('已选 1 张')).toBeVisible()
  await page.getByRole('tab', { name: '已移出 60' }).click()
  const removedPool = page.getByRole('region', { name: '已移出照片池' })
  await expect(removedPool.locator('[data-photo-id]')).toHaveCount(24)
  await expect(page.getByText('已选 1 张')).toBeHidden()

  await page.getByRole('tab', { name: '已保留 60' }).click()
  await expect(keptPool.locator('[data-photo-id]')).toHaveCount(24)
  await keptPool.getByRole('button', { name: '移出照片' }).first().click()
  await expect(page.getByRole('tab', { name: '已保留 59' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '已移出 61' })).toBeVisible()
})

test('uses one progressive pool per expanded chapter and keeps orphan drag actions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const assigned = Array.from({ length: 60 }, (_, index) => `assigned-${String(index + 1).padStart(3, '0')}`)
  const orphaned = Array.from({ length: 60 }, (_, index) => `orphan-${String(index + 1).padStart(3, '0')}`)
  const photos = [...assigned, ...orphaned].map(photo)
  const state = await mockChapterApi(page, {
    phase: 'ready_to_cluster',
    photos,
    chapters: [chapter('chapter-a', '第一章', assigned), chapter('chapter-b', '第二章', [])],
  })
  await page.goto('/albums/album-1/chapters', { waitUntil: 'domcontentloaded' })

  const orphanPool = page.getByRole('region', { name: '未分配镜头照片池' })
  await expectFixedPool(orphanPool)
  await expect(orphanPool.locator('[data-photo-id]')).toHaveCount(24)

  const firstChapter = page.locator('[data-chapter-id="chapter-a"]')
  await firstChapter.getByRole('button', { name: '展开章节' }).click()
  const chapterPool = page.getByRole('region', { name: '第一章照片池' })
  await expectFixedPool(chapterPool)
  await expect(chapterPool.locator('[data-photo-id]')).toHaveCount(24)
  await chapterPool.evaluate((element) => element.scrollTo({ top: element.scrollHeight }))
  await expect.poll(() => chapterPool.locator('[data-photo-id]').count()).toBeGreaterThan(24)

  const viewportFits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
  expect(viewportFits).toBe(true)

  const orphanCard = orphanPool.locator('[data-photo-id="orphan-001"]')
  const targetChapter = page.locator('[data-chapter-id="chapter-b"]')
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer())
  await orphanCard.dispatchEvent('dragstart', { dataTransfer })
  await targetChapter.dispatchEvent('dragover', { dataTransfer })
  await targetChapter.dispatchEvent('drop', { dataTransfer })
  await orphanCard.dispatchEvent('dragend', { dataTransfer })
  await expect.poll(() => state.moves.length).toBe(1)
  expect(state.moves[0]).toEqual({ photoIds: ['orphan-001'], targetChapterId: 'chapter-b' })
})
