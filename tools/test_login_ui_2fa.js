const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');

(async () => {
  console.log('Setting up temporary 2FA test user in database...');
  const initOutput = execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys, json
sys.path.insert(0, '/home/bos/pantau-server/server')
from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.user import User
import security_auth
from core.security import get_password_hash

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
db = Session()

u = db.query(User).filter(User.username == 'puppeteer_2fa_user').first()
if not u:
    u = User(username='puppeteer_2fa_user', password_hash=get_password_hash('SecretPass123!'), role='operator', is_active=1)
    db.add(u)
    db.commit()
    db.refresh(u)

secret = security_auth.generate_totp_secret()
plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
u.totp_secret = secret
u.totp_enabled = 1
u.recovery_codes = json.dumps(hashed_codes)
db.commit()
print(json.dumps({'secret': secret, 'totp': security_auth.compute_totp(secret)}))
db.close()
"`).toString().trim();

  const { secret, totp } = JSON.parse(initOutput);
  console.log('Test user ready. TOTP Secret:', secret, 'Current TOTP:', totp);

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1200,800'],
    defaultViewport: { width: 1200, height: 800 }
  });

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));

    // 1. Visit root with empty localStorage
    await page.goto('http://localhost:8401/', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.clear();
    });
    await page.goto('http://localhost:8401/', { waitUntil: 'domcontentloaded' });
    await new Promise(r => setTimeout(r, 1000));

    // 2. Verify Login Modal is visible (no auto-login hack!)
    const isModalVisible = await page.evaluate(() => {
      const modal = document.querySelector('form');
      return Boolean(modal && document.querySelector('input[type="password"]'));
    });
    console.log('Login modal is visible:', isModalVisible);
    if (!isModalVisible) throw new Error('Login modal was not displayed!');

    // Screenshot Step 1
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0141_login_step1_credentials.png' });
    console.log('Saved screenshots/v0141_login_step1_credentials.png');

    // 3. Fill Credentials
    console.log('Filling username & password...');
    await page.type('input[autocomplete="username"]', 'puppeteer_2fa_user');
    await page.type('input[autocomplete="current-password"]', 'SecretPass123!');
    await page.click('button[type="submit"]');
    await new Promise(r => setTimeout(r, 1200));

    // 4. Verify Step 2 (2FA screen appeared)
    const is2faScreen = await page.evaluate(() => {
      const text = document.body.innerText;
      const has2faInput = Boolean(document.querySelector('input[autocomplete="one-time-code"]'));
      return has2faInput && (text.includes('Two-Factor') || text.includes('2FA'));
    });
    console.log('Transitioned to 2FA Step 2:', is2faScreen);
    if (!is2faScreen) throw new Error('UI failed to transition to 2FA challenge!');

    // Screenshot Step 2
    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0141_login_step2_2fa_challenge.png' });
    console.log('Saved screenshots/v0141_login_step2_2fa_challenge.png');

    // 5. Compute fresh TOTP code
    const freshTotp = execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys; sys.path.insert(0, '/home/bos/pantau-server/server')
import security_auth
print(security_auth.compute_totp('${secret}'))
"`).toString().trim();

    console.log('Submitting valid TOTP code:', freshTotp);
    await page.type('input[autocomplete="one-time-code"]', freshTotp);
    await page.click('button[type="submit"]');
    await new Promise(r => setTimeout(r, 1500));

    // 6. Verify Dashboard Loaded
    const loggedIn = await page.evaluate(() => {
      const token = localStorage.getItem('pantau_token');
      const hasNav = Boolean(document.querySelector('nav'));
      return Boolean(token && hasNav);
    });
    console.log('Successfully authenticated into Dashboard:', loggedIn);
    if (!loggedIn) throw new Error('Dashboard was not reached after 2FA verification!');

    await page.screenshot({ path: '/home/bos/pantau-server/screenshots/v0141_login_success_dashboard.png' });
    console.log('Saved screenshots/v0141_login_success_dashboard.png');

    console.log('ALL LOGIN 2FA UI FLOW TESTS PASSED 100%!');
  } finally {
    // Cleanup test user
    execSync(`/home/bos/pantau-server/env/bin/python3 -c "
import sys
sys.path.insert(0, '/home/bos/pantau-server/server')
from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.user import User

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
db = Session()
u = db.query(User).filter(User.username == 'puppeteer_2fa_user').first()
if u:
    db.delete(u)
    db.commit()
db.close()
"`);
    await browser.close();
  }
})();
