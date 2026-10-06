import time
from playwright.sync_api import sync_playwright


def test_embeddings_visible():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))

        # Navigate to UI
        print("Navigating to UI...")
        page.goto("http://localhost:5173")
        page.wait_for_load_state("networkidle")

        # Check if database is loaded (should be auto-loaded)
        # Select "Programs" tab (default)
        # Click "Embeddings" in sidebar or command menu

        print("Opening Command Menu...")
        page.keyboard.press("Meta+k")
        time.sleep(1)

        print("Selecting Embeddings view...")
        # Try clicking sidebar icon instead of command menu
        # Assuming sidebar has an icon/button with title "Embeddings" or similar
        # Or just use the command menu again with explicit wait

        # Check if database loaded
        if page.locator("text=No Database Selected").count() > 0:
            print("Database not loaded automatically. Loading via Command Menu...")
            page.keyboard.press("Meta+k")
            time.sleep(1)
            page.keyboard.type("Load Database")
            time.sleep(0.5)
            page.keyboard.press("Enter")
            time.sleep(1)
            # Now select the first database
            page.keyboard.press("Enter")
            time.sleep(2)

        if page.locator(".programs-view").count() > 0:
            print("Programs view is visible initially.")
        else:
            print("Programs view NOT visible initially.")

        print("Clicking Embeddings in sidebar...")
        page.click("text=Embeddings")
        time.sleep(2)

        # Check active tab in UI
        header = page.locator("h2").first.inner_text()
        print(f"Current header: {header}")

        # Check if plot is visible
        # Look for "clusters-view" class
        if page.locator(".clusters-view").count() > 0:
            print("Clusters view found.")

            # Check for empty message
            if page.locator(".clusters-view.empty").count() > 0:
                print(
                    "FAILURE: Clusters view is showing 'No PCA embedding data available'."
                )
                # Take screenshot
                page.screenshot(path="/tmp/ui_failure.png")
            else:
                print("SUCCESS: Clusters view is populated (plot visible).")
                # Check for plot container
                if page.locator(".plot-container").count() > 0:
                    print("Plot container found.")
                else:
                    print("WARNING: Plot container not found despite not being empty.")
                    page.screenshot(path="/tmp/ui_warning.png")
        else:
            print("FAILURE: Clusters view component not found.")
            page.screenshot(path="/tmp/ui_not_found.png")
            # Print body content to debug
            print(page.locator("body").inner_html())

        browser.close()


if __name__ == "__main__":
    test_embeddings_visible()
