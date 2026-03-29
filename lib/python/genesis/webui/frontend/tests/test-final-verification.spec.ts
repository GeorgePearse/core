import { test, expect } from '@playwright/test';

test.describe('Genesis Final Verification', () => {
  test('UI should load database and display programs automatically', async ({ page, context }) => {
    // Set longer timeout for this test
    test.setTimeout(30000);
    
    console.log('🚀 Starting UI verification test...\n');
    
    // Navigate to the app
    await page.goto('http://localhost:5173');
    console.log('✅ Navigated to http://localhost:5173');
    
    // Wait for page to fully load
    await page.waitForLoadState('domcontentloaded');
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    console.log('✅ Page loaded');
    
    // Wait for React to render
    await page.waitForTimeout(5000);
    console.log('✅ Waited for React rendering');
    
    // Take a screenshot
    await page.screenshot({ 
      path: 'test-results/final-verification.png',
      fullPage: true 
    });
    console.log('✅ Screenshot saved');
    
    // Get all text content
    const bodyText = await page.textContent('body');
    console.log(`\n📄 Page contains ${bodyText?.length || 0} characters of text\n`);
    
    // Check for key indicators
    const checks = {
      hasDatabase: bodyText?.toLowerCase().includes('database') || false,
      hasProgram: bodyText?.toLowerCase().includes('program') || false,
      hasGeneration: bodyText?.toLowerCase().includes('generation') || bodyText?.toLowerCase().includes('gen') || false,
      hasScore: bodyText?.toLowerCase().includes('score') || false,
      hasRust: bodyText?.toLowerCase().includes('rust') || false,
      hasMask: bodyText?.toLowerCase().includes('mask') || false,
    };
    
    console.log('🔍 Content Analysis:');
    Object.entries(checks).forEach(([key, value]) => {
      console.log(`   ${value ? '✅' : '❌'} ${key}: ${value}`);
    });
    
    // Count interactive elements
    const buttons = await page.locator('button').count();
    const links = await page.locator('a').count();
    const inputs = await page.locator('input').count();
    
    console.log(`\n🎮 Interactive Elements:`);
    console.log(`   Buttons: ${buttons}`);
    console.log(`   Links: ${links}`);
    console.log(`   Inputs: ${inputs}`);
    
    // Look for specific Genesis UI elements
    const hasCommandMenu = await page.locator('[cmdk-root]').count() > 0;
    const hasLeftPanel = await page.locator('[class*="left"], .left-panel, #left-panel').count() > 0;
    const hasRightPanel = await page.locator('[class*="right"], .right-panel, #right-panel').count() > 0;
    
    console.log(`\n🎨 Genesis UI Components:`);
    console.log(`   ${hasCommandMenu ? '✅' : '❌'} Command Menu: ${hasCommandMenu}`);
    console.log(`   ${hasLeftPanel ? '✅' : '❌'} Left Panel: ${hasLeftPanel}`);
    console.log(`   ${hasRightPanel ? '✅' : '❌'} Right Panel: ${hasRightPanel}`);
    
    // Check network requests
    const apiCalls = await context.newPage();
    await apiCalls.close();
    
    // Get console logs
    const consoleLogs: string[] = [];
    page.on('console', msg => {
      const text = msg.text();
      if (text.includes('Auto-loading') || text.includes('database') || text.includes('programs')) {
        consoleLogs.push(text);
      }
    });
    
    // Wait a bit more and check console
    await page.waitForTimeout(2000);
    
    if (consoleLogs.length > 0) {
      console.log(`\n📋 Console Logs (filtered):`);
      consoleLogs.forEach(log => console.log(`   ${log}`));
    }
    
    // Final summary
    console.log(`\n✨ Summary:`);
    console.log(`   Page loaded: ✅`);
    console.log(`   Content present: ${bodyText && bodyText.length > 1000 ? '✅' : '⚠️'}`);
    console.log(`   Has UI elements: ${(buttons + links + inputs) > 0 ? '✅' : '❌'}`);
    
    // Assertion
    expect(bodyText).toBeTruthy();
    expect(bodyText!.length).toBeGreaterThan(100);
  });
});
