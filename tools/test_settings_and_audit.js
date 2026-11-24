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

    await page.goto('http://localhost:8401/', { waitUntil: 'domcontentloaded' });

    // Inject token & user into localStorage, setting lang to 'en'
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
      localStorage.setItem('pantau_user', JSON.stringify({
        id: 1,
        username: 'master-admin',
        role: 'master_admin',
        is_master_admin: true
      }));
    }, token);

    // Reload page with authenticated state
    await page.goto('http://localhost:8401/', { waitUntil: 'domcontentloaded' });
    await new Promise(r => setTimeout(r, 1000));

    // 1. Navigate to 04 // Settings
    console.log('Navigating to Settings view...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const btn = btns.find(b => b.textContent.includes('Settings') || b.textContent.includes('04'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Screenshot 1: Settings Default View (English, Edit button on profile, Icon-only dropdown in table)
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0139_settings_en_overview.png', fullPage: true });
    console.log('Saved screenshots/v0139_settings_en_overview.png');

    // 2. Open Action Dropdown on 2nd row (sysadmin_sadri)
    console.log('Clicking icon-only action button in table...');
    await page.evaluate(() => {
      const actBtns = Array.from(document.querySelectorAll('table tbody tr button[title="Actions"]'));
      if (actBtns.length > 1) {
        actBtns[1].click();
      } else if (actBtns.length > 0) {
        actBtns[0].click();
      }
    });
    await new Promise(r => setTimeout(r, 600));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0139_settings_action_dropdown.png', fullPage: true });
    console.log('Saved screenshots/v0139_settings_action_dropdown.png');

    // 3. Open Edit User Modal (clicking Edit inside dropdown)
    console.log('Opening Edit User Modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('div.absolute button'));
      const editBtn = btns.find(b => b.textContent.trim() === 'Edit' || b.textContent.includes('Edit'));
      if (editBtn) editBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0139_edit_user_modal.png', fullPage: true });
    console.log('Saved screenshots/v0139_edit_user_modal.png');

    // Close Edit modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 4. Open 2FA Setup Modal
    console.log('Opening Setup 2FA Modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const enable2faBtn = btns.find(b => b.textContent.includes('Enable 2FA Now'));
      if (enable2faBtn) enable2faBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0139_setup_2fa_modal.png', fullPage: true });
    console.log('Saved screenshots/v0139_setup_2fa_modal.png');

    // Close 2FA modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Done'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 5. Navigate to 03 // Audit Trail
    console.log('Navigating to Audit Trail view...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const btn = btns.find(b => b.textContent.includes('Audit') || b.textContent.includes('03'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0139_audit_trail_en.png', fullPage: true });
    console.log('Saved screenshots/v0139_audit_trail_en.png');

    console.log('All automated verification screenshots captured successfully!');
  } catch (err) {
    console.error('Test error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
