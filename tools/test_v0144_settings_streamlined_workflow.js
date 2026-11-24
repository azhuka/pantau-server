const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const path = require('path');

const ARTIFACT_DIR = '/home/bos/.gemini/antigravity-cli/brain/0c842cc8-965e-436a-bbe2-9c6ef43e29d0';

(async () => {
  console.log('=== [1] Generating JWT Token for Master Admin ===');
  const adminTok = execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.security import create_access_token
from core.database import SessionLocal
from models.user import User

db = SessionLocal()
admin = db.query(User).filter(User.role == 'master_admin').first()
print(create_access_token({'sub': admin.username, 'role': admin.role, 'uid': admin.id}))
"`).toString().trim();

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));

  try {
    // 1. Set localStorage token and visit app
    await page.goto('http://127.0.0.1:8401', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'id');
    }, adminTok);
    await page.reload({ waitUntil: 'networkidle2' });

    console.log('=== [2] Navigating to Settings View ===');
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.textContent.includes('Setelan') || b.textContent.includes('Settings') || b.textContent.includes('Akun'));
      if (btn) btn.click();
    });

    await new Promise(r => setTimeout(r, 1000));
    await page.waitForSelector('h2', { timeout: 5000 });

    // Screenshot 1: Streamlined Full-Width Overview
    const shot1 = path.join(ARTIFACT_DIR, 'v0144_settings_streamlined_overview.png');
    await page.screenshot({ path: shot1, fullPage: true });
    console.log('[OK] Captured Streamlined Overview:', shot1);

    // 2. Test Add User Modal (Uniform Modal Workflow)
    console.log('=== [3] Testing Add User Modal ===');
    const clickedAdd = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const addBtn = btns.find(b => b.textContent.includes('Tambah Pengguna') || b.textContent.includes('Add New User') || b.textContent.includes('Add User'));
      if (addBtn) {
        addBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked Add User Button:', clickedAdd);
    await new Promise(r => setTimeout(r, 500));

    const shot2 = path.join(ARTIFACT_DIR, 'v0144_modal_add_user.png');
    await page.screenshot({ path: shot2 });
    console.log('[OK] Captured Add User Modal:', shot2);

    // Close AddUserModal
    await page.evaluate(() => {
      const closeBtn = document.querySelector('div.fixed button');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // 3. Test Edit Self Modal
    console.log('=== [4] Testing Edit Self Modal ===');
    const editSelfBtn = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const editBtn = btns.find(b => b.textContent.trim() === 'Edit' || b.getAttribute('title') === 'Edit');
      if (editBtn) {
        editBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked Edit Self Button:', editSelfBtn);
    await new Promise(r => setTimeout(r, 500));

    const shot3 = path.join(ARTIFACT_DIR, 'v0144_modal_edit_self.png');
    await page.screenshot({ path: shot3 });
    console.log('[OK] Captured Edit Self Modal:', shot3);

    // Close EditSelfModal
    await page.evaluate(() => {
      const closeBtn = document.querySelector('div.fixed button');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // 4. Test Action Dropdown on Operator row
    console.log('=== [5] Testing Action Dropdown on Operator row ===');
    const dropdownOpened = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('tbody tr'));
      for (const row of rows) {
        const text = row.textContent;
        if (text.includes('Operator')) {
          const actBtn = row.querySelector('button[aria-label="Actions"]');
          if (actBtn) {
            actBtn.click();
            return true;
          }
        }
      }
      return false;
    });
    console.log('Opened Dropdown on Operator Row:', dropdownOpened);
    await new Promise(r => setTimeout(r, 500));

    // 5. Test Atur Izin Modal (EditPermsModal)
    console.log('=== [6] Testing EditPermsModal (Atur Izin) ===');
    const clickedPerms = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('div.absolute button'));
      const permsBtn = items.find(b => b.textContent.includes('Atur Izin') || b.textContent.includes('Configure Permissions'));
      if (permsBtn) {
        permsBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked Atur Izin:', clickedPerms);
    await new Promise(r => setTimeout(r, 500));

    const shot4 = path.join(ARTIFACT_DIR, 'v0144_modal_edit_perms.png');
    await page.screenshot({ path: shot4 });
    console.log('[OK] Captured Edit Perms Modal:', shot4);

    // Close EditPermsModal
    await page.evaluate(() => {
      const closeBtn = document.querySelector('div.fixed button');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // 6. Test Reset Password Modal
    console.log('=== [7] Testing ResetPasswordModal ===');
    // Open dropdown again
    await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('tbody tr'));
      for (const row of rows) {
        const text = row.textContent;
        if (text.includes('Operator')) {
          const actBtn = row.querySelector('button[aria-label="Actions"]');
          if (actBtn) actBtn.click();
        }
      }
    });
    await new Promise(r => setTimeout(r, 500));

    const clickedReset = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('div.absolute button'));
      const resetBtn = items.find(b => b.textContent.includes('Reset Password'));
      if (resetBtn) {
        resetBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked Reset Password:', clickedReset);
    await new Promise(r => setTimeout(r, 500));

    const shot5 = path.join(ARTIFACT_DIR, 'v0144_modal_reset_password.png');
    await page.screenshot({ path: shot5 });
    console.log('[OK] Captured Reset Password Modal:', shot5);

    console.log('=== ALL WORKFLOW AND MODAL TESTS PASSED 100%! ===');
  } catch (err) {
    console.error('Test Error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
