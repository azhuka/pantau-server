const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');

(async () => {
  console.log('Generating JWT token for master-admin...');
  const token = execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.security import create_access_token
print(create_access_token({'sub': 'master-admin'}))
"`).toString().trim();

  console.log('Token generated:', token.substring(0, 25) + '...');

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });

    // Inject token & user into localStorage
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_user', JSON.stringify({
        id: 1,
        username: 'master-admin',
        role: 'master_admin',
        is_master_admin: true
      }));
    }, token);

    // Reload page with authenticated state
    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // 1. Navigate to 04 // Settings
    console.log('Navigating to Settings view...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const btn = btns.find(b => b.textContent.includes('Settings') || b.textContent.includes('04') || b.textContent.includes('Pengaturan'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Open Dropdown "Actions ▾" on the second row (sysadmin_sadri)
    console.log('Opening Actions ▾ dropdown on operator row...');
    await page.evaluate(() => {
      const dropdownBtns = Array.from(document.querySelectorAll('table tbody tr button'));
      const actBtn = dropdownBtns.find(b => b.textContent.includes('Action') || b.textContent.includes('Aksi'));
      if (actBtn) actBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0138_settings_rbac_dropdown.png', fullPage: true });
    console.log('Saved screenshots/v0138_settings_rbac_dropdown.png');

    // Click "Detail Pengguna" inside dropdown
    console.log('Opening Detail Pengguna (ViewUserModal)...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const detailBtn = btns.find(b => b.textContent.includes('Detail Pengguna') || b.textContent.includes('User Details'));
      if (detailBtn) detailBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0138_view_user_modal.png', fullPage: true });
    console.log('Saved screenshots/v0138_view_user_modal.png');

    // Close Detail modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const closeBtn = btns.find(b => b.textContent.includes('Close') || b.textContent.includes('Tutup'));
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // Switch to Tab 2: Master Control & Ambang Batas
    console.log('Switching to Master Control & Thresholds sub-tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const mcBtn = btns.find(b => b.textContent.includes('Master Control'));
      if (mcBtn) mcBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0138_master_control.png', fullPage: true });
    console.log('Saved screenshots/v0138_master_control.png');

    // 2. Navigate to 03 // Audit Trail
    console.log('Navigating to Audit Trail view...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const btn = btns.find(b => b.textContent.includes('Audit') || b.textContent.includes('03'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0138_audit_trail.png', fullPage: true });
    console.log('Saved screenshots/v0138_audit_trail.png');

    console.log('ALL VERIFICATION SCREENSHOTS CAPTURED SUCCESSFULLY!');
  } catch (err) {
    console.error('Test execution error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
