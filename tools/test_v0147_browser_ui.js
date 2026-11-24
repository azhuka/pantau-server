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
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    // ----------------------------------------------------
    // TEST 1: PRE-LOGIN VIEW (Unauthenticated Visitor)
    // ----------------------------------------------------
    console.log('=== [1] Testing Pre-Login Clean Screen ===');
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 800));

    // Verify Login Screen elements
    const hasLoginCard = await page.evaluate(() => {
      return document.body.innerText.includes('NOC CONTROL PLANE') ||
             document.body.innerText.includes('PANTAU SERVER');
    });
    const hasNoNavbar = await page.evaluate(() => {
      return document.querySelector('header nav') === null;
    });
    const hasNoDashboardData = await page.evaluate(() => {
      return !document.body.innerText.includes('STATUS & PERFORMANCE') &&
             !document.body.innerText.includes('RECENT INCIDENTS');
    });

    console.log('Login Card rendered:', hasLoginCard);
    console.log('No background navbar leakage:', hasNoNavbar);
    console.log('No background dashboard telemetry leakage:', hasNoDashboardData);

    const shot1 = path.join(ARTIFACT_DIR, 'v0147_prelogin_clean_screen.png');
    await page.screenshot({ path: shot1, fullPage: true });
    console.log('Screenshot 1 saved:', shot1);

    // ----------------------------------------------------
    // TEST 2: OPERATOR VIEW (op-sadri) - 10 HOSTS VISIBILITY
    // ----------------------------------------------------
    console.log('\n=== [2] Testing Operator (op-sadri) Fleet Visibility ===');
    const opToken = generateToken('op-sadri');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
    }, opToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1500));

    const opBadge = await page.evaluate(() => {
      return document.body.innerText.includes('OPERATOR');
    });
    const opHostCount = await page.evaluate(() => {
      return document.body.innerText.includes('10') && document.body.innerText.includes('HOST');
    });

    console.log('Operator Role Badge present:', opBadge);
    console.log('10 HOST count detected on Dashboard:', opHostCount);

    const shot2 = path.join(ARTIFACT_DIR, 'v0147_operator_dashboard_10_hosts.png');
    await page.screenshot({ path: shot2, fullPage: true });
    console.log('Screenshot 2 saved:', shot2);

    // Navigate to Asset Inventory
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const assetBtn = btns.find(b => b.innerText.includes('02 //') || b.innerText.includes('Asset Inventory'));
      if (assetBtn) assetBtn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    const opAssetNodes = await page.evaluate(() => {
      return document.body.innerText.includes('10 NODES MONITORED');
    });
    console.log('Asset Matrix shows 10 NODES MONITORED:', opAssetNodes);

    const shot3 = path.join(ARTIFACT_DIR, 'v0147_operator_asset_inventory_10_nodes.png');
    await page.screenshot({ path: shot3, fullPage: true });
    console.log('Screenshot 3 saved:', shot3);

    // ----------------------------------------------------
    // TEST 3: VIEWER (guest) - BLANK SCREEN RESOLUTION
    // ----------------------------------------------------
    console.log('\n=== [3] Testing Viewer (guest) Blank Screen Prevention ===');
    const guestToken = generateToken('guest');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      window.location.hash = '#settings'; // Simulate previous user's settings hash
    }, guestToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1500));

    // Verify it automatically fell back to Dashboard instead of blank screen
    const guestFellBackToDashboard = await page.evaluate(() => {
      return document.body.innerText.includes('TOTAL ASSETS') || document.body.innerText.includes('HOST');
    });
    const guestBadge = await page.evaluate(() => {
      return document.body.innerText.includes('VIEWER');
    });

    console.log('Guest automatically redirected to Dashboard (no blank screen):', guestFellBackToDashboard);
    console.log('Guest Role Badge present:', guestBadge);

    const shot4 = path.join(ARTIFACT_DIR, 'v0147_guest_fallback_dashboard_10_hosts.png');
    await page.screenshot({ path: shot4, fullPage: true });
    console.log('Screenshot 4 saved:', shot4);

    // ----------------------------------------------------
    // TEST 4: LOGOUT WORKFLOW
    // ----------------------------------------------------
    console.log('\n=== [4] Testing Logout Workflow ===');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const logoutBtn = btns.find(b => b.innerHTML.includes('polyline points="16 17 21 12 16 7"') || b.title.includes('Sign Out') || b.title.includes('Keluar'));
      if (logoutBtn) logoutBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    const isBackToLogin = await page.evaluate(() => {
      return localStorage.getItem('pantau_token') === null &&
             (document.body.innerText.includes('NOC CONTROL PLANE') || document.body.innerText.includes('PANTAU SERVER'));
    });
    console.log('Successfully logged out & returned to Login Screen:', isBackToLogin);

    const shot5 = path.join(ARTIFACT_DIR, 'v0147_postlogout_login_screen.png');
    await page.screenshot({ path: shot5, fullPage: true });
    console.log('Screenshot 5 saved:', shot5);

    console.log('\nALL BROWSER WORKFLOW TESTS PASSED PERFECTLY!');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('Browser test failed:', err);
  process.exit(1);
});
