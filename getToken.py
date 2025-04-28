import asyncio
import zendriver as zd

async def get_turnstile_token(page, max_attempts=20, check_interval=0.5):
    attempts = 0
    while attempts < max_attempts:
        element = await page.query_selector('input[name="cf-turnstile-response"]')
        if element:
            attrs = element.attrs
            if attrs and 'value' in attrs:
                return attrs['value']
        await asyncio.sleep(check_interval)
        attempts += 1
    return None

async def get_session_token(max_wait=30):
    browser = await zd.start(headless=False)
    try:
        page = await browser.get("https://spotidownloader.com/")
        
        await page.evaluate("""
            window.originalFetch = window.fetch;
            window.sessionToken = null;
            
            window.fetch = function() {
                const fetchArgs = arguments;
                return new Promise((resolve, reject) => {
                    window.originalFetch.apply(this, fetchArgs)
                        .then(async response => {
                            if (response.url.includes('api.spotidownloader.com/session')) {
                                try {
                                    const clonedResponse = response.clone();
                                    const responseData = await clonedResponse.json();
                                    if (responseData && responseData.token) {
                                        window.sessionToken = responseData.token;
                                    }
                                } catch (e) {}
                            }
                            resolve(response);
                        })
                        .catch(reject);
                });
            };
        """)
        
        turnstile_token = await get_turnstile_token(page)
        if not turnstile_token:
            return None
        
        await page.evaluate("""
            const button = document.querySelector("button.flex.justify-center.items-center.bg-button");
            if (button) {
                button.click();
            }
        """)
        
        for i in range(max_wait * 2):
            token = await page.evaluate("window.sessionToken")
            if token:
                return token
            await asyncio.sleep(0.5)
        
        return None
                
    except Exception as e:
        return None
    finally:
        await browser.stop()

async def main():
    try:
        token = await get_session_token()
        if token:
            print(token)
            return token
        return None
        
    except Exception as e:
        return None

if __name__ == "__main__":
    asyncio.run(main())