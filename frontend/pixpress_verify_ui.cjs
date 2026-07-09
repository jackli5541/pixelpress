const { chromium } = require('playwright');

(async() => {
  const base = 'http://127.0.0.1:5173';
  const albumId = '33a46d84-1eca-46c5-ba23-55ee15a66ec6';
  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2ZXJpZnlfdXNlcl9ydW50aW1lIiwicm9sZSI6InVzZXIiLCJleHAiOjE3ODMyNjk2MzZ9.mFcJEw8OuAU0qSbN2zVpMlcCAwYwEgPWT9YHJAuVq5Q';
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1600 } });
  await context.addInitScript((value) => {
    window.localStorage.setItem('pixpress1_access_token', value);
  }, token);
  const page = await context.newPage();
  const result = {};

  async function visit(path) {
    await page.goto(`${base}${path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    return (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim();
  }

  const cleaningText = await visit(`/albums/${albumId}/cleaning`);
  result.cleaningHasTaskCard = cleaningText.includes('镜头筛选任务');
  result.cleaningHasSummary = cleaningText.includes('总计 1 张') || cleaningText.includes('总计 1张');
  result.cleaningSnippet = cleaningText.slice(0, 700);

  const chapterText = await visit(`/albums/${albumId}/chapters`);
  result.chapterHasTaskCard = chapterText.includes('章节整理任务');
  result.chapterShowsProvider = chapterText.includes('Provider：openai_compatible / gpt-5.4-mini');
  result.chapterHasFallbackText = chapterText.includes('已自动回退到规则流程');
  result.chapterSnippet = chapterText.slice(0, 900);

  const planningText = await visit(`/albums/${albumId}/planning`);
  result.planningHasTaskCardWithoutAction = planningText.includes('任务进行中');
  result.planningHasNoActiveTaskCardAfterRefresh = planningText.includes('页面规划') || planningText.includes('排版渲染');
  result.planningSnippet = planningText.slice(0, 900);

  const exportText = await visit(`/albums/${albumId}/export`);
  result.exportHasTaskCard = exportText.includes('导出任务');
  result.exportShowsFormatSummary = exportText.includes('导出格式：HTML');
  result.exportShowsRecentStatus = exportText.includes('最近导出状态');
  result.exportSnippet = exportText.slice(0, 900);

  await page.screenshot({ path: '/tmp/pixpress-export-page.png', fullPage: true });
  console.log(JSON.stringify(result));
  await browser.close();
})();
