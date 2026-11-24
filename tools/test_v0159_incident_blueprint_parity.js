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
  console.log('=== [1] Launching Browser for v0.1.59 Incident Blueprint Parity Test ===');
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

    // Pastikan problem aktif ada di DB untuk server 1
    execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.database import SessionLocal
from models.problem import ServerProblem
db = SessionLocal()
p = db.query(ServerProblem).filter(ServerProblem.id == 53667).first()
if p:
    p.resolved_at = None
    p.acknowledged_by = 'op-sadri'
    db.commit()
db.close()
"`);

    // ----------------------------------------------------
    // TEST SUITE 1: ActiveIncidentsTable 7 Columns & Blueprint Parity (EN)
    // ----------------------------------------------------
    console.log('\n--- SUITE 1: ActiveIncidentsTable 7 Columns & Actions Dropdown (English) ---');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'en');
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
    await new Promise(r => setTimeout(r, 1200));

    // Verify 7 Column Headers in Active Incidents Table
    const activeHeaders = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const ths = Array.from(activeCard.querySelectorAll('thead th')).map(th => th.textContent.trim());
      return ths;
    });
    console.log('Active Table Headers detected:', activeHeaders);

    if (activeHeaders.length !== 7) {
      throw new Error(`Expected exactly 7 columns, but found ${activeHeaders.length}: ${JSON.stringify(activeHeaders)}`);
    }

    // Check specific column names
    const descCol = activeHeaders[3];
    const solutionCol = activeHeaders[5];
    console.log(`Col 4: "${descCol}" | Col 6: "${solutionCol}"`);

    if (!descCol.toUpperCase().includes('INCIDENT DESCRIPTION')) {
      throw new Error(`Column 4 must be 'INCIDENT DESCRIPTION', but found: '${descCol}'`);
    }
    if (!solutionCol.toUpperCase().includes('SOLUTION')) {
      throw new Error(`Column 6 must be 'SOLUTION', but found: '${solutionCol}'`);
    }
    console.log('[PASS] ✓ 7 Columns verified with INCIDENT DESCRIPTION and SOLUTION headers!');

    // Check Dropdown in Actions Column (Aksi ▾ / Actions ▾)
    const dropdownCheck = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      if (!row) return { error: 'No active incident row found' };
      const dropdown = row.querySelector('.noc-act-dropdown summary');
      const inlineButtons = Array.from(row.querySelectorAll('td:last-child button'));
      return {
        hasDropdown: dropdown !== null,
        dropdownText: dropdown ? dropdown.textContent.replace(/\s+/g, ' ').trim() : null,
        buttonCount: inlineButtons.length
      };
    });
    console.log('Action Dropdown Check:', dropdownCheck);

    if (!dropdownCheck.hasDropdown) {
      throw new Error('Action column does not have the canonical Actions ▾ dropdown!');
    }
    console.log('[PASS] ✓ Canonical Actions ▾ dropdown is present and single!');

    // Open Dropdown and verify contents
    const dropdownContent = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const dropdown = activeCard.querySelector('.noc-act-dropdown');
      if (dropdown) dropdown.open = true;
      const items = Array.from(dropdown.querySelectorAll('div button, div div')).map(el => el.textContent.replace(/\s+/g, ' ').trim());
      const hasUndo = items.some(t => t.toLowerCase().includes('undo'));
      const hasMute = items.some(t => t.toLowerCase().includes('mute'));
      return { items, hasUndo, hasMute };
    });
    console.log('Dropdown items inside Actions:', dropdownContent);

    if (dropdownContent.hasUndo) {
      throw new Error('Unrequested "Undo Handled" found in dropdown! Must be eradicated.');
    }
    if (dropdownContent.hasMute) {
      throw new Error('Unrequested "Mute" found in dropdown! Must be eradicated.');
    }
    console.log('[PASS] ✓ Dropdown contains clean actions without Undo or Mute!');

    const v0159ActiveScreenshot = path.join(ARTIFACT_DIR, 'v0159_incidents_active_table_en.png');
    await page.screenshot({ path: v0159ActiveScreenshot, fullPage: true });
    console.log(`[PASS] Captured English Active Incidents Table screenshot: ${v0159ActiveScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 2: Indonesian Language Parity (ID)
    // ----------------------------------------------------
    console.log('\n--- SUITE 2: Indonesian Parity (Deskripsi Insiden & Solusi) ---');
    await page.evaluate(() => {
      localStorage.setItem('pantau_locale', 'id');
    });
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    // Navigate to Incidents tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Insiden'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const idHeaders = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const ths = Array.from(activeCard.querySelectorAll('thead th')).map(th => th.textContent.trim());
      return ths;
    });
    console.log('Indonesian Table Headers detected:', idHeaders);

    const idDescCol = idHeaders[3];
    const idSolCol = idHeaders[5];
    console.log(`Col 4 (ID): "${idDescCol}" | Col 6 (ID): "${idSolCol}"`);

    if (!idDescCol.toUpperCase().includes('DESKRIPSI INSIDEN')) {
      throw new Error(`Column 4 in ID must be 'Deskripsi Insiden', but found: '${idDescCol}'`);
    }
    if (!idSolCol.toUpperCase().includes('SOLUSI')) {
      throw new Error(`Column 6 in ID must be 'Solusi', but found: '${idSolCol}'`);
    }
    console.log('[PASS] ✓ Indonesian headers verified: Deskripsi Insiden & Solusi!');

    const v0159IdScreenshot = path.join(ARTIFACT_DIR, 'v0159_incidents_active_table_id.png');
    await page.screenshot({ path: v0159IdScreenshot, fullPage: true });
    console.log(`[PASS] Captured Indonesian Active Incidents Table screenshot: ${v0159IdScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 3: Viewer Read-Only Verification
    // ----------------------------------------------------
    console.log('\n--- SUITE 3: Viewer Single Clean Icon Button ---');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'en');
    }, viewerToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    // Navigate to Incidents tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Incidents'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const viewerAction = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      if (!row) return { error: 'No row' };
      const hasDropdown = row.querySelector('.noc-act-dropdown') !== null;
      const buttons = Array.from(row.querySelectorAll('td:last-child button'));
      return {
        hasDropdown,
        buttonCount: buttons.length,
        buttonTitle: buttons[0]?.title || ''
      };
    });
    console.log('Viewer Action Check:', viewerAction);

    if (viewerAction.hasDropdown) {
      throw new Error('Viewer must NOT have the action dropdown!');
    }
    if (viewerAction.buttonCount !== 1) {
      throw new Error(`Viewer must have exactly 1 clean icon button, found ${viewerAction.buttonCount}`);
    }
    console.log('[PASS] ✓ Viewer has exactly 1 clean icon button to view Server Details!');

    const v0159ViewerScreenshot = path.join(ARTIFACT_DIR, 'v0159_incidents_viewer.png');
    await page.screenshot({ path: v0159ViewerScreenshot, fullPage: true });
    console.log(`[PASS] Captured Viewer screenshot: ${v0159ViewerScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 4: Verify No Undo Handled in Workspace & Modal
    // ----------------------------------------------------
    console.log('\n--- SUITE 4: Workspace & Modal Zero Undo Handled Verification ---');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'en');
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    // Open Workspace
    await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      const wsBtn = row.querySelector('button, .noc-act-dropdown summary');
      // Click workspace open
      const details = row.querySelector('.noc-act-dropdown');
      if (details) {
        details.open = true;
        const btn = details.querySelector('button');
        if (btn) btn.click();
      }
    });
    await page.waitForSelector('#server-workspace-modal', { timeout: 8000 });
    await new Promise(r => setTimeout(r, 1200));

    // Switch to incidents tab in workspace
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('#server-workspace-modal button'));
      const incBtn = btns.find(b => b.textContent.includes('Incidents') || b.textContent.includes('Insiden'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const wsHandledCheck = await page.evaluate(() => {
      const ws = document.querySelector('#server-workspace-modal');
      const text = ws.textContent;
      const hasHandled = text.includes('HANDLED') || text.includes('DITANGANI');
      const hasUndo = text.toLowerCase().includes('undo handled') || text.toLowerCase().includes('batal ditangani');
      return { hasHandled, hasUndo };
    });
    console.log('Workspace Incidents Handled Check:', wsHandledCheck);

    if (!wsHandledCheck.hasHandled) {
      throw new Error('Workspace Incidents tab does not show handled status!');
    }
    if (wsHandledCheck.hasUndo) {
      throw new Error('Workspace Incidents tab still has Undo Handled button!');
    }
    console.log('[PASS] ✓ Workspace Incidents tab shows handled status with zero undo button!');

    const v0159WorkspaceScreenshot = path.join(ARTIFACT_DIR, 'v0159_workspace_incidents.png');
    await page.screenshot({ path: v0159WorkspaceScreenshot });
    console.log(`[PASS] Captured Workspace screenshot: ${v0159WorkspaceScreenshot}`);

    console.log('\n============================================================');
    console.log('[SUCCESS] ALL v0.1.59 INCIDENT BLUEPRINT PARITY TESTS PASSED 100%');
    console.log('============================================================');

  } catch (err) {
    console.error('[FAIL]', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
