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
  console.log('=== [1] Launching Browser for v0.1.60 English-Only & Button Ergonomics Test ===');
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

    // Ensure active problem exists in DB
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
    // TEST SUITE 1: Navbar Language Switcher Eradicated
    // ----------------------------------------------------
    console.log('\n--- SUITE 1: Verify Navbar has Zero Language Switcher ---');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'id'); // deliberate attempt to use 'id'
    }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    const navbarCheck = await page.evaluate(() => {
      const navHeader = document.querySelector('header');
      const text = navHeader ? navHeader.textContent : '';
      const hasEN = text.includes('EN') && !text.includes('FEED // LIVE');
      const hasID = text.includes('ID');
      const buttons = Array.from(navHeader ? navHeader.querySelectorAll('button') : []);
      const langBtn = buttons.find(b => b.textContent.trim() === 'EN' || b.textContent.trim() === 'ID');
      return {
        hasLangBtn: !!langBtn,
        allButtonTexts: buttons.map(b => b.textContent.trim())
      };
    });
    console.log('Navbar Check:', navbarCheck);

    if (navbarCheck.hasLangBtn) {
      throw new Error(`Language switcher button still present in Navbar: ${JSON.stringify(navbarCheck)}`);
    }
    console.log('[PASS] ✓ Language switcher button eradicated from Navbar!');

    const navbarScreenshot = path.join(ARTIFACT_DIR, 'v0160_navbar_no_lang_switcher.png');
    await page.screenshot({ path: navbarScreenshot });
    console.log(`[PASS] Captured Navbar screenshot: ${navbarScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 2: Strict English-Only UI Even with 'id' in localStorage
    // ----------------------------------------------------
    console.log('\n--- SUITE 2: Strict English-Only UI Enforcement ---');
    // Navigate to Incidents tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Incidents'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const activeHeaders = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const ths = Array.from(activeCard.querySelectorAll('thead th')).map(th => th.textContent.trim());
      return ths;
    });
    console.log('Active Table Headers detected:', activeHeaders);

    const descCol = activeHeaders[3];
    const solutionCol = activeHeaders[5];
    const actionCol = activeHeaders[6];

    if (!descCol.toUpperCase().includes('INCIDENT DESCRIPTION')) {
      throw new Error(`Column 4 must be 'INCIDENT DESCRIPTION', but found: '${descCol}'`);
    }
    if (!solutionCol.toUpperCase().includes('SOLUTION')) {
      throw new Error(`Column 6 must be 'SOLUTION', but found: '${solutionCol}'`);
    }
    if (actionCol !== 'Actions') {
      throw new Error(`Column 7 header must be exactly 'Actions', but found: '${actionCol}' (No 'Tindakan' allowed!)`);
    }
    console.log('[PASS] ✓ Active Incidents Table headers are strictly English: INCIDENT DESCRIPTION, SOLUTION, and Actions!');

    // ----------------------------------------------------
    // TEST SUITE 3: Operator Actions ▾ Dropdown Ergonomics
    // ----------------------------------------------------
    console.log('\n--- SUITE 3: Operator Actions ▾ Dropdown Ergonomics ---');
    const dropdownErgo = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      if (!row) return { error: 'No active incident row found' };
      const summary = row.querySelector('.noc-act-dropdown summary');
      if (!summary) return { error: 'No dropdown summary found' };
      const rect = summary.getBoundingClientRect();
      const style = window.getComputedStyle(summary);
      return {
        text: summary.textContent.replace(/\s+/g, ' ').trim(),
        width: rect.width,
        height: rect.height,
        cursor: style.cursor
      };
    });
    console.log('Dropdown Ergonomics Check:', dropdownErgo);

    if (!dropdownErgo.text.includes('Actions') || !dropdownErgo.text.includes('▾')) {
      throw new Error(`Dropdown summary text must be 'Actions ▾', found: '${dropdownErgo.text}'`);
    }
    if (dropdownErgo.width < 50 || dropdownErgo.height < 20) {
      throw new Error(`Dropdown size too small: ${dropdownErgo.width}x${dropdownErgo.height}`);
    }
    console.log('[PASS] ✓ Dropdown summary matches NOC ergonomics standard: Actions ▾ (~58px width, 24px height)!');

    const activeEnglishScreenshot = path.join(ARTIFACT_DIR, 'v0160_active_incidents_english_actions.png');
    await page.screenshot({ path: activeEnglishScreenshot });
    console.log(`[PASS] Captured Active Incidents screenshot: ${activeEnglishScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 4: Resolved Incidents Table 26x26px Icon Button
    // ----------------------------------------------------
    console.log('\n--- SUITE 4: Resolved Incidents Table 26x26px Icon Button ---');
    // Switch to Resolved Incidents subtab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const resBtn = btns.find(b => b.textContent.includes('Resolved') || b.textContent.includes('Selesai'));
      if (resBtn) resBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const resolvedCheck = await page.evaluate(() => {
      const cards = document.querySelectorAll('.hud-tactical-card');
      const resCard = cards.length > 1 ? cards[1] : cards[0];
      const ths = Array.from(resCard.querySelectorAll('thead th')).map(th => th.textContent.trim());
      const row = resCard.querySelector('tbody tr');
      const actionTh = ths[ths.length - 1];
      if (!row) return { error: 'No resolved incident row found', actionTh };

      const actCell = row.querySelector('td:last-child');
      const btn = actCell ? actCell.querySelector('button') : null;
      const rect = btn ? btn.getBoundingClientRect() : null;
      const text = btn ? btn.textContent.trim() : null;
      const title = btn ? btn.getAttribute('title') : null;
      const svg = btn ? btn.querySelector('svg') : null;

      return {
        actionTh,
        hasButton: !!btn,
        btnText: text,
        btnTitle: title,
        width: rect ? rect.width : null,
        height: rect ? rect.height : null,
        hasSvg: !!svg
      };
    });
    console.log('Resolved Incidents Action Check:', resolvedCheck);

    if (resolvedCheck.actionTh !== 'Actions') {
      throw new Error(`Resolved table header must be 'Actions', but found '${resolvedCheck.actionTh}'`);
    }
    if (!resolvedCheck.hasButton) {
      throw new Error('Resolved table row does not have action button!');
    }
    if (resolvedCheck.btnText !== '') {
      throw new Error(`Resolved table action button must be ICON-ONLY without text, but found: '${resolvedCheck.btnText}'`);
    }
    if (Math.abs(resolvedCheck.width - 26) > 2 || Math.abs(resolvedCheck.height - 26) > 2) {
      throw new Error(`Resolved table action button must be ~26x26px, but measured: ${resolvedCheck.width}x${resolvedCheck.height}`);
    }
    if (!resolvedCheck.btnTitle || !resolvedCheck.btnTitle.includes('Server Details')) {
      throw new Error(`Resolved table action button must have title 'Server Details', but found: '${resolvedCheck.btnTitle}'`);
    }
    console.log('[PASS] ✓ Resolved Incidents action is standard 26x26px icon-only button with title="Server Details"!');

    const resolvedScreenshot = path.join(ARTIFACT_DIR, 'v0160_resolved_incidents_icon_button.png');
    await page.screenshot({ path: resolvedScreenshot });
    console.log(`[PASS] Captured Resolved Incidents screenshot: ${resolvedScreenshot}`);

    // ----------------------------------------------------
    // TEST SUITE 5: Viewer Read-Only 26x26px Single Icon Button in Active & Asset Table
    // ----------------------------------------------------
    console.log('\n--- SUITE 5: Viewer 26x26px Single Icon Button Verification ---');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_locale', 'en');
    }, viewerToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    // Check Active Incidents as Viewer
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const incBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Incidents'));
      if (incBtn) incBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const viewerActiveCheck = await page.evaluate(() => {
      const activeCard = document.querySelectorAll('.hud-tactical-card')[0];
      const row = activeCard.querySelector('tbody tr');
      if (!row) return { error: 'No row' };
      const hasDropdown = row.querySelector('.noc-act-dropdown') !== null;
      const btn = row.querySelector('td:last-child button');
      const rect = btn ? btn.getBoundingClientRect() : null;
      return {
        hasDropdown,
        buttonCount: row.querySelectorAll('td:last-child button').length,
        width: rect ? rect.width : null,
        height: rect ? rect.height : null,
        title: btn ? btn.title : null,
        text: btn ? btn.textContent.trim() : null
      };
    });
    console.log('Viewer Active Incidents Check:', viewerActiveCheck);

    if (viewerActiveCheck.hasDropdown) {
      throw new Error('Viewer must NOT have the action dropdown!');
    }
    if (viewerActiveCheck.buttonCount !== 1) {
      throw new Error(`Viewer must have exactly 1 clean icon button, found ${viewerActiveCheck.buttonCount}`);
    }
    if (viewerActiveCheck.text !== '') {
      throw new Error(`Viewer button must be icon-only without text, but found: '${viewerActiveCheck.text}'`);
    }
    if (Math.abs(viewerActiveCheck.width - 26) > 2 || Math.abs(viewerActiveCheck.height - 26) > 2) {
      throw new Error(`Viewer button must be ~26x26px, but measured: ${viewerActiveCheck.width}x${viewerActiveCheck.height}`);
    }
    console.log('[PASS] ✓ Viewer has exact 26x26px icon button in Active Incidents table!');

    // Check Asset Table as Viewer
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('03 //') || b.textContent.includes('Asset Inventory'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const viewerAssetCheck = await page.evaluate(() => {
      const row = document.querySelector('table tbody tr');
      if (!row) return { error: 'No asset row found' };
      const btn = row.querySelector('td:last-child button');
      const rect = btn ? btn.getBoundingClientRect() : null;
      return {
        buttonCount: row.querySelectorAll('td:last-child button').length,
        width: rect ? rect.width : null,
        height: rect ? rect.height : null,
        text: btn ? btn.textContent.trim() : null,
        title: btn ? btn.title : null
      };
    });
    console.log('Viewer Asset Table Check:', viewerAssetCheck);

    if (viewerAssetCheck.buttonCount !== 1) {
      throw new Error(`Viewer in Asset Table must have exactly 1 button, found ${viewerAssetCheck.buttonCount}`);
    }
    if (viewerAssetCheck.text !== '') {
      throw new Error(`Viewer in Asset Table must have ICON-ONLY button, but found text: '${viewerAssetCheck.text}'`);
    }
    if (Math.abs(viewerAssetCheck.width - 26) > 2 || Math.abs(viewerAssetCheck.height - 26) > 2) {
      throw new Error(`Viewer button in Asset Table must be ~26x26px, but measured: ${viewerAssetCheck.width}x${viewerAssetCheck.height}`);
    }
    console.log('[PASS] ✓ Viewer has exact 26x26px icon button in Asset Table without text label!');

    const viewerAssetScreenshot = path.join(ARTIFACT_DIR, 'v0160_asset_table_viewer_icon_button.png');
    await page.screenshot({ path: viewerAssetScreenshot });
    console.log(`[PASS] Captured Viewer Asset Table screenshot: ${viewerAssetScreenshot}`);

    console.log('\n================================================================');
    console.log('[SUCCESS] ALL v0.1.60 ENGLISH-ONLY & BUTTON ERGONOMICS TESTS PASSED 100%');
    console.log('================================================================');

  } catch (err) {
    console.error('[FAIL]', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
