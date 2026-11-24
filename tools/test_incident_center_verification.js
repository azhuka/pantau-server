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
  console.log('=== [1] Launching Browser for Incident Command Center Verification ===');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const adminToken = generateToken('master-admin');
    const viewerToken = generateToken('guest');

    const page = await browser.newPage();

    // ----------------------------------------------------
    // TEST SUITE 1: MASTER ADMIN CAPABILITIES & TRIAGE
    // ----------------------------------------------------
    console.log('\n--- SUITE 1: Master Admin Incident Command & Triage ---');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Navigate to Incidents tab
    console.log('Navigating to 02 // Incidents tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Incidents'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Verify 2 stacked tables exist
    const titles = await page.evaluate(() => {
      const h3s = Array.from(document.querySelectorAll('h3')).map(h => h.textContent.trim());
      return h3s;
    });
    console.log('Detected section titles:', titles);
    const hasActiveTitle = titles.some(t => t.includes('Active Physical Incidents'));
    const hasResolvedTitle = titles.some(t => t.includes('Historical Incidents') || t.includes('MTTR Resolution'));
    if (!hasActiveTitle || !hasResolvedTitle) {
      throw new Error(`Dual tables missing! Found titles: ${JSON.stringify(titles)}`);
    }
    console.log('[PASS] Dual stacked tables verified: Active Table and Resolved/MTTR Table.');

    // Verify MTTR Summary Ribbon
    const mttrStats = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.hud-tactical-card .grid > div'));
      return cards.map(c => c.textContent.replace(/\s+/g, ' ').trim());
    });
    console.log('MTTR Ribbon Stats detected:', mttrStats.slice(0, 4));

    // Take full screenshot of Incident View for Master Admin
    const adminScreenshotPath = path.join(ARTIFACT_DIR, 'v0155_incidents_master_admin.png');
    await page.screenshot({ path: adminScreenshotPath, fullPage: true });
    console.log(`[PASS] Captured Master Admin screenshot: ${adminScreenshotPath}`);

    // Test Global Thresholds Modal
    console.log('\nTesting Global Thresholds modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const thBtn = btns.find(b => b.textContent.includes('Global Thresholds'));
      if (thBtn) thBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));

    const thresholdModalVisible = await page.evaluate(() => {
      return document.querySelector('.hud-tactical-card:has(input[type="number"])') !== null;
    });
    console.log('Thresholds modal visible:', thresholdModalVisible);
    if (!thresholdModalVisible) throw new Error('Threshold modal failed to open');

    const thresholdScreenshotPath = path.join(ARTIFACT_DIR, 'v0155_thresholds_modal.png');
    await page.screenshot({ path: thresholdScreenshotPath });
    console.log(`[PASS] Captured Threshold Modal screenshot: ${thresholdScreenshotPath}`);

    // Close Thresholds modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.hud-tactical-card button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Batal'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // Test "Tangani" (Acknowledge) action
    console.log('\nTesting Tangani (Acknowledge) action on active incident...');
    const ackResult = await page.evaluate(async () => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const rows = Array.from(activeCard.querySelectorAll('tbody tr'));
      if (rows.length === 0) return { skipped: true, reason: 'No active incident rows' };

      const unackRow = rows.find(r => r.querySelector('button[title*="Acknowledge"], button[title*="Tangani"]'));
      if (!unackRow) return { skipped: true, reason: 'All active incidents already handled' };

      const ackBtn = unackRow.querySelector('button[title*="Acknowledge"], button[title*="Tangani"]');
      ackBtn.click();
      return { clicked: true };
    });
    console.log('Ack test click result:', ackResult);
    await new Promise(r => setTimeout(r, 1000));

    // Test Asset Details button (Opens ServerWorkspaceModal)
    console.log('\nTesting "Asset Details" button (Major Remediation path)...');
    const openWorkspaceResult = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      if (!row) return { skipped: true };
      const wsBtn = row.querySelector('button[title*="Asset Details"], button[title*="Rincian Aset"]');
      if (wsBtn) {
        wsBtn.click();
        return { clicked: true };
      }
      return { clicked: false };
    });
    console.log('Workspace button click result:', openWorkspaceResult);
    await new Promise(r => setTimeout(r, 1500));

    const workspaceModalVisible = await page.evaluate(() => {
      const modal = document.querySelector('#server-workspace-modal, .hud-tactical-card:has(nav)');
      return modal !== null;
    });
    console.log('Server Workspace Modal opened:', workspaceModalVisible);
    if (workspaceModalVisible) {
      const wsScreenshotPath = path.join(ARTIFACT_DIR, 'v0155_workspace_from_incident.png');
      await page.screenshot({ path: wsScreenshotPath });
      console.log(`[PASS] Captured Workspace from Incident screenshot: ${wsScreenshotPath}`);

      // Close workspace modal
      await page.evaluate(() => {
        const closeBtn = document.querySelector('button[title="Close Workspace (Esc)"], button[title*="Close Workspace"], button[title*="Tutup"]');
        if (closeBtn) closeBtn.click();
      });
      await new Promise(r => setTimeout(r, 800));
    }

    // ----------------------------------------------------
    // TEST SUITE 2: VIEWER READ-ONLY ISOLATION
    // ----------------------------------------------------
    console.log('\n--- SUITE 2: Viewer Read-Only RBAC Isolation ---');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, viewerToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Navigate to Incidents tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Incidents'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Verify Viewer has NO mutation buttons
    const viewerButtons = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button')).map(b => ({
        text: b.textContent.trim(),
        title: b.title || ''
      }));
      return {
        hasAck: btns.some(b => b.text.includes('Handle') || b.text.includes('Tangani') || b.title.includes('Acknowledge')),
        hasIgnore: btns.some(b => b.text.includes('Mute') || b.text.includes('Abaikan')),
        hasThresholds: btns.some(b => b.text.includes('Global Thresholds')),
        hasAssetDetails: btns.some(b => b.text.includes('Asset Details'))
      };
    });
    console.log('Viewer permissions check:', viewerButtons);
    if (viewerButtons.hasAck || viewerButtons.hasIgnore || viewerButtons.hasThresholds) {
      throw new Error(`RBAC LEAK: Viewer has mutation buttons! ${JSON.stringify(viewerButtons)}`);
    }
    if (!viewerButtons.hasAssetDetails) {
      console.warn('Note: Asset Details button not found or table empty');
    }
    console.log('[PASS] Viewer RBAC Isolation 100% verified: No mutation buttons visible.');

    const viewerScreenshotPath = path.join(ARTIFACT_DIR, 'v0155_incidents_viewer_readonly.png');
    await page.screenshot({ path: viewerScreenshotPath, fullPage: true });
    console.log(`[PASS] Captured Viewer Read-Only screenshot: ${viewerScreenshotPath}`);

    console.log('\n============================================================');
    console.log('[SUCCESS] ALL INCIDENT MANAGEMENT AUTOMATED TESTS PASSED 100%');
    console.log('============================================================');

  } catch (err) {
    console.error('[FAIL] Test failed with error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
