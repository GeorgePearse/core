import { test, expect } from '@playwright/test';

test.describe('Genesis Auto-Load Database', () => {
  test('should automatically load database and show programs', async ({ page }) => {
    // Monitor API calls
    let listDbsCalled = false;
    let getProgramsCalled = false;
    let programsCount = 0;
    
    page.on('response', async response => {
      const url = response.url();
      
      if (url.includes('list_databases')) {
        listDbsCalled = true;
        const data = await response.json();
        console.log(`✅ list_databases called - returned ${data.length} databases`);
      }
      
      if (url.includes('get_programs')) {
        getProgramsCalled = true;
        const data = await response.json();
        programsCount = data.length;
        console.log(`✅ get_programs called - returned ${data.length} programs`);
        console.log(`   Database: ${url.split('db_path=')[1]}`);
        if (data.length > 0) {
          console.log(`   First program: Gen ${data[0].generation}, Score ${data[0].combined_score}`);
        }
      }
    });
    
    // Navigate to app
    await page.goto('http://localhost:5173');
    
    // Wait for network to be idle (all API calls complete)
    await page.waitForLoadState('networkidle');
    
    // Wait a bit more for rendering
    await page.waitForTimeout(3000);
    
    // Take screenshot of final state
    await page.screenshot({ 
      path: 'test-results/auto-load-final.png',
      fullPage: true 
    });
    
    // Verify API calls were made
    console.log('\n📊 API Call Summary:');
    console.log(`   list_databases: ${listDbsCalled ? '✅' : '❌'}`);
    console.log(`   get_programs: ${getProgramsCalled ? '✅' : '❌'}`);
    console.log(`   Programs loaded: ${programsCount}`);
    
    expect(listDbsCalled, 'list_databases should be called').toBe(true);
    expect(getProgramsCalled, 'get_programs should be called').toBe(true);
    expect(programsCount, 'Should load at least one program').toBeGreaterThan(0);
    
    // Check page content
    const bodyText = await page.textContent('body');
    
    // Look for indicators that programs are displayed
    const hasGeneration = bodyText?.includes('generation') || bodyText?.includes('Generation');
    const hasScore = bodyText?.includes('score') || bodyText?.includes('Score');
    const hasProgram = bodyText?.includes('program') || bodyText?.includes('Program');
    
    console.log('\n🔍 UI Content Check:');
    console.log(`   Contains "generation": ${hasGeneration ? '✅' : '❌'}`);
    console.log(`   Contains "score": ${hasScore ? '✅' : '❌'}`);
    console.log(`   Contains "program": ${hasProgram ? '✅' : '❌'}`);
    
    // Count visible elements
    const visibleCount = await page.locator('*:visible').count();
    console.log(`   Visible elements: ${visibleCount}`);
    
    // Look for specific UI components
    const leftPanel = await page.locator('[class*="left"], [class*="panel"], [class*="sidebar"]').count();
    const rightPanel = await page.locator('[class*="right"], [class*="detail"]').count();
    
    console.log(`   Left panels found: ${leftPanel}`);
    console.log(`   Right panels found: ${rightPanel}`);
    
    // Get all visible text for debugging
    const allText = await page.locator('body').allTextContents();
    const textPreview = allText[0]?.substring(0, 500);
    console.log(`\n📝 Page text preview:\n${textPreview}...`);
  });
  
  test('should show database name in UI', async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    
    // Look for database name display
    const dbNameElement = page.locator('text=/mask_to_seg|squeeze|circle_packing/i').first();
    const dbNameVisible = await dbNameElement.isVisible().catch(() => false);
    
    console.log(`Database name visible: ${dbNameVisible ? '✅' : '❌'}`);
    
    if (dbNameVisible) {
      const text = await dbNameElement.textContent();
      console.log(`Database name text: "${text}"`);
    }
  });
  
  test('should display programs in tree or table view', async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    
    // Look for common UI patterns
    const rows = await page.locator('tr, [role="row"]').count();
    const listItems = await page.locator('li, [role="listitem"]').count();
    const treeItems = await page.locator('[role="treeitem"]').count();
    
    console.log(`\n🎨 UI Elements Found:`);
    console.log(`   Table rows: ${rows}`);
    console.log(`   List items: ${listItems}`);
    console.log(`   Tree items: ${treeItems}`);
    
    const totalItems = rows + listItems + treeItems;
    console.log(`   Total data items: ${totalItems}`);
    
    // At least one of these should have content
    expect(totalItems).toBeGreaterThan(0);
  });
});
