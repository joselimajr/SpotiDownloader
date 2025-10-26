from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage
import requests
import time

def get_session_token_sync(max_wait=30):
    page = None
    try:
        page = ChromiumPage()
        page.get("https://spotidownloader.com/")

        bypasser = CloudflareBypasser(page, max_retries=3, log=True)
        bypasser.bypass()

        if not bypasser.is_bypassed():
            return None

        print("Cloudflare bypassed successfully.")

        custom_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            # 'Origin': 'https://spotidownloader.com',
            'Referer': 'https://spotidownloader.com/'
        }

        r = requests.post("https://api.spotidownloader.com/session", headers=custom_headers)

        if r.status_code != 200:
            print("Failed to initiate session request.")

        if "token" in r.json():
            return r.json()["token"]

        print(r.json())

        page.run_js("""
            window.originalFetch = window.fetch;
            window.sessionToken = null;
            window.fetch = function(...args) {
                return window.originalFetch(...args).then(async response => {
                    if (response.url.includes('api.spotidownloader.com/session')) {
                        try {
                            const data = await response.clone().json();
                            if (data?.token) window.sessionToken = data.token;
                        } catch {}
                    }
                    return response;
                });
            };
        """)

        for _ in range(max_wait * 2):
            token = page.run_js("return window.sessionToken")
            if token:
                return token
            time.sleep(0.5)

        return None
    except:
        return None
    finally:
        if page:
            try:
                page.quit()
            except:
                pass

async def main():
    return get_session_token_sync()

def get_token():
    return get_session_token_sync()

if __name__ == "__main__":
    token = get_token()
    if token:
        print(token)