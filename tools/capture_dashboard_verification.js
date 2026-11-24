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
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });

  try {
    // ----------------------------------------------------
    // TEST 1: MASTER ADMIN VIEW
    // ----------------------------------------------------
    console.log('=== [1] Testing Master Admin Dashboard ===');
    const adminToken = generateToken('master-admin');
    const pageAdmin = await browser.newPage();
    await pageAdmin.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageAdmin.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, adminToken);
    await pageAdmin.reload({ waitUntil: 'networkidle2' });
    await pageAdmin.waitForSelector('#kpi-card-total', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1500));

    // Verify 10 servers pagination: with 10 servers, .table-pagination-bar MUST NOT be visible!
    const pagBarAdmin = await pageAdmin.$('.table-pagination-bar');
    console.log('Admin pagination bar on 10 nodes (should be null):', pagBarAdmin === null);
    if (pagBarAdmin !== null) {
      throw new Error('Pagination bar is visible for <= 10 rows! Rule violation.');
    }

    const adminDashPath = path.join(ARTIFACT_DIR, 'v0150_dashboard_master_admin.png');
    await pageAdmin.screenshot({ path: adminDashPath });
    console.log(`Saved: ${adminDashPath}`);

    // Open SevDetailModal
    await pageAdmin.evaluate(() => {
      const tile = document.querySelector('#kpi-card-prob .grid > div');
      if (tile) tile.click();
    });
    await new Promise(r => setTimeout(r, 800));
    const adminSevModalPath = path.join(ARTIFACT_DIR, 'v0150_sev_modal_admin.png');
    await pageAdmin.screenshot({ path: adminSevModalPath });
    console.log(`Saved: ${adminSevModalPath}`);
    await pageAdmin.keyboard.press('Escape');
    await new Promise(r => setTimeout(r, 500));

    // Open ProblemDetailModal
    const incidentRow = await pageAdmin.$('#dash-problems-card tbody tr');
    if (incidentRow) {
      await incidentRow.click();
      await new Promise(r => setTimeout(r, 800));
      
      // Verify admin sees Ignore button
      const hasIgnoreBtn = await pageAdmin.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        return btns.some(b => b.textContent.includes('Ignore') || b.textContent.includes('Abaikan'));
      });
      console.log('Admin has Ignore button in modal:', hasIgnoreBtn);
      if (!hasIgnoreBtn) {
        throw new Error('Admin should have Ignore button in ProblemDetailModal!');
      }

      const adminProbModalPath = path.join(ARTIFACT_DIR, 'v0150_problem_detail_admin.png');
      await pageAdmin.screenshot({ path: adminProbModalPath });
      console.log(`Saved: ${adminProbModalPath}`);
      await pageAdmin.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, 500));
    }
    await pageAdmin.close();

    // ----------------------------------------------------
    // TEST 2: VIEWER (GUEST) READ-ONLY VIEW
    // ----------------------------------------------------
    console.log('\n=== [2] Testing Viewer (guest) Dashboard ===');
    const guestToken = generateToken('guest');
    const pageGuest = await browser.newPage();
    await pageGuest.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await pageGuest.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, guestToken);
    await pageGuest.reload({ waitUntil: 'networkidle2' });
    await pageGuest.waitForSelector('#kpi-card-total', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1500));

    const guestDashPath = path.join(ARTIFACT_DIR, 'v0150_dashboard_viewer_readonly.png');
    await pageGuest.screenshot({ path: guestDashPath });
    console.log(`Saved: ${guestDashPath}`);

    // Open ProblemDetailModal as viewer
    const guestIncRow = await pageGuest.$('#dash-problems-card tbody tr');
    if (guestIncRow) {
      await guestIncRow.click();
      await new Promise(r => setTimeout(r, 800));

      // VERIFY: Viewer MUST NOT see Ignore button or Terminate SSH button!
      const viewerHasIgnoreBtn = await pageGuest.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        return btns.some(b => b.textContent.includes('Ignore') || b.textContent.includes('Abaikan'));
      });
      console.log('Viewer has Ignore button (MUST BE FALSE):', viewerHasIgnoreBtn);
      if (viewerHasIgnoreBtn) {
        throw new Error('Viewer can see Ignore button! RBAC leak.');
      }

      const viewerHasTermBtn = await pageGuest.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        return btns.some(b => b.textContent.includes('Terminate') || b.textContent.includes('Putus'));
      });
      console.log('Viewer has Terminate button (MUST BE FALSE):', viewerHasTermBtn);
      if (viewerHasTermBtn) {
        throw new Error('Viewer can see Terminate SSH button! RBAC leak.');
      }

      const guestProbModalPath = path.join(ARTIFACT_DIR, 'v0150_problem_detail_viewer_no_actions.png');
      await pageGuest.screenshot({ path: guestProbModalPath });
      console.log(`Saved: ${guestProbModalPath}`);
      await pageGuest.keyboard.press('Escape');
      await new Promise(r => setTimeout(r, 500));
    }

    // Open SevDetailModal as viewer
    await pageGuest.evaluate(() => {
      const tile = document.querySelector('#kpi-card-prob .grid > div');
      if (tile) tile.click();
    });
    await new Promise(r => setTimeout(r, 800));

    // VERIFY: In SevDetailModal, row action buttons for Ignore / Unignore MUST NOT be present for viewer!
    const viewerHasModalIgnoreBtns = await pageGuest.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('table tbody button'));
      return btns.some(b => (b.title && (b.title.includes('Ignore') || b.title.includes('Unignore') || b.title.includes('Abaikan'))));
    });
    console.log('Viewer has Ignore/Unignore table buttons (MUST BE FALSE):', viewerHasModalIgnoreBtns);
    if (viewerHasModalIgnoreBtns) {
      throw new Error('Viewer can see table action buttons in SevDetailModal! RBAC leak.');
    }

    const guestSevModalPath = path.join(ARTIFACT_DIR, 'v0150_sev_modal_viewer_no_actions.png');
    await pageGuest.screenshot({ path: guestSevModalPath });
    console.log(`Saved: ${guestSevModalPath}`);

    await pageGuest.close();

    console.log('\n=== ALL BROWSER RBAC & UI/UX CHECKS PASSED WITH FLYING COLORS! ===');
  } catch (err) {
    console.error('Test error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();
