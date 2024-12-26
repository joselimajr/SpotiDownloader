[![GitHub All Releases](https://img.shields.io/github/downloads/afkarxyz/SpotifyDown-GUI/total?style=for-the-badge)](https://github.com/afkarxyz/SpotifyDown-GUI/releases)

**SpotifyDown GUI** is a graphical user interface for downloading Spotify tracks, albums, and playlists directly from Spotify using an API created by spotifydown.com

### [Download](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.3/SpotifyDown.exe) SpotifyDown GUI

## Screenshots

![image](https://github.com/user-attachments/assets/74bea158-4b62-403b-bd37-38e9085ae471)

![image](https://github.com/user-attachments/assets/325da8cb-a2f2-4b20-a467-a69537de45e2)

![image](https://github.com/user-attachments/assets/8e4d25a8-be9f-4b3a-b300-1fcf98d353eb)

## Features

- Download individual tracks, entire albums, or playlists
- The ability to download more than `100 tracks` from a playlist  
- The ability to download more than `50 tracks` from an album
- High-quality audio download at `320 kbps`
- No Spotify account required

> [!IMPORTANT]  
> Due to updates in the API, a token is required periodically. It seems that the token expiration period is around 10 minutes. Follow the steps below to obtain the token.

## 1. Obtaining Tokens Manually

![image](https://github.com/user-attachments/assets/00448018-482f-4b19-b143-7b4ee8d9bca9)

1. Visit [https://spotifydown.com](https://spotifydown.com/) and open the **Network** tab in your browser's developer tools (press `F12`).  
2. While the Network tab is open, press the download button. Then, press the second download button.
3. Filter the requests to display only **Fetch/XHR**, then look for `{track_id}?token=` and click on it.  
4. Open the **Payload** tab.
5. Copy the token value.
   
## 2. Obtaining Tokens Semi-Automatically

![image](https://github.com/user-attachments/assets/7c79c2da-9c64-4000-ad85-b8e8eb68fe69)

> [!NOTE]
> - Wait until Cloudflare verification is successful, then press **Get Token**
> - Requires **Tampermonkey**

#### Install [Token Grabber Script](https://github.com/afkarxyz/SpotifyDown-GUI/raw/refs/heads/main/TokenGrabber.user.js)

## 3. Obtaining Tokens Automatically

![image](https://github.com/user-attachments/assets/3c264911-d132-4d39-96ce-dce4b201022b)

> [!NOTE]  
> Requires **Google Chrome**

#### Download [Token Grabber](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.2/TokenGrabber.exe)
