import { test, expect } from '@playwright/test';

test('clicking program row shows code in viewer', async ({ page }) => {
  // Navigate to the app
  await page.goto('http://localhost:5173/');

  // Wait for initial load and API data
  await page.waitForTimeout(2000);

  // Take screenshot of initial state
  await page.screenshot({ path: 'test-results/01-initial.png', fullPage: true });

  // Click on the TASK dropdown button (has specific structure from Sidebar.tsx)
  // The button contains "Select a task..." text
  const taskButton = page.locator('button:has-text("Select a task")').first();
  console.log('Task button visible:', await taskButton.isVisible());

  if (await taskButton.isVisible()) {
    console.log('Clicking task dropdown button...');
    await taskButton.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'test-results/02-task-dropdown-open.png', fullPage: true });

    // The dropdown menu appears as buttons inside a div with z-10
    // Look for any button that's NOT "Select a task..."
    const taskOptions = page.locator('.absolute.z-10 button').all();
    const options = await taskOptions;
    console.log('Found task options:', options.length);

    if (options.length > 0) {
      const firstOption = options[0];
      const optionText = await firstOption.textContent();
      console.log('Clicking first task option:', optionText);
      await firstOption.click();
      await page.waitForTimeout(500);
    }
  }

  await page.screenshot({ path: 'test-results/03-after-task-select.png', fullPage: true });

  // Now click the result dropdown - it should auto-select but let's be sure
  await page.waitForTimeout(500);

  // Check if a result was auto-selected, if not, click to select
  const resultButton = page.locator('button:has-text("Select a result")').first();
  if (await resultButton.isVisible()) {
    console.log('Result not auto-selected, clicking dropdown...');
    await resultButton.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'test-results/04-result-dropdown-open.png', fullPage: true });

    const resultOptions = await page.locator('.absolute.z-10 button').all();
    console.log('Found result options:', resultOptions.length);

    if (resultOptions.length > 0) {
      await resultOptions[0].click();
      await page.waitForTimeout(500);
    }
  }

  // Wait for database to load
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'test-results/05-after-result-select.png', fullPage: true });

  // Now click on "Programs" in the left sidebar
  const programsButton = page.locator('button:has-text("Programs")').first();
  if (await programsButton.isVisible()) {
    console.log('Clicking Programs tab...');
    await programsButton.click();
    await page.waitForTimeout(1000);
  }

  await page.screenshot({ path: 'test-results/06-programs-view.png', fullPage: true });

  // Look for programs table rows
  const programRows = await page.locator('.programs-table tbody tr, table tbody tr').all();
  console.log('Found program rows:', programRows.length);

  if (programRows.length > 0) {
    // Click the first program row
    console.log('Clicking first program row...');
    await programRows[0].click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/07-after-row-click.png', fullPage: true });
  } else {
    console.log('No program rows found - checking page content');
    const bodyHTML = await page.locator('body').innerHTML();
    console.log('Body contains "programs-table":', bodyHTML.includes('programs-table'));
    console.log('Body contains "No Database":', bodyHTML.includes('No Database'));
  }

  // Check the right panel
  await page.screenshot({ path: 'test-results/08-right-panel.png', fullPage: true });

  // Check if code viewer panel has content
  const codePanel = page.locator('.code-viewer-panel').first();
  if (await codePanel.count() > 0) {
    const codePanelHTML = await codePanel.innerHTML();
    console.log('Code panel HTML (first 1000 chars):', codePanelHTML.substring(0, 1000));

    // Check for actual code content
    const codeElement = page.locator('.code-viewer-panel code').first();
    if (await codeElement.count() > 0) {
      const codeText = await codeElement.textContent();
      console.log('Code content (first 500 chars):', codeText?.substring(0, 500));
    } else {
      console.log('No code element found in code-viewer-panel');
    }
  } else {
    console.log('Code viewer panel not found');
  }

  // Test the resizable divider
  const divider = page.locator('[title="Drag to resize, double-click to reset"]').first();
  if (await divider.count() > 0) {
    console.log('Found resizable divider');

    // Get the divider's bounding box
    const dividerBox = await divider.boundingBox();
    if (dividerBox) {
      // Drag the divider to make the panel wider
      const startX = dividerBox.x + dividerBox.width / 2;
      const startY = dividerBox.y + dividerBox.height / 2;

      await page.mouse.move(startX, startY);
      await page.mouse.down();
      await page.mouse.move(startX - 200, startY); // Drag left to make panel wider
      await page.mouse.up();

      await page.waitForTimeout(500);
      await page.screenshot({ path: 'test-results/10-after-resize-wider.png', fullPage: true });
      console.log('Resized panel wider');

      // Drag back to make it narrower
      const newDividerBox = await divider.boundingBox();
      if (newDividerBox) {
        const newStartX = newDividerBox.x + newDividerBox.width / 2;
        await page.mouse.move(newStartX, startY);
        await page.mouse.down();
        await page.mouse.move(newStartX + 300, startY); // Drag right to make panel narrower
        await page.mouse.up();

        await page.waitForTimeout(500);
        await page.screenshot({ path: 'test-results/11-after-resize-narrower.png', fullPage: true });
        console.log('Resized panel narrower');
      }

      // Double-click to reset
      await divider.dblclick();
      await page.waitForTimeout(500);
      await page.screenshot({ path: 'test-results/12-after-reset.png', fullPage: true });
      console.log('Reset panel to default width');
    }
  } else {
    console.log('Resizable divider not found');
  }

  await page.screenshot({ path: 'test-results/09-final.png', fullPage: true });
});
