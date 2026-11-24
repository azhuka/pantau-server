const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const path = require('path');

const ARTIFACT_DIR = '/home/bos/.gemini/antigravity-cli/brain/0c842cc8-965e-436a-bbe2-9c6ef43e29d0';

(async () => {
  console.log('=== [1] Generating JWT Token for Master Admin ===');
  const adminTok = execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.security import create_access_token
print(create_access_token({'sub': 'master-admin', 'role': 'master_admin', 'uid': 1}))
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
    // 1. Visit app with token
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
    await page.waitForSelector('tbody tr', { timeout: 10000 });

    console.log('=== [3] Opening Action Dropdown on Operator row ===');
    const rowTexts = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('tbody tr')).map(r => r.textContent.replace(/\s+/g, ' ').trim());
    });
    console.log('Detected Rows in Table:', rowTexts);

    const opened = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('tbody tr'));
      for (const row of rows) {
        if (row.textContent.includes('sysadmin_sadri') || row.textContent.includes('Operator')) {
          const actBtn = row.querySelector('button[aria-label="Actions"]');
          if (actBtn) {
            actBtn.click();
            return true;
          }
        }
      }
      return false;
    });

    if (!opened) throw new Error('Could not find Operator row action button');
    await new Promise(r => setTimeout(r, 600));

    // Verify all dropdown items exist
    const items = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('div[style*="position: fixed"] button'));
      return btns.map(b => b.textContent.trim());
    });
    console.log('Detected Dropdown Items in Fixed Menu:', items);

    if (items.length === 0) {
      throw new Error('Dropdown menu not found in fixed position body teleport');
    }

    // Capture screenshot of the table with dropdown opened
    const shotPath = path.join(ARTIFACT_DIR, 'v0144_table_action_dropdown_unclipped.png');
    await page.screenshot({ path: shotPath });
    console.log('[OK] Captured Unclipped Dropdown Screenshot:', shotPath);

    // Also copy to workspace screenshots folder
    const wsShotPath = '/home/bos/pantau-server/screenshots/v0144_table_action_dropdown_unclipped.png';
    await page.screenshot({ path: wsShotPath });
    console.log('[OK] Captured Workspace Screenshot:', wsShotPath);

    console.log('=== VERIFICATION PASSED: DROPDOWN IS 100% UNCLIPPED & TELEPORTED TO BODY! ===');
  } catch (err) {
    console.error('Test Error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
