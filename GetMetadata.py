import sys
import io
import re
import aiohttp
import asyncio
import unicodedata
from typing import Dict, Any, List
from spotapi import Song, PublicAlbum, PublicPlaylist

if sys.stdout is None or not hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.StringIO()
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def is_emoji(char):
    return unicodedata.category(char).startswith(('So', 'Sm', 'Sk', 'Sc'))

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    cleaned = ''.join(char for char in text if not is_emoji(char))
    cleaned = re.sub(r'\.{2,}$|…$|\.$', '', cleaned)
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()

def format_duration(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"

def extract_spotify_id(url: str) -> str:
    match = re.search(r'spotify\.com/(?:track|album|playlist)/([a-zA-Z0-9]{22})', url)
    return match.group(1) if match else url

def modify_cover_size(cover_url: str, size: str = "300") -> str:
    size = str(size).replace('px', '').lower()
    
    size_codes = {
        "300": "ab67616d00001e02",
        "640": "ab67616d0000b273",
        "original": "ab67616d000082c1"
    }
    
    if not cover_url or "i.scdn.co/image/" not in cover_url:
        return cover_url
        
    pattern = r'i\.scdn\.co/image/[a-z0-9]{16}(.*?)$'
    match = re.search(pattern, cover_url)
    if not match:
        return cover_url
        
    unique_part = match.group(1)
    size_code = size_codes.get(size, size_codes["300"])
    
    return f"https://i.scdn.co/image/{size_code}{unique_part}"

async def get_track_metadata_from_api(session: aiohttp.ClientSession, track_id: str, cover_size: str = "300") -> Dict[str, Any]:
    url = f"https://spotify-down.com/api/metadata?link=https://open.spotify.com/track/{track_id}"
    headers = {
        'Origin': 'https://spotify-down.com',
        'Referer': 'https://spotify-down.com/'
    }
    payload = {'link': f'https://open.spotify.com/track/{track_id}'}
    
    async with session.post(url, headers=headers, json=payload) as response:
        if response.status != 200:
            raise ValueError(f"API request failed with status {response.status}")
        
        data = await response.json()
        track_data = data['data']
        
        cover_size = str(cover_size).replace('px', '')
        
        return {
            'cover': modify_cover_size(track_data['cover_url'], cover_size),
            'title': clean_text(track_data['title']),
            'artist': track_data['artists'],
            'album': clean_text(track_data['album']),
            'duration': format_duration(track_data['duration']),
            'release': track_data['release_date'],
            'isrc': track_data['isrc']
        }

async def extract_track_metadata(song: Song, track_id: str, cover_size: str = "300") -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        try:
            return await get_track_metadata_from_api(session, track_id, cover_size)
        except Exception as e:
            raise ValueError(f"Failed to fetch track metadata: {str(e)}")

async def fetch_track_metadata_batch(session: aiohttp.ClientSession, track_ids: List[str], cover_size: str = "300") -> List[Dict[str, Any]]:
    tasks = [get_track_metadata_from_api(session, track_id, cover_size) for track_id in track_ids]
    return await asyncio.gather(*tasks, return_exceptions=True)

async def extract_album_metadata(album: PublicAlbum, cover_size: str = "300") -> Dict[str, Any]:
    try:
        initial_data = album.get_album_info(limit=50)
        album_data = initial_data['data']['albumUnion']
        
        track_list = []
        total_duration_ms = 0
        
        async with aiohttp.ClientSession() as session:
            for page in album.paginate_album():
                track_ids = [track['track']['uri'].split(':')[-1] for track in page]
                track_metadata = await fetch_track_metadata_batch(session, track_ids, cover_size)
                
                for i, metadata in enumerate(track_metadata):
                    if isinstance(metadata, Exception):
                        continue
                    
                    duration_ms = int(metadata['duration'].split(':')[0]) * 60000 + \
                                int(metadata['duration'].split(':')[1]) * 1000
                    total_duration_ms += duration_ms
                    
                    track_list.append({
                        'id': track_ids[i],
                        'title': metadata['title'],
                        'artist': metadata['artist'],
                        'album': metadata['album'],
                        'cover': metadata['cover'],
                        'duration': metadata['duration'],
                        'release': metadata['release'],
                        'isrc': metadata['isrc']
                    })
        
        album_cover = album_data['coverArt']['sources'][2]['url']
        
        return {
            'album_info': {
                'cover': modify_cover_size(album_cover, cover_size),
                'title': clean_text(album_data['name']),
                'owner': clean_text(album_data['artists']['items'][0]['profile']['name']),
                'release': album_data['date']['isoString'].split('T')[0],
                'total': album_data['tracksV2']['totalCount'],
                'duration': format_duration(total_duration_ms)
            },
            'track_list': track_list
        }
    except Exception as e:
        raise ValueError(f"Failed to parse album data: {str(e)}")

async def extract_playlist_metadata(playlist: PublicPlaylist, cover_size: str = "300") -> Dict[str, Any]:
    try:
        initial_data = playlist.get_playlist_info(limit=343)
        playlist_v2 = initial_data['data']['playlistV2']
        
        track_list = []
        total_duration_ms = 0
        
        async with aiohttp.ClientSession() as session:
            for page in playlist.paginate_playlist():
                track_ids = [
                    item['itemV2']['data']['uri'].split(':')[-1] 
                    for item in page['items']
                ]
                track_metadata = await fetch_track_metadata_batch(session, track_ids, cover_size)
                
                for i, metadata in enumerate(track_metadata):
                    if isinstance(metadata, Exception):
                        continue
                    
                    duration_ms = int(metadata['duration'].split(':')[0]) * 60000 + \
                                int(metadata['duration'].split(':')[1]) * 1000
                    total_duration_ms += duration_ms
                    
                    track_list.append({
                        'id': track_ids[i],
                        'title': metadata['title'],
                        'artist': metadata['artist'],
                        'album': metadata['album'],
                        'cover': metadata['cover'],
                        'duration': metadata['duration'],
                        'release': metadata['release'],
                        'isrc': metadata['isrc']
                    })
        
        playlist_cover = playlist_v2['images']['items'][0]['sources'][0]['url']
        
        return {
            'playlist_info': {
                'cover': modify_cover_size(playlist_cover, cover_size),
                'title': clean_text(playlist_v2['name']),
                'owner': clean_text(playlist_v2['ownerV2']['data']['name']),
                'total': playlist_v2['content']['totalCount'],
                'duration': format_duration(total_duration_ms)
            },
            'track_list': track_list
        }
    except Exception as e:
        raise ValueError(f"Failed to parse playlist data: {str(e)}")

async def get_track_metadata(track_input: str, cover_size: str = "300") -> Dict[str, Any]:
    try:
        track_id = extract_spotify_id(track_input)
        song = Song()
        return await extract_track_metadata(song, track_id, cover_size)
    except Exception as e:
        raise ValueError(f"Error getting track metadata: {str(e)}")

async def get_album_metadata(album_input: str, cover_size: str = "300") -> Dict[str, Any]:
    try:
        album_id = extract_spotify_id(album_input)
        album = PublicAlbum(album_id)
        return await extract_album_metadata(album, cover_size)
    except Exception as e:
        raise ValueError(f"Error getting album metadata: {str(e)}")

async def get_playlist_metadata(playlist_input: str, cover_size: str = "300") -> Dict[str, Any]:
    try:
        playlist_id = extract_spotify_id(playlist_input)
        playlist = PublicPlaylist(playlist_id)
        return await extract_playlist_metadata(playlist, cover_size)
    except Exception as e:
        raise ValueError(f"Error getting playlist metadata: {str(e)}")

async def main():
    try:
        track_url = "https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe"
        track_data_small = await get_track_metadata(track_url, "640")
        print("Track Data (300px):", track_data_small)

        album_url = "https://open.spotify.com/album/3gFT1ZUBt4wfek4hm0VsBV"
        album_data = await get_album_metadata(album_url, "640")
        print("Album Data:", album_data)

        playlist_url = "https://open.spotify.com/playlist/5Qvz8wZIRYbEUUFoPueKI5"
        playlist_data = await get_playlist_metadata(playlist_url, "640")
        print("Playlist Data:", playlist_data)
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")

if __name__ == '__main__':
    asyncio.run(main())
