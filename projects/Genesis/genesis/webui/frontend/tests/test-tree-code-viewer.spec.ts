import { test, expect } from '@playwright/test';

test('clicking tree node shows code in viewer', async ({ page }) => {
  await page.goto('http://localhost:5173/');
  await page.waitForTimeout(2000);

  // Select task - use genesis_mask_to_seg_rust which has actual data
  const taskButton = page.locator('button:has-text("Select a task")').first();
  if (await taskButton.isVisible()) {
    await taskButton.click();
    await page.waitForTimeout(500);

    // Look for mask_to_seg_rust task specifically
    const maskToSegTask = page.locator('.absolute.z-10 button:has-text("mask_to_seg_rust")').first();
    if (await maskToSegTask.count() > 0) {
      await maskToSegTask.click();
    } else {
      // Fallback to first task
      const taskOptions = await page.locator('.absolute.z-10 button').all();
      if (taskOptions.length > 0) {
        await taskOptions[0].click();
      }
    }
    await page.waitForTimeout(500);
  }

  // Wait for database to load
  await page.waitForTimeout(3000);

  // Make sure we're on Tree view (default)
  const treeButton = page.locator('button:has-text("Tree")').first();
  if (await treeButton.isVisible()) {
    await treeButton.click();
    await page.waitForTimeout(1000);
  }

  await page.screenshot({ path: 'test-results/tree-01-initial.png', fullPage: true });

  // Look for tree nodes (SVG g elements inside g.nodes)
  // The tree renders nodes as <g class="nodes"><g>...</g><g>...</g>...</g>
  const treeNodes = await page.locator('.tree-view-container svg g.nodes > g').all();
  console.log('Found tree nodes:', treeNodes.length);

  // Also log if there's any SVG at all
  const svgCount = await page.locator('.tree-view-container svg').count();
  console.log('SVG elements found:', svgCount);

  if (treeNodes.length > 0) {
    // Click the first tree node
    console.log('Clicking first tree node...');
    await treeNodes[0].click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/tree-02-after-click.png', fullPage: true });

    // Check if code viewer has content
    const codePanel = page.locator('.code-viewer-panel').first();
    if (await codePanel.count() > 0) {
      const codeElement = page.locator('.code-viewer-panel code').first();
      if (await codeElement.count() > 0) {
        const codeText = await codeElement.textContent();
        console.log('Code content (first 200 chars):', codeText?.substring(0, 200));
      }
    } else {
      console.log('Code viewer panel not found after clicking tree node');
    }
  } else {
    console.log('No tree nodes found');
  }

  await page.screenshot({ path: 'test-results/tree-03-final.png', fullPage: true });
});
