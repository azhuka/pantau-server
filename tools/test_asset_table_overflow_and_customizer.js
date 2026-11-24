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
  console.log('=== [1] Launching Browser for Asset Matrix Layout & Customizer Test ===');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,950'],
    defaultViewport: { width: 1600, height: 950 }
  });

  try {
    const adminToken = generateToken('master-admin');
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
      localStorage.removeItem('pantau_asset_matrix_columns_v1'); // Start clean
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Navigate to Assets tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Assets'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Verify table rendered
    await page.waitForSelector('table tbody tr', { timeout: 10000 });

    // ----------------------------------------------------
    // CHECK 1: TABLE OVERFLOW & CLIPPING AUDIT AT 1600px
    // ----------------------------------------------------
    console.log('=== [2] Checking Table Container & Overflow Bounds at 1600x950 ===');
    const tableBounds = await page.evaluate(() => {
      const card = document.querySelector('.hud-tactical-card:has(table)');
      const scrollContainer = card ? card.querySelector('.overflow-x-auto') : null;
      const table = document.querySelector('table');
      const thActions = document.querySelector('table thead th:last-child');
      const firstRowActions = document.querySelector('table tbody tr:first-child td:last-child');

      const cardRect = card ? card.getBoundingClientRect() : null;
      const scrollRect = scrollContainer ? scrollContainer.getBoundingClientRect() : null;
      const tableRect = table ? table.getBoundingClientRect() : null;
      const thActionsRect = thActions ? thActions.getBoundingClientRect() : null;
      const firstRowActionsRect = firstRowActions ? firstRowActions.getBoundingClientRect() : null;

      const isScrollable = scrollContainer ? scrollContainer.scrollWidth > scrollContainer.clientWidth : false;
      const rightEdgeClipped = thActionsRect && cardRect ? (thActionsRect.right > cardRect.right + 2) : false;

      return {
        cardWidth: cardRect?.width,
        tableWidth: tableRect?.width,
        scrollWidth: scrollContainer?.scrollWidth,
        clientWidth: scrollContainer?.clientWidth,
        isScrollable,
        thActionsRight: thActionsRect?.right,
        cardRight: cardRect?.right,
        rightEdgeClipped,
        thActionsText: thActions?.textContent?.trim()
      };
    });

    console.log('Table Bounds Report (1600px):', tableBounds);
    if (tableBounds.rightEdgeClipped) {
      throw new Error(`Actions column is CLIPPED past card boundary! thActionsRight=${tableBounds.thActionsRight}, cardRight=${tableBounds.cardRight}`);
    }

    const fullMatrixPath = path.join(ARTIFACT_DIR, 'v0154_asset_matrix_1600_optimized_density.png');
    await page.screenshot({ path: fullMatrixPath });
    console.log(`Saved screenshot: ${fullMatrixPath}`);

    // ----------------------------------------------------
    // CHECK 2: TEST AT 1366px LAPTOP VIEWPORT
    // ----------------------------------------------------
    console.log('=== [3] Checking Table at 1366x768 Laptop Viewport ===');
    await page.setViewport({ width: 1366, height: 768 });
    await new Promise(r => setTimeout(r, 600));

    const tableBounds1366 = await page.evaluate(() => {
      const card = document.querySelector('.hud-tactical-card:has(table)');
      const scrollContainer = card ? card.querySelector('.overflow-x-auto') : null;
      const cardRect = card ? card.getBoundingClientRect() : null;
      const thActions = document.querySelector('table thead th:last-child');
      const thActionsRect = thActions ? thActions.getBoundingClientRect() : null;

      return {
        cardWidth: cardRect?.width,
        scrollWidth: scrollContainer?.scrollWidth,
        clientWidth: scrollContainer?.clientWidth,
        isScrollable: scrollContainer ? scrollContainer.scrollWidth > scrollContainer.clientWidth : false,
        thActionsRight: thActionsRect?.right,
        cardRight: cardRect?.right
      };
    });

    console.log('Table Bounds Report (1366px):', tableBounds1366);
    const laptopMatrixPath = path.join(ARTIFACT_DIR, 'v0154_asset_matrix_1366_compact.png');
    await page.screenshot({ path: laptopMatrixPath });
    console.log(`Saved screenshot: ${laptopMatrixPath}`);

    // Reset viewport to 1600px for remaining tests
    await page.setViewport({ width: 1600, height: 950 });
    await new Promise(r => setTimeout(r, 500));

    // ----------------------------------------------------
    // CHECK 3: COLUMN CUSTOMIZER DROPDOWN TEST
    // ----------------------------------------------------
    console.log('=== [4] Testing Column Customizer Dropdown ===');
    // Find customizer button
    const colBtn = await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Columns') || b.textContent.includes('Kolom'));
      return btn ? btn.textContent.trim() : null;
    });
    console.log('Found Column Customizer Button:', colBtn);
    if (!colBtn) {
      throw new Error('Column Customizer button not found in toolbar!');
    }

    // Click column customizer button to open dropdown
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Columns') || b.textContent.includes('Kolom'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    const dropdownPath = path.join(ARTIFACT_DIR, 'v0154_asset_matrix_columns_dropdown_open.png');
    await page.screenshot({ path: dropdownPath });
    console.log(`Saved screenshot: ${dropdownPath}`);

    // Inspect dropdown contents: presets and column checkboxes
    const dropdownState = await page.evaluate(() => {
      const labels = Array.from(document.querySelectorAll('label')).map(l => l.textContent.trim());
      const presetBtns = Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim());
      return { labels, presetBtns };
    });
    console.log('Dropdown Presets & Items:', dropdownState);

    // Click "Performance" preset
    console.log('=== [5] Applying Performance Preset ===');
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Performance' || b.textContent.trim() === 'Kinerja');
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // Verify visible columns under Performance preset
    const perfColCheck = await page.evaluate(() => {
      const ths = Array.from(document.querySelectorAll('table thead th')).map(th => th.textContent.trim().replace(/[↕\s]+/g, ' '));
      const badge = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Columns') || b.textContent.includes('Kolom'))?.textContent?.trim();
      return { count: ths.length, headers: ths, badge };
    });
    console.log('Performance Preset Active Headers:', perfColCheck);
    if (perfColCheck.count !== 8) {
      throw new Error(`Expected 8 columns in Performance preset, got ${perfColCheck.count}!`);
    }

    const perfPresetPath = path.join(ARTIFACT_DIR, 'v0154_asset_matrix_perf_preset.png');
    await page.screenshot({ path: perfPresetPath });
    console.log(`Saved screenshot: ${perfPresetPath}`);

    // Test Persistence: Reload page and verify Performance columns remained saved
    console.log('=== [6] Testing Persistence across Page Reload ===');
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Assets'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const persistedCount = await page.evaluate(() => document.querySelectorAll('table thead th').length);
    console.log(`Columns after reload: ${persistedCount} (Expected: 8)`);
    if (persistedCount !== 8) {
      throw new Error(`Persistence failed! Expected 8 columns after reload, got ${persistedCount}`);
    }

    // Reset columns back to All (12/12)
    console.log('=== [7] Testing Reset to Default (All Columns) ===');
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Columns') || b.textContent.includes('Kolom'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 400));
    await page.evaluate(() => {
      const resetBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Reset');
      if (resetBtn) resetBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    const resetCount = await page.evaluate(() => document.querySelectorAll('table thead th').length);
    console.log(`Columns after reset: ${resetCount} (Expected: 12)`);
    if (resetCount !== 12) {
      throw new Error(`Reset failed! Expected 12 columns, got ${resetCount}`);
    }

    console.log('=== ALL TESTS PASSED WITH 100% SUCCESS! ===');
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error('Test execution failed:', err);
  process.exit(1);
});
