[![GitHub All Releases](https://img.shields.io/github/downloads/afkarxyz/SpotifyDown-GUI/total?style=for-the-badge)](https://github.com/afkarxyz/SpotifyDown-GUI/releases)

**SpotifyDown GUI** is a graphical user interface for downloading Spotify tracks, albums, and playlists directly from Spotify using an API created by spotifydown.com

### [Download](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.2/SpotifyDown.exe) SpotifyDown GUI

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

## Obtaining Tokens Manually

1. Visit [https://spotifydown.com](https://spotifydown.com/) and open the **Network** tab in your browser's developer tools (press `F12`).  
2. While the Network tab is open, press the download button. Then, press the second download button.
3. Filter the requests to display only **Fetch/XHR**, then look for `{track_id}?token=` and click on it.  
4. Open the **Payload** tab.
   
![image](https://github.com/user-attachments/assets/00448018-482f-4b19-b143-7b4ee8d9bca9)

5. Copy the token value.

#### Or you can use this userscript [Token Grabber](https://github.com/afkarxyz/SpotifyDown-GUI/raw/refs/heads/main/TokenGrabber.user.js)

![image](https://github.com/user-attachments/assets/f0a90511-973f-4917-8de9-5f34cf346f36)

> [!NOTE]  
> Requires **Tampermonkey**

## Obtaining Tokens Automatically

`Normal` speed has a 5-second delay, while `Slow` speed has a 10-second delay.

![image](https://github.com/user-attachments/assets/ec72ef14-e25d-4cfd-ab70-852fac00fa41)

> [!NOTE]  
> Requires **Google Chrome**

#### [Download](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.1/TokenGrabber.exe) Token Grabber
