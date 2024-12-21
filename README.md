[![GitHub All Releases](https://img.shields.io/github/downloads/afkarxyz/SpotifyDown-GUI/total?style=for-the-badge)](https://github.com/afkarxyz/SpotifyDown-GUI/releases)

**SpotifyDown GUI** is a graphical user interface for downloading Spotify tracks, albums, and playlists directly from Spotify using an API created by SpotifyDown.com

### [Download](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.0/SpotifyDown.exe) SpotifyDown GUI

## Screenshots

![image](https://github.com/user-attachments/assets/f1fb5a71-6e81-48de-9c1c-718fb936a023)

![image](https://github.com/user-attachments/assets/ac85475b-746a-4eae-93fc-ec3b5606191e)

![image](https://github.com/user-attachments/assets/7ddf6be4-b24a-45cc-ae74-ee6a5d5adbd4)

## Features

- Download individual tracks, entire albums, or playlists
- The ability to download more than `100 tracks`
- High-quality audio download at `320 kbps`
- No Spotify account required

> [!IMPORTANT]  
> Due to updates in the API, a token is required periodically. Follow the steps below to obtain the token.

## Obtaining Tokens Manually

1. Visit [https://spotifydown.com/](https://spotifydown.com/) and open the **Network** tab in your browser's developer tools (press `F12`).  
2. While the Network tab is open, press the download button. Then, press the second download button.
3. Filter the requests to display only **Fetch/XHR**, then look for `{track_id}?token=` and click on it.  
4. Open the **Payload** tab.
   
![image](https://github.com/user-attachments/assets/00448018-482f-4b19-b143-7b4ee8d9bca9)

5. Copy token value.

#### Or you can use this userscript [SpotifyDown Token Grabber](https://github.com/afkarxyz/SpotifyDown-GUI/raw/refs/heads/main/SpotifyDown.user.js)

![image](https://github.com/user-attachments/assets/f0a90511-973f-4917-8de9-5f34cf346f36)

## Obtaining Tokens Automatically

![image](https://github.com/user-attachments/assets/a4116cd6-d273-4af0-b702-abac61ea4eec)

### [Download](https://github.com/afkarxyz/SpotifyDown-GUI/releases/download/v1.0/TokenGrabber.exe) Token Grabber
