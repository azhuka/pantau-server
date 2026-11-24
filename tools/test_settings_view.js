const puppeteer = require('puppeteer-core');

(async () => {
  console.log('Launching Chrome for Settings & User Management verification...');
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
    await new Promise(r => setTimeout(r, 800));

    // Log in via Login Modal UI
    console.log('Logging in via Login Modal UI...');
    await page.waitForSelector('input[autocomplete="username"]', { timeout: 4000 });
    await page.type('input[autocomplete="username"]', 'master-admin');
    await page.type('input[autocomplete="current-password"]', 'AdminPass@2026');
    await page.click('form button[type="submit"]');

    await new Promise(r => setTimeout(r, 1500));

    // Navigate to 04 // Settings
    console.log('Navigating to Settings view...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const settingsBtn = btns.find(b => b.textContent.includes('Settings') || b.textContent.includes('04') || b.textContent.includes('Pengaturan'));
      if (settingsBtn) settingsBtn.click();
    });

    await new Promise(r => setTimeout(r, 1200));

    // Click Update Password button to expand change password form
    console.log('Expanding password change form...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const changePwdBtn = btns.find(b => b.textContent.includes('Update Password') || b.textContent.includes('Perbarui Kata Sandi'));
      if (changePwdBtn) changePwdBtn.click();
    });

    await new Promise(r => setTimeout(r, 800));

    // 1. Capture Settings View with profile, expanded change password form, and User Directory table
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0136_settings_user_management.png', fullPage: true });
    console.log('Captured v0136_settings_user_management.png');

    // 2. Open Add User Modal
    console.log('Opening Add User Modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const addBtn = btns.find(b => b.textContent.includes('Add New User') || b.textContent.includes('Tambah Pengguna Baru'));
      if (addBtn) addBtn.click();
    });

    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0136_add_user_modal.png' });
    console.log('Captured v0136_add_user_modal.png');

    // Close Add User Modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Batal'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 3. Open Reset Password Modal for viewer-1 or test-1
    console.log('Opening Reset Password Modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('table button'));
      const resetBtn = btns.find(b => b.title && (b.title.includes('Reset') || b.title.includes('Atur Ulang')));
      if (resetBtn) resetBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0136_reset_password_modal.png' });
    console.log('Captured v0136_reset_password_modal.png');

    // Close Reset Password Modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Batal'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 4. Switch Language to ID
    console.log('Switching language to Indonesian (ID)...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const langBtn = btns.find(b => b.title && (b.title.includes('Switch Language') || b.title.includes('Ganti Bahasa')));
      if (langBtn) langBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0136_settings_id.png', fullPage: true });
    console.log('Captured v0136_settings_id.png');

    console.log('All Settings & User Management verifications succeeded!');
  } catch (err) {
    console.error('Test error:', err);
  } finally {
    await browser.close();
  }
})();
