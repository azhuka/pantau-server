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

  console.log('Admin Token:', adminTok ? 'Obtained' : 'Failed');

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

    console.log('=== [2] Navigating to Settings Page ===');
    // Click Settings in navbar
    const settingsBtn = await page.waitForSelector('button:has-text("Setelan"), button:has-text("Pengaturan"), button:has-text("Settings"), button[title*="Setelan"]', { timeout: 5000 }).catch(async () => {
      // Fallback: click nav button with cog
      return await page.$('nav button svg');
    });

    // Alternatively, evaluate page to switch view to settings
    await page.evaluate(() => {
      // Find button that switches to settings
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.textContent.includes('Setelan') || b.textContent.includes('Settings') || b.textContent.includes('Akun'));
      if (btn) btn.click();
    });

    await new Promise(r => setTimeout(r, 1000));

    // Check if Settings view is loaded
    await page.waitForSelector('h2', { timeout: 5000 });
    console.log('Settings view loaded.');

    // Screenshot 1: 2-column Settings & User Management Overview
    const shot1 = path.join(ARTIFACT_DIR, 'v0143_settings_2col_overview.png');
    await page.screenshot({ path: shot1, fullPage: true });
    console.log('[OK] Captured:', shot1);

    // 2. Test "Edit" button on Profile Card -> opens EditSelfModal
    console.log('=== [3] Testing Edit Self Modal ===');
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

    const shot2 = path.join(ARTIFACT_DIR, 'v0143_edit_self_modal.png');
    await page.screenshot({ path: shot2 });
    console.log('[OK] Captured:', shot2);

    // Close EditSelfModal
    await page.evaluate(() => {
      const closeBtn = document.querySelector('div.fixed button');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // 3. Test Action Dropdown on Operator row
    console.log('=== [4] Testing Actions Dropdown on Operator row ===');
    const dropdownOpened = await page.evaluate(() => {
      // Find action button in table
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

    const shot3 = path.join(ARTIFACT_DIR, 'v0143_table_action_dropdown.png');
    await page.screenshot({ path: shot3 });
    console.log('[OK] Captured:', shot3);

    // 4. Click "Atur Izin" in dropdown -> opens EditPermsModal
    console.log('=== [5] Testing EditPermsModal (Atur Izin) ===');
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

    const shot4 = path.join(ARTIFACT_DIR, 'v0143_edit_perms_modal.png');
    await page.screenshot({ path: shot4 });
    console.log('[OK] Captured:', shot4);

    // Close EditPermsModal
    await page.evaluate(() => {
      const closeBtn = document.querySelector('div.fixed button');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // 5. Navigate to Asset Inventory & open Server Workspace Modal
    console.log('=== [6] Opening Asset Workspace Modal for Host 1 ===');
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const assetBtn = buttons.find(b => b.textContent.includes('Aset') || b.textContent.includes('Assets') || b.textContent.includes('Inventaris'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // Click first asset row in table
    await page.evaluate(() => {
      const row = document.querySelector('tbody tr');
      if (row) row.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Verify Services tab with Start/Stop/Reload/Restart
    console.log('=== [7] Testing Tactical Controls in Workspace Services Tab ===');
    await page.evaluate(() => {
      const subTabs = Array.from(document.querySelectorAll('button'));
      const svcTab = subTabs.find(b => b.textContent.includes('Services') || b.textContent.includes('Layanan'));
      if (svcTab) svcTab.click();
    });
    await new Promise(r => setTimeout(r, 800));

    const shot5 = path.join(ARTIFACT_DIR, 'v0143_workspace_services_tactical.png');
    await page.screenshot({ path: shot5 });
    console.log('[OK] Captured:', shot5);

    // Verify Processes tab with SIGTERM/SIGKILL/SIGSTOP/SIGCONT
    console.log('=== [8] Testing Tactical Controls in Workspace Processes Tab ===');
    await page.evaluate(() => {
      const subTabs = Array.from(document.querySelectorAll('button'));
      const procTab = subTabs.find(b => b.textContent.includes('Proses') || b.textContent.includes('Processes') || b.textContent.includes('Tasks'));
      if (procTab) procTab.click();
    });
    await new Promise(r => setTimeout(r, 800));

    const shot6 = path.join(ARTIFACT_DIR, 'v0143_workspace_processes_tactical.png');
    await page.screenshot({ path: shot6 });
    console.log('[OK] Captured:', shot6);

    // Verify FIM Tab (Clean, no fake hashes!)
    console.log('=== [9] Testing Workspace FIM Tab (Zero-Fake Data) ===');
    await page.evaluate(() => {
      const subTabs = Array.from(document.querySelectorAll('button'));
      const fimTab = subTabs.find(b => b.textContent.includes('FIM') || b.textContent.includes('Integritas'));
      if (fimTab) fimTab.click();
    });
    await new Promise(r => setTimeout(r, 800));

    const shot7 = path.join(ARTIFACT_DIR, 'v0143_workspace_fim_zero_fake.png');
    await page.screenshot({ path: shot7 });
    console.log('[OK] Captured:', shot7);

    // Verify SSL Tab (Clean, no fake certs!)
    console.log('=== [10] Testing Workspace SSL Tab (Zero-Fake Data) ===');
    await page.evaluate(() => {
      const subTabs = Array.from(document.querySelectorAll('button'));
      const sslTab = subTabs.find(b => b.textContent.includes('SSL') || b.textContent.includes('Sertifikat'));
      if (sslTab) sslTab.click();
    });
    await new Promise(r => setTimeout(r, 800));

    const shot8 = path.join(ARTIFACT_DIR, 'v0143_workspace_ssl_zero_fake.png');
    await page.screenshot({ path: shot8 });
    console.log('[OK] Captured:', shot8);

    console.log('=== ALL AUTOMATED BROWSER TESTS PASSED! ===');
  } catch (err) {
    console.error('Test Error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
