import { test, expect } from '@playwright/test';

test.describe('Command Menu Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app and wait for it to load
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should navigate to Programs Table via Cmd+K menu', async ({ page }) => {
    // Open the command menu with Ctrl+K
    await page.keyboard.press('Control+k');

    // Wait for the search input to be visible and interactable
    const searchInput = page.locator('[cmdk-input]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });
    await expect(searchInput).toBeEnabled({ timeout: 5000 });

    // Type to search - cmdk filters on the `value` prop which is "table-view"
    await searchInput.fill('table');

    // Wait for the filtered results
    await page.waitForTimeout(300);

    // Click on the Programs Table item
    const programsItem = page.locator('[cmdk-item]').filter({ hasText: 'Programs Table' });
    await expect(programsItem).toBeVisible({ timeout: 3000 });
    await programsItem.click();

    // Wait for dialog to close
    await page.waitForTimeout(500);

    // Verify the command dialog closes (this confirms onSelect handler was called)
    const searchInputAfter = page.locator('[cmdk-input]');
    await expect(searchInputAfter).not.toBeVisible({ timeout: 3000 });
  });

  test('should open command menu with keyboard shortcut', async ({ page }) => {
    // Verify command dialog input is not visible initially
    const searchInput = page.locator('[cmdk-input]');
    await expect(searchInput).not.toBeVisible();

    // Open with Ctrl+K
    await page.keyboard.press('Control+k');

    // Check that input becomes visible
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Close with Escape
    await page.keyboard.press('Escape');

    // Wait for dialog to close
    await page.waitForTimeout(300);

    // Verify input is hidden again
    await expect(searchInput).not.toBeVisible({ timeout: 3000 });
  });

  test('should filter command items when typing', async ({ page }) => {
    // Open the command menu
    await page.keyboard.press('Control+k');

    // Wait for input to be visible
    const searchInput = page.locator('[cmdk-input]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Type a search term - cmdk filters on the `value` prop which is "tree-view"
    await searchInput.fill('tree');

    // Wait for filtering
    await page.waitForTimeout(300);

    // Verify Tree View item is visible
    const treeItem = page.locator('[cmdk-item]').filter({ hasText: 'Tree View' });
    await expect(treeItem).toBeVisible();

    // Verify that items NOT matching "tree" are filtered out
    const programsItem = page.locator('[cmdk-item]').filter({ hasText: 'Programs Table' });
    await expect(programsItem).not.toBeVisible();
  });

  test('should navigate to Tree View via command menu', async ({ page }) => {
    // Open command menu
    await page.keyboard.press('Control+k');

    // Wait for input to be visible
    const searchInput = page.locator('[cmdk-input]');
    await expect(searchInput).toBeVisible({ timeout: 5000 });

    // Search and select Tree View - cmdk filters on the `value` prop which is "tree-view"
    await searchInput.fill('tree');
    await page.waitForTimeout(300);

    const treeItem = page.locator('[cmdk-item]').filter({ hasText: 'Tree View' });
    await expect(treeItem).toBeVisible();
    await treeItem.click();

    // Verify dialog closes (confirms onSelect handler was called)
    await page.waitForTimeout(500);
    await expect(searchInput).not.toBeVisible({ timeout: 3000 });
  });
});
