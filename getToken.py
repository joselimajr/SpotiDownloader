import asyncio
import zendriver as zd

async def wait_for_turnstile_token(page, max_attempts=20, check_interval=0.5):
    attempts = 0
    while attempts < max_attempts:
        element = await page.query_selector('input[name="cf-turnstile-response"]')
        if element:
            attrs = element.attrs
            if attrs and 'value' in attrs:
                return attrs['value']
        await asyncio.sleep(check_interval)
        attempts += 1
    raise TimeoutError("Turnstile element not found within timeout period")

async def fetch_token(delay=5):
    browser = await zd.start(headless=False)
    try:
        print("Opening spotidownloader.com...")
        page = await browser.get("https://spotidownloader.com/")
        
        print("Waiting for turnstile token...")
        token = await wait_for_turnstile_token(page)
        return token
                
    finally:
        await browser.stop()

async def main():
    try:
        print("Starting token grabber...")
        token = await fetch_token()
        print(f"\nToken retrieved successfully:")
        print(f"{token}")
        return token
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

if __name__ == "__main__":
    token = asyncio.run(main())
