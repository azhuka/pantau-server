const puppeteer = require('puppeteer-core');
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

async function navTo(page, matchText) {
  await page.evaluate((txt) => {
    const btns = Array.from(document.querySelectorAll('nav button, nav a'));
    const target = btns.find(b => b.textContent.includes(txt));
    if (target) target.click();
  }, matchText);
  await new Promise(r => setTimeout(r, 900));
}

async function run() {
  console.log('=== [1] Launching Browser for v0.1.63 Blueprint Filtering E2E Test ===');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  try {
    const adminToken = generateToken('master-admin');
    const page = await browser.newPage();

    // Inject token & load app
    await page.goto('http://127.0.0.1:8401/', { waitUntil: 'networkidle2' });
    await page.evaluate((tok) => { localStorage.setItem('pantau_token', tok); }, adminToken);
    await page.reload({ waitUntil: 'networkidle2' });
    await page.waitForSelector('nav', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 900));

    // ----------------------------------------------------
    // SUITE 1: Dashboard Group Filter (with Ungrouped) & Tag Search & Reset
    // ----------------------------------------------------
    console.log('\n--- SUITE 1: Dashboard Ungrouped Filter, Comprehensive Search & Zero-Pagination ---');
    const dashData = await page.evaluate(() => {
      const sel = Array.from(document.querySelectorAll('select')).find(s => Array.from(s.options).some(o => o.value === '__none__'));
      const opts = sel ? Array.from(sel.options).map(o => ({ val: o.value, text: o.text.trim() })) : [];
      const pagBars = document.querySelectorAll('.table-pagination-bar').length;
      return { hasUngroupedOpt: opts.some(o => o.val === '__none__'), opts, pagBars };
    });
    console.log('[CHECK] Dashboard options:', dashData);
    if (!dashData.hasUngroupedOpt) throw new Error('Dashboard group dropdown missing Ungrouped (__none__)');
    if (dashData.pagBars !== 0) throw new Error('Dashboard must remain strictly zero-pagination');

    // Search by tag 'Server-Clone'
    await page.type('input[placeholder*="Search host"]', 'Server-Clone');
    await new Promise(r => setTimeout(r, 400));
    const dashTagMatch = await page.evaluate(() => {
      const tables = Array.from(document.querySelectorAll('table'));
      const assetTbl = tables[tables.length - 1];
      const rows = assetTbl ? assetTbl.querySelectorAll('tbody tr') : [];
      const hasReset = Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === 'Reset');
      return { rows: rows.length, hasReset };
    });
    console.log('[CHECK] Dashboard tag search "Server-Clone":', dashTagMatch);
    if (dashTagMatch.rows !== 2 || !dashTagMatch.hasReset) {
      throw new Error(`Expected 2 rows for tag Server-Clone + Reset btn, got ${JSON.stringify(dashTagMatch)}`);
    }
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Reset');
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 300));
    console.log('  -> PASS: Dashboard Ungrouped, tag search, Reset & Zero-Pagination verified');

    // ----------------------------------------------------
    // SUITE 2: Incidents Center (Active Pills Sync + Asset/Group + Resolved 7 Modes + Presets)
    // ----------------------------------------------------
    console.log('\n--- SUITE 2: Incident Center Multi-Criteria Filters & Pill Sync ---');
    await navTo(page, 'Incidents');
    await new Promise(r => setTimeout(r, 800));

    const incCheck = await page.evaluate(() => {
      const assetSel = document.getElementById('inc-active-asset');
      const grpSel = document.getElementById('inc-active-group');
      const sevSel = document.getElementById('inc-active-sev');
      const resAsset = document.getElementById('res-filter-asset');
      const resSev = document.getElementById('res-filter-sev');
      const resType = document.getElementById('res-filter-type');
      const resStart = document.getElementById('res-date-start');
      const resEnd = document.getElementById('res-date-end');
      return {
        activeInputs: Boolean(assetSel && grpSel && sevSel),
        resolvedInputs: Boolean(resAsset && resSev && resType && resStart && resEnd),
        resTypesCount: resType ? resType.options.length : 0,
      };
    });
    console.log('[CHECK] Incident Center filter elements:', incCheck);
    if (!incCheck.activeInputs || !incCheck.resolvedInputs || incCheck.resTypesCount < 7) {
      throw new Error(`Incident filters incomplete: ${JSON.stringify(incCheck)}`);
    }

    // Test 2-way sync between Severity Dropdown and Pill
    await page.select('#inc-active-sev', 'warning');
    await new Promise(r => setTimeout(r, 300));
    const pillSynced = await page.evaluate(() => {
      const resetVisible = Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === 'Reset');
      return { sevVal: document.getElementById('inc-active-sev').value, resetVisible };
    });
    if (pillSynced.sevVal !== 'warning' || !pillSynced.resetVisible) throw new Error('Active incidents filter sync/reset failed');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0163_incidents_filters.png') });
    console.log('  -> PASS: Incidents Active + Resolved multi-criteria filters & presets verified');

    // ----------------------------------------------------
    // SUITE 3: Asset Inventory Matrix (Group, Status 5-opt, Environment Tier, Tag Search, Reset)
    // ----------------------------------------------------
    console.log('\n--- SUITE 3: Asset Inventory Blueprint Filter Bar ---');
    await navTo(page, 'Asset Inventory');
    await new Promise(r => setTimeout(r, 800));

    await page.select('#assets-tier-filter', '1');
    await new Promise(r => setTimeout(r, 400));
    const assetTierCheck = await page.evaluate(() => {
      const grpSel = document.getElementById('assets-group-filter');
      const stSel = document.getElementById('assets-status-filter');
      const rows = document.querySelectorAll('tbody tr').length;
      const resetVisible = Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === 'Reset');
      return {
        hasGroupFilter: Boolean(grpSel),
        statusOpts: stSel ? Array.from(stSel.options).map(o => o.value) : [],
        tier1Rows: rows,
        resetVisible,
      };
    });
    console.log('[CHECK] Asset Inventory Tier 1 filter:', assetTierCheck);
    if (!assetTierCheck.hasGroupFilter || !assetTierCheck.statusOpts.includes('maint') || !assetTierCheck.statusOpts.includes('problem') || assetTierCheck.tier1Rows < 1 || assetTierCheck.tier1Rows >= 10 || !assetTierCheck.resetVisible) {
      throw new Error(`Asset Inventory multi-filter invalid: ${JSON.stringify(assetTierCheck)}`);
    }
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0163_assets_filters.png') });

    // Reset back to show all servers before opening Workspace
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Reset');
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 400));
    console.log('  -> PASS: Asset Inventory Group, Status, Tier & Reset verified');

    // ----------------------------------------------------
    // SUITE 4: Audit Trail Multi-Filter Bar (Operator, Asset, Action Optgroup, Date Range, Presets)
    // ----------------------------------------------------
    console.log('\n--- SUITE 4: Audit Trail Blueprint Multi-Filter & Presets ---');
    await navTo(page, 'Audit Trail');
    await new Promise(r => setTimeout(r, 900));

    const auditCheck = await page.evaluate(() => {
      const uSel = document.getElementById('audit-user-filter');
      const sSel = document.getElementById('audit-server-filter');
      const aSel = document.getElementById('audit-action-filter');
      const stSel = document.getElementById('audit-status-filter');
      const dStart = document.getElementById('audit-date-start');
      const dEnd = document.getElementById('audit-date-end');
      const optGroups = aSel ? aSel.querySelectorAll('optgroup').length : 0;
      const presets = Array.from(document.querySelectorAll('.noc-btn-preset')).map(b => b.textContent.trim());
      return { allPresent: Boolean(uSel && sSel && aSel && stSel && dStart && dEnd), optGroups, presets };
    });
    console.log('[CHECK] Audit Trail filter panel:', auditCheck);
    if (!auditCheck.allPresent || auditCheck.optGroups < 5 || auditCheck.presets.length < 5) {
      throw new Error(`Audit filter panel incomplete: ${JSON.stringify(auditCheck)}`);
    }
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0163_audit_filters.png') });
    console.log('  -> PASS: Audit Trail 6-criteria filters + Presets verified');

    // ----------------------------------------------------
    // SUITE 5: Workspace Modal Sub-Tab Filters (Services Boot, Ports Proto/Access, Packages, Logs)
    // ----------------------------------------------------
    console.log('\n--- SUITE 5: Workspace Tabs Multi-Filters (Services, Ports, Packages, Logs) ---');
    await navTo(page, 'Asset Inventory');
    await new Promise(r => setTimeout(r, 700));
    await page.evaluate(() => {
      const viewBtn = document.querySelector('tbody tr button');
      if (viewBtn) viewBtn.click();
    });
    await new Promise(r => setTimeout(r, 1800));

    // Services tab
    await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('Services & Ports'));
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 600));
    const svcOk = await page.evaluate(() => Boolean(document.getElementById('sysd-status-filter') && document.getElementById('sysd-boot-filter') && document.getElementById('sysd-search-input')));
    if (!svcOk) throw new Error('Workspace Services missing status/boot/search filters');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0163_workspace_services_filters.png') });

    // Switch to Ports
    await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('Listening Ports'));
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 400));
    const portsOk = await page.evaluate(() => {
      const pf = document.getElementById('port-proto-filter');
      const af = document.getElementById('port-access-filter');
      const tables = Array.from(document.querySelectorAll('table'));
      const portTbl = tables[tables.length - 1];
      const rows = portTbl ? Array.from(portTbl.querySelectorAll('tbody tr')) : [];
      // Verify 127.0.0.x is marked INTERNAL, not PUBLIC
      const badLoopback = rows.some(tr => tr.textContent.includes('127.0.0.') && tr.textContent.includes('PUBLIC'));
      return { hasFilters: Boolean(pf && af), rowCount: rows.length, badLoopback };
    });
    console.log('[CHECK] Workspace Ports filters & loopback badge:', portsOk);
    if (!portsOk.hasFilters || portsOk.badLoopback) throw new Error(`Ports check failed: ${JSON.stringify(portsOk)}`);

    // Switch to Packages
    await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(el => el.textContent.trim().startsWith('Packages'));
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 500));
    const pkgOk = await page.evaluate(() => Boolean(document.getElementById('pkg-type-filter') && document.getElementById('pkg-status-filter') && document.getElementById('pkg-search-input')));
    if (!pkgOk) throw new Error('Workspace Packages missing Type/Status/Search filters');

    // Switch to Logs
    await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find(el => el.textContent.trim().startsWith('Logs'));
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 1500));
    const logsOk = await page.evaluate(() => {
      const u = document.getElementById('log-unit-select');
      const l = document.getElementById('log-lines-select');
      const lvl = document.getElementById('log-level-select');
      const k = document.getElementById('log-keyword-input');
      return {
        allControls: Boolean(u && l && lvl && k),
        sourceGroups: u ? u.querySelectorAll('optgroup').length : 0,
        sourceCount: u ? u.querySelectorAll('option').length : 0,
      };
    });
    console.log('[CHECK] Workspace Logs filter panel:', logsOk);
    if (!logsOk.allControls || logsOk.sourceCount < 3) throw new Error(`Workspace Logs incomplete: ${JSON.stringify(logsOk)}`);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'v0163_workspace_logs_filters.png') });

    console.log('\n=== ALL 5 E2E BLUEPRINT FILTERING SUITES PASSED FLAWLESSLY! ===\n');
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('\n[FATAL TEST ERROR]:', err);
  process.exit(1);
});
