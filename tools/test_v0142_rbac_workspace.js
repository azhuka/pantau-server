const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');

(async () => {
  console.log('=== [1] Generating JWT tokens for master-admin and restricted operator ===');
  const tokens = JSON.parse(execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
import json
from core.security import create_access_token
from core.database import SessionLocal
from models.user import User

db = SessionLocal()
admin = db.query(User).filter(User.role == 'master_admin').first()
admin_tok = create_access_token({'sub': admin.username, 'role': admin.role, 'uid': admin.id})

# Clean up or create restricted operator
db.query(User).filter(User.username == 'test_ui_op').delete()
db.commit()

from core.security import get_password_hash
op = User(
    username='test_ui_op',
    password_hash=get_password_hash('OpPass123!'),
    role='operator',
    is_active=1,
    allowed_server_ids=json.dumps([1]),
    permissions=json.dumps({'can_services': True, 'can_processes': False, 'can_firewall': False, 'can_terminal': False, 'can_server_control': False, 'can_manage_servers': False, 'can_apt': False})
)
db.add(op)
db.commit()
db.refresh(op)

op_tok = create_access_token({'sub': op.username, 'role': op.role, 'uid': op.id})
db.close()

print(json.dumps({'admin_token': admin_tok, 'op_token': op_tok, 'op_id': op.id}))
"`).toString().trim());

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });

  const artifactDir = '/home/bos/.gemini/antigravity-cli/brain/0c842cc8-965e-436a-bbe2-9c6ef43e29d0';

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

    // TEST 1: MASTER ADMIN WORKSPACE (FULL CAPABILITIES)
    console.log('\n--- Testing Master Admin Workspace ---');
    await page.goto('http://localhost:8401/', { waitUntil: 'domcontentloaded' });
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, tokens.admin_token);

    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    // Open workspace by clicking first row in dashboard
    console.log('Opening workspace for Server #1 as Admin...');
    await page.evaluate(() => {
      const row = document.querySelector('tbody tr');
      if (row) row.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    // Check workspace modal is open
    const adminModalOpen = await page.evaluate(() => {
      return !!document.querySelector('.fixed.inset-0');
    });
    console.log('Master Admin Workspace Modal Open:', adminModalOpen);

    // Get visible subTabs in workspace modal
    const adminTabs = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return [];
      const tabs = Array.from(modal.querySelectorAll('button')).filter(b => {
        const text = b.textContent.toLowerCase();
        return text.includes('performance') || text.includes('incidents') || text.includes('services') || 
               text.includes('tasks') || text.includes('firewall') || text.includes('accounts') || 
               text.includes('cron') || text.includes('fim') || text.includes('packages') || text.includes('ssl') || text.includes('logs');
      });
      return tabs.map(t => t.textContent.trim());
    });
    console.log('Master Admin Tabs in Modal:', adminTabs);

    await page.screenshot({ path: `${artifactDir}/v0142_admin_workspace_full.png` });
    console.log('Saved screenshot: v0142_admin_workspace_full.png');

    // TEST 2: RESTRICTED OPERATOR WORKSPACE (SCOPED & FILTERED)
    console.log('\n--- Testing Restricted Operator Workspace (allowed_server_ids=[1], can_services=True only) ---');
    await page.evaluate((tok) => {
      localStorage.setItem('pantau_token', tok);
      localStorage.setItem('pantau_lang', 'en');
    }, tokens.op_token);

    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1200));

    console.log('Opening workspace for Server #1 as Restricted Operator...');
    await page.evaluate(() => {
      const row = document.querySelector('tbody tr');
      if (row) row.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    const opTabs = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return [];
      const tabs = Array.from(modal.querySelectorAll('button')).filter(b => {
        const text = b.textContent.toLowerCase();
        return text.includes('performance') || text.includes('incidents') || text.includes('services') || 
               text.includes('tasks') || text.includes('firewall') || text.includes('accounts') || 
               text.includes('cron') || text.includes('fim') || text.includes('packages') || text.includes('ssl') || text.includes('logs');
      });
      return tabs.map(t => t.textContent.trim());
    });
    console.log('Restricted Operator Visible SubTabs in Modal:', opTabs);

    // Verify that Tasks, Firewall, Accounts, Cron, Packages, SSL are NOT present
    const opTabsJoined = opTabs.join(' ').toLowerCase();
    const hasForbiddenTabs = opTabsJoined.includes('tasks') || opTabsJoined.includes('firewall') || 
                             opTabsJoined.includes('accounts') || opTabsJoined.includes('cron') || 
                             opTabsJoined.includes('packages') || opTabsJoined.includes('ssl');
    console.log('Has Forbidden SubTabs in DOM:', hasForbiddenTabs);
    if (hasForbiddenTabs) {
      throw new Error('Forbidden subTabs found in restricted operator workspace!');
    }

    // Verify toolbar buttons: Terminal, Reboot, Power Off should NOT be present
    const hasTerminalBtn = await page.evaluate(() => {
      const modal = document.querySelector('.fixed.inset-0');
      if (!modal) return false;
      const btns = Array.from(modal.querySelectorAll('button'));
      return btns.some(b => b.textContent.toLowerCase().includes('terminal') || b.title?.toLowerCase().includes('terminal'));
    });
    console.log('Has Terminal Toolbar Button in DOM for Operator:', hasTerminalBtn);
    if (hasTerminalBtn) {
      throw new Error('Terminal toolbar button should be hidden for restricted operator!');
    }

    await page.screenshot({ path: `${artifactDir}/v0142_restricted_operator_workspace.png` });
    console.log('Saved screenshot: v0142_restricted_operator_workspace.png');

    // TEST 3: RESTRICTED OPERATOR INVENTORY TABLE (02 // Assets)
    console.log('\n--- Testing Restricted Operator Inventory Table ---');
    // Close modal first
    await page.evaluate(() => {
      const closeBtn = document.querySelector('button[title*="Close"], button[title*="Tutup"]');
      if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 600));

    // Navigate to Assets tab
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('nav button'));
      const btn = btns.find(b => b.textContent.includes('Assets') || b.textContent.includes('02'));
      if (btn) btn.click();
    });
    await new Promise(r => setTimeout(r, 1200));

    // Count rows in table
    const visibleServerRows = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      return rows.length;
    });
    console.log('Visible Server Rows for Restricted Operator:', visibleServerRows);
    if (visibleServerRows !== 1) {
      throw new Error(`Expected exactly 1 server row for restricted operator, found ${visibleServerRows}`);
    }

    // Open More Actions dropdown (⋮) on that row
    await page.evaluate(() => {
      const moreBtn = document.querySelector('button[title*="More Actions"], button[title*="Aksi"]');
      if (moreBtn) moreBtn.click();
    });
    await new Promise(r => setTimeout(r, 500));

    // Check dropdown items
    const dropdownItems = await page.evaluate(() => {
      const popover = document.querySelector('.z-\\[9999\\]');
      if (!popover) return [];
      return Array.from(popover.querySelectorAll('button')).map(b => b.textContent.trim());
    });
    console.log('Dropdown Menu Items for Restricted Operator:', dropdownItems);

    const dropdownJoined = dropdownItems.join(' ').toLowerCase();
    const hasForbiddenActions = dropdownJoined.includes('edit host') || dropdownJoined.includes('inject key') || dropdownJoined.includes('delete');
    console.log('Has Forbidden Actions in Dropdown:', hasForbiddenActions);
    if (hasForbiddenActions) {
      throw new Error('Forbidden actions found in restricted operator dropdown menu!');
    }

    await page.screenshot({ path: `${artifactDir}/v0142_restricted_operator_inventory.png` });
    console.log('Saved screenshot: v0142_restricted_operator_inventory.png');

    console.log('\n======================================================');
    console.log('>>> ALL PUPPETEER UI TESTS PASSED 100% WITH PROOF! <<<');
    console.log('======================================================');

  } finally {
    // Cleanup test user
    execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
from core.database import SessionLocal
from models.user import User
db = SessionLocal()
db.query(User).filter(User.username == 'test_ui_op').delete()
db.commit()
db.close()
"`);
    console.log('Cleaned up test_ui_op.');
    await browser.close();
  }
})();
