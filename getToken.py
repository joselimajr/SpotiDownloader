import asyncio
import zendriver as zd

async def get_token(max_wait=10):
    browser = await zd.start(headless=False)
    try:
        page = await browser.get("https://spotidownloader.com/")
        
        await page.evaluate("""
            window.originalFetch = window.fetch;
            window.fetch = function() {
                return new Promise((resolve, reject) => {
                    window.originalFetch.apply(this, arguments)
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
        
        for _ in range(max_wait * 10):
            token = await page.evaluate("window.sessionToken")
            if token:
                return token
            await asyncio.sleep(0.1)
            
        return None
                
    finally:
        await browser.stop()

async def main():
    try:
        token = await get_token()
        if token:
            print(token)
            return token
        else:
            print("Not found")
            return None
        
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(main())