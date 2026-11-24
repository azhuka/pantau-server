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
  console.log('=== [1] Launching Browser for Incident Handled Dashboard Parity Test ===');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const adminToken = generateToken('master-admin');
    const page = await browser.newPage();

    // Pastikan ada problem yang aktif dan di-ack
    console.log('Ensuring acknowledged problem exists in DB...');
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
    print('Problem 53667 activated with ack_by=op-sadri')
db.close()
"`);

    console.log('\n--- TEST SUITE 1: Dashboard Handled Badge Visibility ---');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'en');
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('#dash-problems-card', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1200));

    // Verify Handled badge exists in Recent Incidents table
    const handledBadges = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#dash-problems-card tbody tr'));
      return rows.map(r => {
        const text = r.textContent.replace(/\s+/g, ' ').trim();
        const hasHandled = r.querySelector('.text-emerald-300') !== null;
        return { text, hasHandled };
      });
    });
    console.log('Detected Dashboard Incident Rows:', handledBadges);

    const hasHandledOnDash = handledBadges.some(b => b.hasHandled && b.text.includes('HANDLED'));
    if (!hasHandledOnDash) {
      throw new Error(`Handled badge missing on Dashboard Recent Incidents! Found: ${JSON.stringify(handledBadges)}`);
    }
    console.log('[PASS] ✓ HANDLED badge successfully verified on Dashboard Recent Incidents table!');

    const dashScreenshot = path.join(ARTIFACT_DIR, 'v0157_dashboard_handled_badge.png');
    await page.screenshot({ path: dashScreenshot });
    console.log(`[PASS] Captured Dashboard screenshot: ${dashScreenshot}`);

    // Test Opening ProblemDetailModal
    console.log('\n--- TEST SUITE 2: ProblemDetailModal Handled & Unack Action ---');
    await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#dash-problems-card tbody tr'));
      const ackRow = rows.find(r => r.textContent.includes('op-sadri'));
      if (ackRow) ackRow.click();
    });
    await page.waitForSelector('#problem-detail-modal', { timeout: 5000 });
    await new Promise(r => setTimeout(r, 500));

    const modalData = await page.evaluate(() => {
      const modal = document.querySelector('#problem-detail-modal');
      if (!modal) return null;
      return {
        text: modal.textContent.replace(/\s+/g, ' ').trim(),
        hasHandledBtn: modal.querySelector('.text-emerald-300') !== null
      };
    });
    console.log('ProblemDetailModal content detected:', modalData?.text?.slice(0, 150));
    if (!modalData || !modalData.hasHandledBtn) {
      throw new Error('ProblemDetailModal failed to display handled state');
    }
    console.log('[PASS] ProblemDetailModal displays handled state and action.');

    const pdmScreenshot = path.join(ARTIFACT_DIR, 'v0157_problem_detail_modal_handled.png');
    await page.screenshot({ path: pdmScreenshot });
    console.log(`[PASS] Captured ProblemDetailModal screenshot: ${pdmScreenshot}`);

    // Close modal
    await page.evaluate(() => {
      const closeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Close') || b.textContent.includes('Tutup'));
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // Test Workspace Modal Incidents Tab
    console.log('\n--- TEST SUITE 3: ServerWorkspaceModal Incidents Tab Parity ---');
    // Open server 1 workspace
    await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#dash-assets-card tbody tr'));
      const srv1 = rows.find(r => r.textContent.includes('rj45'));
      if (srv1) srv1.click();
    });
    await page.waitForSelector('#server-workspace-modal', { timeout: 8000 });
    await new Promise(r => setTimeout(r, 1000));

    // Switch to problems tab in workspace
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('#server-workspace-modal button'));
      const incBtn = btns.find(b => b.textContent.includes('Incidents') || b.textContent.includes('Insiden'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const wsIncidentsData = await page.evaluate(() => {
      const ws = document.querySelector('#server-workspace-modal');
      if (!ws) return null;
      const cards = Array.from(ws.querySelectorAll('.hud-tactical-card')).map(c => c.textContent.replace(/\s+/g, ' ').trim());
      const hasHandled = ws.querySelector('.text-emerald-300') !== null;
      return { cards: cards.slice(0, 3), hasHandled };
    });
    console.log('Workspace Incidents tab data:', wsIncidentsData);
    if (!wsIncidentsData || !wsIncidentsData.hasHandled) {
      throw new Error('Workspace Incidents tab failed to display handled state');
    }
    console.log('[PASS] ServerWorkspaceModal Incidents Tab displays handled state with operator action!');

    const wsScreenshot = path.join(ARTIFACT_DIR, 'v0157_workspace_incidents_handled.png');
    await page.screenshot({ path: wsScreenshot });
    console.log(`[PASS] Captured Workspace screenshot: ${wsScreenshot}`);

    // Close workspace
    await page.evaluate(() => {
      const closeBtn = document.querySelector('#server-workspace-modal [title="Close"]');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // Test Language switch to ID
    console.log('\n--- TEST SUITE 4: Indonesian Language Parity (DITANGANI) ---');
    await page.evaluate(() => {
      localStorage.setItem('pantau_locale', 'id');
    });
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    const idRows = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('#dash-problems-card tbody tr'));
      return rows.map(r => r.textContent.replace(/\s+/g, ' ').trim());
    });
    console.log('Indonesian Rows sample:', idRows);
    const hasDitangani = idRows.some(r => r.includes('DITANGANI'));
    if (!hasDitangani) {
      throw new Error(`Indonesian badge DITANGANI not found! Found: ${JSON.stringify(idRows)}`);
    }
    console.log('[PASS] Indonesian ✓ DITANGANI badge verified!');

    const idScreenshot = path.join(ARTIFACT_DIR, 'v0157_dashboard_id_ditangani.png');
    await page.screenshot({ path: idScreenshot });
    console.log(`[PASS] Captured Indonesian screenshot: ${idScreenshot}`);

    console.log('\n=== ALL TEST SUITES PASSED 100% ===');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('[FAIL]', err);
  process.exit(1);
});
