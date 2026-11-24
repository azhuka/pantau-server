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
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });

  try {
    // ----------------------------------------------------
    // TEST 1: MASTER ADMIN ASSET MATRIX
    // ----------------------------------------------------
    console.log('=== [1] Testing Master Admin on Asset Infrastructure Matrix ===');
    const adminToken = generateToken('master-admin');
    const pageAdmin = await browser.newPage();
    await pageAdmin.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageAdmin.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, adminToken);
    await pageAdmin.reload({ waitUntil: 'networkidle2' });
    await pageAdmin.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Switch to Assets tab (02 // Assets)
    await pageAdmin.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Assets'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Verify Asset Matrix table exists
    await pageAdmin.waitForSelector('table tbody tr', { timeout: 10000 });
    const rowCountAdmin = await pageAdmin.evaluate(() => document.querySelectorAll('table tbody tr').length);
    console.log(`Admin Asset Matrix row count: ${rowCountAdmin}`);
    if (rowCountAdmin < 10) {
      throw new Error(`Expected at least 10 rows in Asset Matrix, got ${rowCountAdmin}`);
    }

    // Check pagination bar is hidden (<= 10 items rule)
    const pagBarAdmin = await pageAdmin.$('.table-pagination-bar');
    console.log('Admin pagination bar on 10 nodes (should be null):', pagBarAdmin === null);
    if (pagBarAdmin !== null) {
      throw new Error('Pagination bar is visible for <= 10 rows in Asset Matrix! GEMINI.md Rule 2 violation.');
    }

    // Check table header capitalization (no uppercase class on tr)
    const headerTrClass = await pageAdmin.evaluate(() => {
      const tr = document.querySelector('table thead tr');
      return tr ? tr.className : '';
    });
    console.log('Header <tr> class:', headerTrClass);
    if (headerTrClass.includes('uppercase')) {
      throw new Error('Table header <tr> still has "uppercase" class! GEMINI.md Rule 3 violation.');
    }

    // Check action buttons for admin: Probe and Dropdown must be present
    const adminActionChecks = await pageAdmin.evaluate(() => {
      const probeBtns = document.querySelectorAll('table tbody button[title*="Sync"], table tbody button[title*="Probe"]');
      const dropdownBtns = document.querySelectorAll('table tbody button[aria-label="Actions"]');
      return {
        probeCount: probeBtns.length,
        dropdownCount: dropdownBtns.length
      };
    });
    console.log('Admin Action Buttons:', adminActionChecks);
    if (adminActionChecks.dropdownCount === 0) {
      throw new Error('Master admin should have dropdown action buttons!');
    }

    const adminMatrixPath = path.join(ARTIFACT_DIR, 'v0152_asset_matrix_master_admin.png');
    await pageAdmin.screenshot({ path: adminMatrixPath });
    console.log(`Saved: ${adminMatrixPath}`);

    // Click dropdown button on first server to show teleported dropdown menu
    await pageAdmin.evaluate(() => {
      const dropdownBtn = document.querySelector('table tbody button[aria-label="Actions"]');
      if (dropdownBtn) dropdownBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // Verify Teleported dropdown menu is visible and contains expected actions
    const dropdownActions = await pageAdmin.evaluate(() => {
      const dropdown = document.querySelector('div[style*="position: fixed"][style*="z-index: 100005"]');
      if (!dropdown) return [];
      return Array.from(dropdown.querySelectorAll('button')).map(b => b.textContent.trim());
    });
    console.log('Teleported Dropdown Menu items:', dropdownActions);
    if (dropdownActions.length < 4) {
      throw new Error('Dropdown menu missing expected administrative actions!');
    }

    const adminDropdownPath = path.join(ARTIFACT_DIR, 'v0152_asset_matrix_dropdown.png');
    await pageAdmin.screenshot({ path: adminDropdownPath });
    console.log(`Saved: ${adminDropdownPath}`);

    // Click "Delete Host" to open DeleteHostModal and verify SVG warning icon
    await pageAdmin.evaluate(() => {
      const dropdown = document.querySelector('div[style*="position: fixed"][style*="z-index: 100005"]');
      if (dropdown) {
        const deleteBtn = Array.from(dropdown.querySelectorAll('button')).find(b => b.textContent.toLowerCase().includes('delete'));
        if (deleteBtn) deleteBtn.click();
      }
    });
    await new Promise(r => setTimeout(r, 600));

    // Verify Delete Host Modal has SVG warning icon and NO cartoon emoji
    const deleteModalCheck = await pageAdmin.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return { open: false };
      const hasSvg = modal.querySelector('svg.text-amber-400') !== null;
      const text = modal.textContent;
      const hasEmoji = /[\uD83C-\uDBFF\uDC00-\uDFFF\u2600-\u26FF]/.test(text);
      return { open: true, hasSvg, hasEmoji };
    });
    console.log('DeleteHostModal check:', deleteModalCheck);
    if (deleteModalCheck.hasEmoji) {
      throw new Error('DeleteHostModal contains cartoon emoji! Zero-Emoji violation.');
    }
    if (!deleteModalCheck.hasSvg) {
      throw new Error('DeleteHostModal missing amber warning SVG icon!');
    }

    const deleteModalPath = path.join(ARTIFACT_DIR, 'v0152_delete_modal_svg_icon.png');
    await pageAdmin.screenshot({ path: deleteModalPath });
    console.log(`Saved: ${deleteModalPath}`);

    // Close modal
    await pageAdmin.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 400));
    await pageAdmin.close();

    // ----------------------------------------------------
    // TEST 2: VIEWER (GUEST) READ-ONLY ASSET MATRIX
    // ----------------------------------------------------
    console.log('=== [2] Testing Viewer / Guest on Asset Infrastructure Matrix ===');
    const guestToken = generateToken('guest');
    const pageGuest = await browser.newPage();
    await pageGuest.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageGuest.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, guestToken);
    await pageGuest.reload({ waitUntil: 'networkidle2' });
    await pageGuest.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Switch to Assets tab
    await pageGuest.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Assets'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Check rows count
    const rowCountGuest = await pageGuest.evaluate(() => document.querySelectorAll('table tbody tr').length);
    console.log(`Guest Asset Matrix row count: ${rowCountGuest}`);

    // RBAC AUDIT: Ensure Viewer has ZERO mutation buttons
    const guestActionChecks = await pageGuest.evaluate(() => {
      const probeBtns = document.querySelectorAll('table tbody button[title*="Sync"], table tbody button[title*="Probe"]');
      const dropdownBtns = document.querySelectorAll('table tbody button[aria-label="Actions"]');
      const viewBtns = document.querySelectorAll('table tbody button');
      return {
        probeCount: probeBtns.length,
        dropdownCount: dropdownBtns.length,
        totalButtonCount: viewBtns.length
      };
    });
    console.log('Guest Action Buttons:', guestActionChecks);

    if (guestActionChecks.probeCount > 0) {
      throw new Error(`RBAC Leak! Guest has ${guestActionChecks.probeCount} Probe buttons in DOM!`);
    }
    if (guestActionChecks.dropdownCount > 0) {
      throw new Error(`RBAC Leak! Guest has ${guestActionChecks.dropdownCount} Dropdown action buttons in DOM!`);
    }

    const guestMatrixPath = path.join(ARTIFACT_DIR, 'v0152_asset_matrix_viewer_readonly.png');
    await pageGuest.screenshot({ path: guestMatrixPath });
    console.log(`Saved: ${guestMatrixPath}`);
    await pageGuest.close();

    // ----------------------------------------------------
    // TEST 3: OPERATOR (op-sadri) ASSET MATRIX
    // ----------------------------------------------------
    console.log('=== [3] Testing Operator (op-sadri) on Asset Infrastructure Matrix ===');
    const opToken = generateToken('op-sadri');
    const pageOp = await browser.newPage();
    await pageOp.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageOp.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, opToken);
    await pageOp.reload({ waitUntil: 'networkidle2' });
    await pageOp.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1000));

    // Switch to Assets tab
    await pageOp.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const assetBtn = btns.find(b => b.textContent.includes('02 //') || b.textContent.includes('Assets'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const opMatrixPath = path.join(ARTIFACT_DIR, 'v0152_asset_matrix_operator.png');
    await pageOp.screenshot({ path: opMatrixPath });
    console.log(`Saved: ${opMatrixPath}`);
    await pageOp.close();

    console.log('=== ALL MULTI-ROLE ASSET MATRIX TESTS PASSED 100%! ===');
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
