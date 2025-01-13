> [!IMPORTANT]  
> Due to updates in the API, a token is required periodically. It seems that the token expiration period is around 10 minutes. Follow the steps below to obtain the token.

## Obtaining Tokens

![image](https://github.com/user-attachments/assets/00448018-482f-4b19-b143-7b4ee8d9bca9)

1. Visit [https://spotifydown.com](https://spotifydown.com/) and open the **Network** tab in your browser's developer tools (press `F12`).  
2. While the Network tab is open, press the download button. Then, press the second download button.
3. Filter the requests to display only **Fetch/XHR**, then look for `{track_id}?token=` and click on it.  
4. Open the **Payload** tab.
5. Copy the token value.
