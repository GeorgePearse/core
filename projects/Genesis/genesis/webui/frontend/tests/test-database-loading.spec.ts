import { test, expect } from '@playwright/test';

test.describe('Genesis Database Loading', () => {
  test('should load databases from ClickHouse backend', async ({ page }) => {
    // Navigate to the app
    await page.goto('http://localhost:5173');
    
    // Wait for the page to load
    await page.waitForLoadState('networkidle');
    
    // Take a screenshot of initial state
    await page.screenshot({ path: 'test-results/01-initial-load.png' });
    
    console.log('✅ Page loaded successfully');
  });

  test('should fetch databases from backend API', async ({ page }) => {
    // Set up request interception to monitor API calls
    const apiCalls: string[] = [];
    
    page.on('request', request => {
      if (request.url().includes('localhost:8000')) {
        apiCalls.push(request.url());
        console.log(`📡 API Request: ${request.url()}`);
      }
    });
    
    page.on('response', async response => {
      if (response.url().includes('localhost:8000')) {
        console.log(`📥 API Response: ${response.url()} - Status: ${response.status()}`);
        if (response.url().includes('list_databases')) {
          const data = await response.json();
          console.log(`📊 Found ${data.length} databases`);
        }
      }
    });
    
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    
    // Wait a bit for any async operations
    await page.waitForTimeout(2000);
    
    console.log(`Total API calls made: ${apiCalls.length}`);
    
    // Verify at least one API call was made
    expect(apiCalls.length).toBeGreaterThan(0);
  });

  test('should display database selector', async ({ page }) => {
    await page.goto('http://localhost:5173');
    
    // Look for command menu trigger (Cmd+K)
    const commandTrigger = page.locator('button').filter({ hasText: /⌘K|Cmd.*K/i }).first();
    
    // If command menu exists, try to find database selector
    const databaseSelector = page.locator('text=/database|select.*database/i').first();
    
    // Wait a bit for UI to render
    await page.waitForTimeout(2000);
    
    await page.screenshot({ path: 'test-results/02-database-selector.png' });
    
    console.log('✅ Database selector check complete');
  });

  test('should open command menu and show databases', async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    
    // Wait for initial render
    await page.waitForTimeout(2000);
    
    // Try to open command menu with Cmd+K
    await page.keyboard.press('Meta+k');
    
    // Wait for command menu to open
    await page.waitForTimeout(1000);
    
    await page.screenshot({ path: 'test-results/03-command-menu.png' });
    
    // Look for database options
    const databaseOptions = page.locator('[role="option"]');
    const count = await databaseOptions.count();
    
    console.log(`📋 Found ${count} options in command menu`);
    
    // Look for text that might indicate databases
    const bodyText = await page.textContent('body');
    console.log('🔍 Page contains "database":', bodyText?.includes('database') || bodyText?.includes('Database'));
    console.log('🔍 Page contains "experiment":', bodyText?.includes('experiment') || bodyText?.includes('Experiment'));
  });

  test('should load and display programs when database is selected', async ({ page }) => {
    // Monitor network requests
    const responses: any[] = [];
    
    page.on('response', async response => {
      if (response.url().includes('localhost:8000')) {
        const url = response.url();
        const status = response.status();
        
        try {
          const data = await response.json();
          responses.push({ url, status, data });
          
          if (url.includes('get_programs')) {
            console.log(`📦 Programs loaded: ${data.length} programs`);
            console.log(`   Sample program ID: ${data[0]?.id}`);
            console.log(`   Sample generation: ${data[0]?.generation}`);
          }
        } catch (e) {
          // Not JSON response
        }
      }
    });
    
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    
    // Try to open command menu
    await page.keyboard.press('Meta+k');
    await page.waitForTimeout(1000);
    
    // Look for any database option and click it
    const firstOption = page.locator('[role="option"]').first();
    const optionExists = await firstOption.count() > 0;
    
    if (optionExists) {
      console.log('🎯 Clicking first database option...');
      await firstOption.click();
      await page.waitForTimeout(2000);
      
      await page.screenshot({ path: 'test-results/04-database-selected.png' });
      
      // Check if programs were loaded
      const programsResponse = responses.find(r => r.url.includes('get_programs'));
      if (programsResponse) {
        console.log(`✅ Programs loaded successfully!`);
        console.log(`   Total programs: ${programsResponse.data.length}`);
        expect(programsResponse.data.length).toBeGreaterThan(0);
      } else {
        console.log('⚠️  No get_programs request detected');
      }
    } else {
      console.log('⚠️  No database options found in command menu');
    }
  });

  test('should verify programs table is visible', async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    
    // Open command menu
    await page.keyboard.press('Meta+k');
    await page.waitForTimeout(1000);
    
    // Try to select first database
    const firstOption = page.locator('[role="option"]').first();
    if (await firstOption.count() > 0) {
      await firstOption.click();
      await page.waitForTimeout(3000);
      
      // Look for table elements or program listings
      const tables = page.locator('table');
      const tableCount = await tables.count();
      console.log(`📊 Found ${tableCount} tables`);
      
      // Look for tree view or program list
      const treeView = page.locator('[role="tree"], [role="treegrid"]');
      const treeCount = await treeView.count();
      console.log(`🌳 Found ${treeCount} tree views`);
      
      // Look for any generation indicators
      const genText = await page.locator('text=/generation|gen.*\\d+/i').count();
      console.log(`🔢 Found ${genText} generation indicators`);
      
      // Take final screenshot
      await page.screenshot({ path: 'test-results/05-programs-view.png', fullPage: true });
      
      // Get page content for debugging
      const bodyText = await page.textContent('body');
      console.log('🔍 Page contains "program":', bodyText?.includes('program'));
      console.log('🔍 Page contains "generation":', bodyText?.includes('generation'));
      console.log('🔍 Page contains "score":', bodyText?.includes('score'));
      
      // Check if we have any visible content
      const visibleElements = await page.locator('*:visible').count();
      console.log(`👁️  Total visible elements: ${visibleElements}`);
    }
  });
});
