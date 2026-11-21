const puppeteer = require('puppeteer-core');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });
  const page = await browser.newPage();
  await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
  await page.waitForSelector('#dash-problems-card', { timeout: 5000 });
  
  // 0. Capture Clean Passive Dashboard
  await page.screenshot({ path: 'screenshots/visual_0_dashboard.png' });
  console.log('0. Captured visual_0_dashboard.png');

  // 1. Open Workspace modal by clicking incident row or fleet row
  await page.waitForSelector('#dash-problems-card tbody tr', { timeout: 5000 });
  const row = await page.$('#dash-problems-card tbody tr');
  if (row) {
    await row.click();
  } else {
    const anyRow = await page.$('tbody tr');
    if (anyRow) await anyRow.click();
  }
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: 'screenshots/visual_1_workspace_header.png' });
  console.log('1. Captured visual_1_workspace_header.png');

  // 2. Open Fleet Switcher dropdown
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const swBtn = btns.find(b => b.title && b.title.toLowerCase().includes('search') || b.textContent.includes('▾'));
    if (swBtn) swBtn.click();
  });
  await new Promise(r => setTimeout(r, 500));
  await page.screenshot({ path: 'screenshots/visual_2_fleet_switcher.png' });
  console.log('2. Captured visual_2_fleet_switcher.png');

  // Close dropdown by clicking title
  await page.evaluate(() => {
    const t = document.querySelector('.bg-\\[\\#060a15\\]');
    if (t) t.click();
  });
  await new Promise(r => setTimeout(r, 400));

  // 3. Open Terminal Floating Window
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const tBtn = btns.find(b => b.textContent.trim().includes('Terminal'));
    if (tBtn) tBtn.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: 'screenshots/visual_3_floating_terminal.png' });
  console.log('3. Captured visual_3_floating_terminal.png');

  // Close terminal modal if open
  await page.evaluate(() => {
    const termModal = document.querySelector('.z-\\[60\\]');
    if (termModal) {
      const closeBtn = termModal.querySelector('button[title*="Close"]');
      if (closeBtn) closeBtn.click();
    }
  });
  await new Promise(r => setTimeout(r, 400));

  // 4. Open File Manager Floating Window
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const fBtn = btns.find(b => b.textContent.trim().includes('File Manager'));
    if (fBtn) fBtn.click();
  });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: 'screenshots/visual_4_floating_filemanager.png' });
  console.log('4. Captured visual_4_floating_filemanager.png');

  // Close all modals and navigate to Fleet Inventory tab
  await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
  await page.evaluate(() => {
    const navBtns = Array.from(document.querySelectorAll('nav button'));
    const fleetNav = navBtns.find(b => b.textContent.includes('Fleet Inventory'));
    if (fleetNav) fleetNav.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: 'screenshots/visual_5_fleet_table.png' });
  console.log('5. Captured visual_5_fleet_table.png');

  await browser.close();
  console.log('Finished visual test suite successfully!');
})();
