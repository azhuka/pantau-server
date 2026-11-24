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
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  try {
    // ----------------------------------------------------
    // TEST 1: OPERATOR VIEW (op-sadri) - Zero-Knowledge Check
    // ----------------------------------------------------
    console.log('=== [1] Testing Operator View (op-sadri) ===');
    const opToken = generateToken('op-sadri');
    const pageOp = await browser.newPage();
    await pageOp.setViewport({ width: 1440, height: 900 });

    await pageOp.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageOp.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
    }, opToken);
    await pageOp.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // Click Settings in Navbar
    await pageOp.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const settingsBtn = btns.find(b => b.innerText.includes('04 //') || b.innerText.includes('SETTINGS') || b.innerText.includes('Settings'));
      if (settingsBtn) settingsBtn.click();
    });

    await pageOp.waitForFunction(() => document.body.innerText.includes('USER ACCOUNTS DIRECTORY') || document.body.innerText.includes('accounts'), { timeout: 8000 });
    await new Promise(r => setTimeout(r, 800));

    // Verify Master Admin is NOT in table and NOT in KPI strip
    const hasMasterAdminInTable = await pageOp.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      for (const r of rows) {
        if (r.innerText.includes('master-admin')) {
          return true;
        }
      }
      return false;
    });

    const hasMasterControlBtn = await pageOp.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.some(b => b.innerText.includes('Master Control'));
    });

    console.log(`[OPERATOR CHECK] Master Admin in table: ${hasMasterAdminInTable} (expected false)`);
    console.log(`[OPERATOR CHECK] Master Control button: ${hasMasterControlBtn} (expected false)`);

    if (hasMasterAdminInTable || hasMasterControlBtn) {
      throw new Error('Zero-Knowledge leak detected: Operator saw Master Admin or Master Control button!');
    }

    const opScreenshot = path.join(ARTIFACT_DIR, 'v0146_operator_view_zero_knowledge.png');
    await pageOp.screenshot({ path: opScreenshot, fullPage: false });
    console.log(`[SUCCESS] Operator screenshot captured at ${opScreenshot}`);
    await pageOp.close();

    // ----------------------------------------------------
    // TEST 2: MASTER ADMIN VIEW (master-admin) - Full Visibility
    // ----------------------------------------------------
    console.log('=== [2] Testing Master Admin View (master-admin) ===');
    const adminToken = generateToken('master-admin');
    const pageAdmin = await browser.newPage();
    await pageAdmin.setViewport({ width: 1440, height: 900 });

    await pageAdmin.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageAdmin.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
    }, adminToken);
    await pageAdmin.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    await pageAdmin.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const settingsBtn = btns.find(b => b.innerText.includes('04 //') || b.innerText.includes('SETTINGS') || b.innerText.includes('Settings'));
      if (settingsBtn) settingsBtn.click();
    });

    await pageAdmin.waitForFunction(() => document.body.innerText.includes('USER ACCOUNTS DIRECTORY') || document.body.innerText.includes('accounts'), { timeout: 8000 });
    await new Promise(r => setTimeout(r, 800));

    const hasMasterAdminRow = await pageAdmin.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      for (const r of rows) {
        if (r.innerText.includes('master-admin')) {
          return true;
        }
      }
      return false;
    });

    const hasAdminMCBtn = await pageAdmin.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      return btns.some(b => b.innerText.includes('Master Control'));
    });

    console.log(`[MASTER ADMIN CHECK] Master Admin row in table: ${hasMasterAdminRow} (expected true)`);
    console.log(`[MASTER ADMIN CHECK] Master Control button: ${hasAdminMCBtn} (expected true)`);

    if (!hasMasterAdminRow || !hasAdminMCBtn) {
      throw new Error('Master Admin visibility error: Missing master-admin row or Master Control button');
    }

    const adminScreenshot = path.join(ARTIFACT_DIR, 'v0146_master_admin_view_full.png');
    await pageAdmin.screenshot({ path: adminScreenshot, fullPage: false });
    console.log(`[SUCCESS] Master Admin screenshot captured at ${adminScreenshot}`);
    await pageAdmin.close();

    console.log('ALL BROWSER UI VERIFICATIONS PASSED 100%!');
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
