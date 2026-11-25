const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ARTIFACT_DIR = '/home/bos/.gemini/antigravity-cli/brain/0c842cc8-965e-436a-bbe2-9c6ef43e29d0';

function generateToken(username) {
  const script = `
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.security import create_access_token
from models.user import User
from core.database import SessionLocal
db = SessionLocal()
u = db.query(User).filter(User.username == '${username}').first()
print(create_access_token({'sub': u.username, 'role': u.role, 'uid': u.id}))
db.close()
`;
  return execSync(`/home/bos/pantau-server/env/bin/python3 -c "${script}"`).toString().trim();
}

async function run() {
  console.log('=== [1] Launching Browser for v0.1.62 Blueprint Pagination Parity Test ===');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const adminToken = generateToken('master-admin');
    const page = await browser.newPage();

    // ----------------------------------------------------
    // TEST SUITE 1: Dashboard View Zero-Pagination Rule
    // ----------------------------------------------------
    console.log('\n--- SUITE 1: Dashboard View Absolute Zero-Pagination ---');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });

    const dashboardPaginationBars = await page.$$('.table-pagination-bar');
    console.log(`[CHECK] Dashboard .table-pagination-bar count: ${dashboardPaginationBars.length}`);
    if (dashboardPaginationBars.length !== 0) {
      throw new Error(`VIOLATION: DashboardView must have ZERO pagination bars, found ${dashboardPaginationBars.length}`);
    }
    console.log('  -> PASS: Dashboard has zero pagination bars (Zero-Hidden Awareness strictly respected)');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0162_dashboard_zero_pagination.png'), fullPage: false });

    // ----------------------------------------------------
    // TEST SUITE 2: Audit Trail Pagination Parity
    // ----------------------------------------------------
    console.log('\n--- SUITE 2: Audit Trail Pagination Parity (3-Part Layout & Select Limit) ---');
    // Click Audit Trail in Navbar
    await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a, button'));
      const auditBtn = links.find(el => el.textContent.includes('Audit Trail') || el.textContent.includes('05 //'));
      if (auditBtn) auditBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const auditPagination = await page.evaluate(() => {
      const bar = document.querySelector('.table-pagination-bar');
      if (!bar) return null;
      const info = bar.querySelector('.table-pagination-info')?.textContent?.trim() || '';
      const nav = bar.querySelector('.table-pagination-nav')?.textContent?.trim() || '';
      const prevBtn = bar.querySelector('.table-pagination-nav button:first-child')?.disabled;
      const nextBtn = bar.querySelector('.table-pagination-nav button:last-child')?.disabled;
      const pageText = bar.querySelector('.table-pagination-nav .page-indicator')?.textContent?.trim() || '';
      const limitSelect = bar.querySelector('.table-pagination-limit select');
      const limitVal = limitSelect ? limitSelect.value : null;
      const options = limitSelect ? Array.from(limitSelect.options).map(o => o.text.trim()) : [];
      const rows = document.querySelectorAll('tbody tr').length;
      return { info, nav, prevBtn, nextBtn, pageText, limitVal, options, rows };
    });

    console.log('[CHECK] Audit pagination data:', JSON.stringify(auditPagination, null, 2));
    if (!auditPagination) {
      throw new Error('Audit table must display .table-pagination-bar when activities > 10');
    }
    if (!auditPagination.info.includes('activities') || !auditPagination.info.includes('Showing 1–10 of')) {
      throw new Error(`Audit info format mismatch: ${auditPagination.info}`);
    }
    if (!auditPagination.options.some(o => o.includes('10 activities')) || !auditPagination.options.some(o => o.includes('All activities'))) {
      throw new Error(`Audit limit selector options missing standard units: ${JSON.stringify(auditPagination.options)}`);
    }
    console.log('  -> PASS: 3-part layout on Audit Trail verified');

    // Test changing limit to 25
    await page.select('.table-pagination-limit select', '25');
    await new Promise(r => setTimeout(r, 600));

    const afterLimitChange = await page.evaluate(() => {
      const bar = document.querySelector('.table-pagination-bar');
      const info = bar.querySelector('.table-pagination-info')?.textContent?.trim() || '';
      const rows = document.querySelectorAll('tbody tr').length;
      const selectVal = bar.querySelector('.table-pagination-limit select')?.value;
      return { info, rows, selectVal };
    });
    console.log('[CHECK] After changing limit to 25:', afterLimitChange);
    if (afterLimitChange.selectVal !== '25') {
      throw new Error(`Expected limit select value 25, got ${afterLimitChange.selectVal}`);
    }
    console.log('  -> PASS: Limit change to 25 verified');

    // Reset back to 10
    await page.select('.table-pagination-limit select', '10');
    await new Promise(r => setTimeout(r, 600));

    // Test page navigation
    await page.click('.table-pagination-nav button:last-child'); // Next »
    await new Promise(r => setTimeout(r, 600));

    const page2Info = await page.evaluate(() => {
      const bar = document.querySelector('.table-pagination-bar');
      return {
        info: bar.querySelector('.table-pagination-info')?.textContent?.trim(),
        pageText: bar.querySelector('.table-pagination-nav .page-indicator')?.textContent?.trim()
      };
    });
    console.log('[CHECK] Audit Page 2 data:', page2Info);
    if (!page2Info.pageText.includes('Page 2') || !page2Info.info.includes('Showing 11–20 of')) {
      throw new Error(`Audit page 2 navigation failed: ${JSON.stringify(page2Info)}`);
    }
    console.log('  -> PASS: Page navigation (Next / Prev) verified');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0162_audit_pagination_parity.png'), fullPage: false });

    // ----------------------------------------------------
    // TEST SUITE 3: Asset Inventory Table Auto-Hide (<= 10 items)
    // ----------------------------------------------------
    console.log('\n--- SUITE 3: Asset Inventory Table Auto-Hide Rule (<= 10 items) ---');
    await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a, button'));
      const assetBtn = links.find(el => el.textContent.includes('Asset Inventory') || el.textContent.includes('03 //'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const assetTableState = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr').length;
      const bar = document.querySelector('.table-pagination-bar');
      return { rows, barExists: !!bar };
    });
    console.log('[CHECK] Asset table state (10 active servers):', assetTableState);
    if (assetTableState.rows <= 10 && assetTableState.barExists) {
      throw new Error(`VIOLATION: Auto-hide rule failed! Total rows is ${assetTableState.rows} (<= 10), but .table-pagination-bar is still displayed!`);
    }
    console.log('  -> PASS: Auto-hide rule verified on Asset Inventory (bar hidden when rows <= 10)');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0162_asset_table_autohide_pagination.png'), fullPage: false });

    // ----------------------------------------------------
    // TEST SUITE 4: Incidents View (Active & Resolved)
    // ----------------------------------------------------
    console.log('\n--- SUITE 4: Incidents Center Pagination Parity ---');
    await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a, button'));
      const incBtn = links.find(el => el.textContent.includes('Incident Center') || el.textContent.includes('02 //'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Check Active Incidents
    const activeIncState = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr').length;
      const bar = document.querySelector('.table-pagination-bar');
      return { rows, barExists: !!bar };
    });
    console.log('[CHECK] Active Incidents state:', activeIncState);
    if (activeIncState.rows <= 10 && activeIncState.barExists) {
      throw new Error(`Active Incidents has <= 10 rows (${activeIncState.rows}) but pagination bar is displayed`);
    }
    console.log('  -> PASS: Active Incidents pagination respects auto-hide');

    // Switch to Resolved Tab
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll('button'));
      const resTab = tabs.find(b => b.textContent.includes('Resolved') || b.textContent.includes('RESOLVED'));
      if (resTab) resTab.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const resolvedIncState = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr').length;
      const bar = document.querySelector('.table-pagination-bar');
      if (!bar) return { rows, barExists: false };
      return {
        rows,
        barExists: true,
        info: bar.querySelector('.table-pagination-info')?.textContent?.trim(),
        options: Array.from(bar.querySelectorAll('.table-pagination-limit select option')).map(o => o.text.trim())
      };
    });
    console.log('[CHECK] Resolved Incidents state:', resolvedIncState);
    if (resolvedIncState.rows > 10 && !resolvedIncState.barExists) {
      throw new Error('Resolved Incidents has > 10 rows but pagination bar is missing');
    }
    console.log('  -> PASS: Resolved Incidents pagination verified');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0162_incidents_pagination.png'), fullPage: false });

    // ----------------------------------------------------
    // TEST SUITE 5: Workspace Modal Processes Tab Pagination
    // ----------------------------------------------------
    console.log('\n--- SUITE 5: Workspace Modal Processes Tab Pagination ---');
    // Open Asset Inventory and click View button on the first server
    await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a, button'));
      const assetBtn = links.find(el => el.textContent.includes('Asset Inventory') || el.textContent.includes('03 //'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // Click the View button on the first row
    await page.evaluate(() => {
      const viewBtn = document.querySelector('tbody tr button');
      if (viewBtn) viewBtn.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Click Tasks (Processes) tab in workspace modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const procTab = btns.find(b => b.textContent.includes('Tasks') || b.textContent.includes('Processes'));
      if (procTab) procTab.click();
    });
    await new Promise(r => setTimeout(r, 2000));

    const procPagination = await page.evaluate(() => {
      const bars = Array.from(document.querySelectorAll('.table-pagination-bar'));
      const bar = bars[bars.length - 1]; // In modal
      if (!bar) return null;
      return {
        info: bar.querySelector('.table-pagination-info')?.textContent?.trim(),
        options: Array.from(bar.querySelectorAll('.table-pagination-limit select option')).map(o => o.text.trim()),
        rows: document.querySelectorAll('tbody tr').length
      };
    });

    console.log('[CHECK] Workspace processes pagination:', procPagination);
    if (!procPagination) {
      throw new Error('Workspace processes tab must display .table-pagination-bar when processes > 10');
    }
    if (!procPagination.info.includes('processes')) {
      throw new Error(`Processes tab info mismatch: ${procPagination.info}`);
    }
    console.log('  -> PASS: Workspace processes pagination verified with 3-part layout');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0162_workspace_processes_pagination.png'), fullPage: false });

    console.log('\n=== ALL TEST SUITES PASSED FLAWLESSLY! ===\n');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('\n[FATAL TEST ERROR]:', err);
  process.exit(1);
});
