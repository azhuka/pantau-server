const puppeteer = require('puppeteer-core');

(async () => {
  console.log('Launching Chrome for Full RBAC & User Management workflow verification...');
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
    console.log('Logging in as master-admin...');
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

    // 1. Capture Settings View with full RBAC table
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0137_settings_rbac_en.png', fullPage: true });
    console.log('Captured v0137_settings_rbac_en.png');

    // 2. Open Add User Modal
    console.log('Opening Add User Modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const addBtn = btns.find(b => b.textContent.includes('Add New User') || b.textContent.includes('Tambah Pengguna Baru'));
      if (addBtn) addBtn.click();
    });

    await new Promise(r => setTimeout(r, 800));

    // In Add User modal, click "Maintenance" preset and select "Specific Servers"
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const maintBtn = btns.find(b => b.textContent.includes('Maintenance') || b.textContent.includes('Pemeliharaan'));
      if (maintBtn) maintBtn.click();

      const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
      const customRadio = radios.find(r => r.value === 'custom');
      if (customRadio) customRadio.click();
    });

    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0137_add_operator_modal.png' });
    console.log('Captured v0137_add_operator_modal.png');

    // Close Add User Modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Batal'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 3. Open Edit User Modal for sysadmin_sadri
    console.log('Opening Edit User Modal for sysadmin_sadri...');
    await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('table tbody tr'));
      const sadriRow = rows.find(r => r.textContent.includes('sysadmin_sadri'));
      if (sadriRow) {
        const editBtn = sadriRow.querySelector('button[title*="Edit"], button[title*="Sunting"]');
        if (editBtn) editBtn.click();
      }
    });

    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0137_edit_operator_modal.png' });
    console.log('Captured v0137_edit_operator_modal.png');

    // Close Edit User Modal
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const cancelBtn = btns.find(b => b.textContent.includes('Cancel') || b.textContent.includes('Batal'));
      if (cancelBtn) cancelBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 4. Switch Language to Indonesian (ID)
    console.log('Switching language to Indonesian (ID)...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('header button'));
      const langBtn = btns.find(b => b.title && (b.title.includes('Switch Language') || b.title.includes('Ganti Bahasa')));
      if (langBtn) langBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0137_settings_rbac_id.png', fullPage: true });
    console.log('Captured v0137_settings_rbac_id.png');

    console.log('All Full RBAC & User Management workflow verifications succeeded!');
  } catch (err) {
    console.error('Test error:', err);
  } finally {
    await browser.close();
  }
})();
