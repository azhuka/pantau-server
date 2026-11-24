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

    // Screenshot 1: Overview
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0140_settings_overview.png', fullPage: true });
    console.log('Saved screenshots/v0140_settings_overview.png');

    // 2. Test Clicking Edit on Profile Card
    console.log('Testing Edit button on Active User Profile Card...');
    const clickedProfileEdit = await page.evaluate(() => {
      // Find the Edit button in Panel 1 (Profile card)
      const editBtn = document.querySelector('button[title="Edit"]');
      if (editBtn) {
        editBtn.click();
        return true;
      }
      return false;
    });
    console.log('Profile card Edit clicked:', clickedProfileEdit);
    await new Promise(r => setTimeout(r, 800));

    // Check modal content (Self Mode)
    const selfModalCheck = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return { open: false };
      const text = modal.innerText.toUpperCase();
      const pwdInputs = modal.querySelectorAll('input[type="password"]');
      const hasCurrentPwdInput = Array.from(pwdInputs).some(i => i.placeholder.toLowerCase().includes('current'));
      const hasRoleMatrix = text.includes('OPERATOR PERMISSIONS MATRIX');
      return {
        open: true,
        pwdInputCount: pwdInputs.length,
        hasCurrentPwdInput,
        hasRoleMatrix
      };
    });
    console.log('Self modal check:', selfModalCheck);
    if (!selfModalCheck.open || !selfModalCheck.hasCurrentPwdInput || selfModalCheck.hasRoleMatrix || selfModalCheck.pwdInputCount !== 3) {
      throw new Error(`Self modal validation failed: ${JSON.stringify(selfModalCheck)}`);
    }

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0140_edit_self_modal.png', fullPage: true });
    console.log('Saved screenshots/v0140_edit_self_modal.png');

    // Close modal
    await page.evaluate(() => {
      const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Cancel'));
      if (cancel) cancel.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 2b. Test Clicking Edit on OWN user row in Directory Table (master-admin)
    console.log('Testing Edit button on Directory Table for OWN user (master-admin)...');
    await page.evaluate(() => {
      const actBtns = Array.from(document.querySelectorAll('table tbody tr button[title="Actions"]'));
      if (actBtns.length > 0) {
        actBtns[0].click();
      }
    });
    await new Promise(r => setTimeout(r, 600));

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('div.absolute button'));
      const editBtn = btns.find(b => b.textContent.trim() === 'Edit' || b.textContent.includes('Edit'));
      if (editBtn) editBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));

    // Check modal content (Self Mode via table row)
    const selfTableModalCheck = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return { open: false };
      const text = modal.innerText.toUpperCase();
      const pwdInputs = modal.querySelectorAll('input[type="password"]');
      const hasCurrentPwdInput = Array.from(pwdInputs).some(i => i.placeholder.toLowerCase().includes('current'));
      const hasRoleMatrix = text.includes('OPERATOR PERMISSIONS MATRIX');
      return {
        open: true,
        pwdInputCount: pwdInputs.length,
        hasCurrentPwdInput,
        hasRoleMatrix
      };
    });
    console.log('Self table row modal check:', selfTableModalCheck);
    if (!selfTableModalCheck.open || !selfTableModalCheck.hasCurrentPwdInput || selfTableModalCheck.hasRoleMatrix || selfTableModalCheck.pwdInputCount !== 3) {
      throw new Error(`Self table row modal validation failed: ${JSON.stringify(selfTableModalCheck)}`);
    }

    // Close modal
    await page.evaluate(() => {
      const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Cancel'));
      if (cancel) cancel.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 3. Test Clicking Edit on Other User in Directory Table
    console.log('Testing Edit button on Directory Table (sysadmin_sadri)...');
    await page.evaluate(() => {
      const actBtns = Array.from(document.querySelectorAll('table tbody tr button[title="Actions"]'));
      if (actBtns.length > 1) {
        actBtns[1].click();
      }
    });
    await new Promise(r => setTimeout(r, 600));

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('div.absolute button'));
      const editBtn = btns.find(b => b.textContent.trim() === 'Edit' || b.textContent.includes('Edit'));
      if (editBtn) editBtn.click();
    });
    await new Promise(r => setTimeout(r, 800));

    // Check modal content (Admin Mode)
    const adminModalCheck = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return { open: false };
      const text = modal.innerText.toUpperCase();
      const pwdInputs = modal.querySelectorAll('input[type="password"]');
      const hasCurrentPwdInput = Array.from(pwdInputs).some(i => i.placeholder.toLowerCase().includes('current'));
      const hasRoleMatrix = text.includes('OPERATOR PERMISSIONS MATRIX');
      return {
        open: true,
        pwdInputCount: pwdInputs.length,
        hasCurrentPwdInput,
        hasRoleMatrix
      };
    });
    console.log('Admin modal check:', adminModalCheck);
    if (!adminModalCheck.open || adminModalCheck.hasCurrentPwdInput || !adminModalCheck.hasRoleMatrix || adminModalCheck.pwdInputCount !== 2) {
      throw new Error(`Admin modal validation failed: ${JSON.stringify(adminModalCheck)}`);
    }

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0140_edit_admin_modal.png', fullPage: true });
    console.log('Saved screenshots/v0140_edit_admin_modal.png');

    // Close modal
    await page.evaluate(() => {
      const cancel = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Cancel'));
      if (cancel) cancel.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // 4. Test 2FA Button (Verify label is clean "Enable 2FA" without "Now")
    console.log('Verifying 2FA Button label and opening modal...');
    const btn2faText = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find(b => b.textContent.includes('2FA'));
      return btn ? btn.textContent.trim() : null;
    });
    console.log('2FA button text found:', btn2faText);
    if (btn2faText !== 'Enable 2FA' && btn2faText !== 'Disable 2FA') {
      throw new Error(`Unexpected 2FA button text: "${btn2faText}"`);
    }

    if (btn2faText === 'Enable 2FA') {
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const btn = btns.find(b => b.textContent.trim() === 'Enable 2FA');
        if (btn) btn.click();
      });
      await new Promise(r => setTimeout(r, 1200));

      await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0140_setup_2fa_modal.png', fullPage: true });
      console.log('Saved screenshots/v0140_setup_2fa_modal.png');
    }

    console.log('ALL VERIFICATION CHECKS PASSED 100%!');
  } catch (err) {
    console.error('Test failed:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
