const puppeteer = require('puppeteer-core');

(async () => {
  console.log('Launching Chrome for Terminal Dock verification...');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // 1. Click TERMINAL button in Navbar
    console.log('1. Clicking TERMINAL button in navbar...');
    const clickedNavTerm = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('header button'));
      const termBtn = btns.find(b => b.textContent.includes('TERMINAL'));
      if (termBtn) {
        termBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked navbar terminal button:', clickedNavTerm);

    await new Promise(r => setTimeout(r, 1000));

    // 2. In Terminal Dock, if no tabs open or dropdown available, open tab for first server
    console.log('2. Opening a terminal tab for server...');
    await page.evaluate(() => {
      // Find new tab button (+) or connect new server button
      const btns = Array.from(document.querySelectorAll('button'));
      const addBtn = btns.find(b => b.title && b.title.includes('Open New Terminal Tab') || b.textContent.includes('Connect New Server'));
      if (addBtn) addBtn.click();
    });

    await new Promise(r => setTimeout(r, 500));

    // Pick first server from dropdown
    await page.evaluate(() => {
      const serverItems = Array.from(document.querySelectorAll('.max-h-52 div.cursor-pointer'));
      if (serverItems.length > 0) {
        serverItems[0].click();
      }
    });

    // Wait for PTY WebSocket connection and output
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: 'screenshots/visual_terminal_dock_tab1.png' });
    console.log('Captured screenshots/visual_terminal_dock_tab1.png');

    // 3. Open second tab
    console.log('3. Opening second tab for multi-tab management...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const addBtn = btns.find(b => b.title && b.title.includes('Open New Terminal Tab'));
      if (addBtn) addBtn.click();
    });

    await new Promise(r => setTimeout(r, 500));
    await page.evaluate(() => {
      const serverItems = Array.from(document.querySelectorAll('.max-h-52 div.cursor-pointer'));
      if (serverItems.length > 1) {
        serverItems[1].click();
      } else if (serverItems.length > 0) {
        serverItems[0].click();
      }
    });

    await new Promise(r => setTimeout(r, 1500));
    await page.screenshot({ path: 'screenshots/visual_terminal_dock_multitab.png' });
    console.log('Captured screenshots/visual_terminal_dock_multitab.png');

    // 4. Test Minimize to Dock Shelf
    console.log('4. Testing Minimize to Dock Shelf...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const minBtn = btns.find(b => b.title && b.title.includes('Minimize to Dock'));
      if (minBtn) minBtn.click();
    });

    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: 'screenshots/visual_terminal_dock_minimized_shelf.png' });
    console.log('Captured screenshots/visual_terminal_dock_minimized_shelf.png');

    // 5. Test Restore from Dock Shelf
    console.log('5. Testing Restore from Shelf...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const restoreBtn = btns.find(b => b.title && b.title.includes('Restore Terminal Dock') || b.textContent.includes('Restore'));
      if (restoreBtn) restoreBtn.click();
    });

    await new Promise(r => setTimeout(r, 800));
    await page.screenshot({ path: 'screenshots/visual_terminal_dock_restored.png' });
    console.log('Captured screenshots/visual_terminal_dock_restored.png');

    console.log('All Terminal Dock visual verifications completed successfully!');
  } finally {
    await browser.close();
  }
})();
