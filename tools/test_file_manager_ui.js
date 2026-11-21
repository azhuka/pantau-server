const puppeteer = require('puppeteer-core');

(async () => {
  console.log('Launching Chrome for File Manager UI verification...');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 }
  });

  try {
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

    console.log('1. Navigating to Pantau Server at http://localhost:8401/ ...');
    await page.goto('http://localhost:8401/', { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1000));

    // Open first server workspace by clicking on the row in Fleet Table or Dashboard
    console.log('2. Clicking first server in table to open Workspace Modal...');
    const openedWorkspace = await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      if (rows.length > 0) {
        rows[0].click();
        return true;
      }
      return false;
    });
    console.log('Opened Workspace modal:', openedWorkspace);
    await new Promise(r => setTimeout(r, 1000));

    // Look for the File Manager button in Workspace modal header
    console.log('3. Clicking File Manager button in Workspace toolbar...');
    const clickedFm = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const fmBtn = btns.find(b => b.title && b.title.includes('File Manager') || b.textContent.includes('File Manager'));
      if (fmBtn) {
        fmBtn.click();
        return true;
      }
      return false;
    });
    console.log('Clicked File Manager button:', clickedFm);
    await new Promise(r => setTimeout(r, 1500));

    // Verify File Manager elements
    console.log('4. Verifying File Manager modal DOM elements...');
    const fmInfo = await page.evaluate(() => {
      const header = document.querySelector('span.text-cyan-300');
      const bookmarks = Array.from(document.querySelectorAll('button')).filter(b => 
        ['~ Home', '/ Root', '/var/log', '/etc', '/opt', '/var/www'].some(text => b.textContent.includes(text))
      );
      const actionBtns = Array.from(document.querySelectorAll('button')).filter(b =>
        ['New File', 'New Folder'].some(text => b.textContent.includes(text))
      );
      const tableRows = document.querySelectorAll('tbody tr');
      return {
        hasHeader: !!header,
        headerText: header ? header.textContent.trim() : null,
        bookmarksCount: bookmarks.length,
        actionBtnsCount: actionBtns.length,
        itemsInTable: tableRows.length
      };
    });

    console.log('File Manager Verification Result:', JSON.stringify(fmInfo, null, 2));

    if (fmInfo.bookmarksCount >= 4 && fmInfo.actionBtnsCount >= 2) {
      console.log('\n========================================================');
      console.log('  REMOTE FILE MANAGER UI VERIFICATION PASSED');
      console.log('========================================================');
    } else {
      console.warn('File Manager UI elements count lower than expected:', fmInfo);
    }
  } catch (err) {
    console.error('Error during FM UI test:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
