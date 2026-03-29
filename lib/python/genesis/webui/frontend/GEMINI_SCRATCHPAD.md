# Scratchpad: Fixing Command Menu Tests

## Current Status
- **Test File:** `tests/command-menu.spec.ts`
- **Issue:** Tests for "Command Menu Navigation" are failing to assert the active tab state.
- **Symptoms:** The test clicks the menu item, but the assertion for the active tab times out or fails.

## Diagnosis
1. **Code Review:**
   - `CommandMenu.tsx` was recently fixed to ensure commands execute before closing the menu. This logic appears correct now.
   - `LeftPanel.tsx` renders tabs with the class `left-tab` (singular).
   - `LeftPanel.css` styles these as `.left-tabs .left-tab`.
   - When active, the class is `.left-tab.active`.

2. **Selector Mismatch:**
   - The Playwright test likely uses a selector like `.left-tabs button.active` or similar generic selector.
   - The actual DOM element is a `<button>` with class `left-tab`.
   - The CSS rule is `.left-tabs .left-tab.active`.

## Recommended Fix
Update the selector in `tests/command-menu.spec.ts` to specifically target the correct class structure.

**Change:**
From:
```typescript
// Likely current incorrect selector
page.locator('.left-tabs button.active') 
// or 
page.locator('.left-tabs >> text=Tree')
```

To:
```typescript
// Correct selector matching LeftPanel.css
page.locator('.left-tabs .left-tab.active')
```

## Action Plan for Gemini
1. Read `genesis/webui/frontend/tests/command-menu.spec.ts`.
2. Locate the assertions checking for the active tab (e.g., `expect(page.locator(...)).toHaveClass(/active/)` or similar).
3. Update the locator to use `.left-tabs .left-tab.active` or ensure it targets the `.left-tab` class specifically.
4. Run the tests again to verify the fix.
