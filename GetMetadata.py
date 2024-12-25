import sys
import io
import re
import requests
from typing import Dict, Any
from spotapi import Song, PublicAlbum, PublicPlaylist

if sys.stdout is None or not hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.StringIO()
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def clean_unicode_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return ''.join(char for char in text if ord(char) < 65536)

def format_duration(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"

def safe_unicode_join(artists):
    try:
        artist_names = []
        for artist in artists:
            if isinstance(artist, str):
                cleaned_name = clean_unicode_text(artist)
                artist_names.append(cleaned_name)
            else:
                artist_names.append(str(artist))
        return ' & '.join(artist_names)
    except Exception as e:
        return ' & '.join(str(artist) for artist in artists)

def extract_spotify_id(url: str) -> str:
    match = re.search(r'spotify\.com/(?:track|album|playlist)/([a-zA-Z0-9]{22})', url)
    return match.group(1) if match else url

def extract_track_metadata(song: Song, track_id: str) -> Dict[str, Any]:
    try:
        fab_api_url = f"https://api.fabdl.com/spotify/get?url=https://open.spotify.com/track/{track_id}"
        response = requests.get(fab_api_url)
        response.raise_for_status()
        fab_data = response.json()['result']
        
        track_info = song.get_track_info(track_id)
        track_data = track_info['data']['trackUnion']
        
        duration = format_duration(fab_data['duration_ms'])
        
        return {
            'cover': fab_data['image'],
            'title': clean_unicode_text(fab_data['name']),
            'artist': fab_data['artists'],
            'duration': duration,
            'release': track_data['albumOfTrack']['date']['isoString'].split('T')[0]
        }
    
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch data from fabdl API: {str(e)}")
    except KeyError as e:
        raise ValueError(f"Failed to parse track data: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {str(e)}")

def extract_album_metadata(album: PublicAlbum) -> Dict[str, Any]:
    try:
        initial_data = album.get_album_info(limit=50)
        album_data = initial_data['data']['albumUnion']
        
        track_list = []
        total_duration_ms = 0
        
        for page in album.paginate_album():
            for track in page:
                try:
                    duration_ms = track['track']['duration']['totalMilliseconds']
                    total_duration_ms += duration_ms
                    
                    track_list.append({
                        'id': track['track']['uri'].split(':')[-1],
                        'title': clean_unicode_text(track['track']['name']),
                        'artist': safe_unicode_join(
                            clean_unicode_text(artist['profile']['name']) 
                            for artist in track['track']['artists']['items']
                        ),
                        'duration': format_duration(duration_ms)
                    })
                except UnicodeEncodeError:
                    continue
        
        return {
            'album_info': {
                'cover': album_data['coverArt']['sources'][0]['url'],
                'title': clean_unicode_text(album_data['name']),
                'owner': clean_unicode_text(album_data['artists']['items'][0]['profile']['name']),
                'release': album_data['date']['isoString'].split('T')[0],
                'total': album_data['tracksV2']['totalCount'],
                'duration': format_duration(total_duration_ms)
            },
            'track_list': track_list
        }
    
    except KeyError as e:
        raise ValueError(f"Failed to parse album data: {str(e)}")

def extract_playlist_metadata(playlist: PublicPlaylist) -> Dict[str, Any]:
    try:
        initial_data = playlist.get_playlist_info(limit=343)
        playlist_v2 = initial_data['data']['playlistV2']
        
        track_list = []
        total_duration_ms = 0
        
        for page in playlist.paginate_playlist():
            for item in page['items']:
                try:
                    track_data = item['itemV2']['data']
                    duration_ms = track_data['trackDuration']['totalMilliseconds']
                    total_duration_ms += duration_ms
                    
                    track_list.append({
                        'id': track_data['uri'].split(':')[-1],
                        'title': clean_unicode_text(track_data['name']),
                        'artist': safe_unicode_join(
                            clean_unicode_text(artist['profile']['name']) 
                            for artist in track_data['artists']['items']
                        ),
                        'album': clean_unicode_text(track_data['albumOfTrack']['name']),
                        'cover': track_data['albumOfTrack']['coverArt']['sources'][0]['url'],
                        'duration': format_duration(duration_ms)
                    })
                except (UnicodeEncodeError, KeyError):
                    continue
        
        return {
            'playlist_info': {
                'cover': playlist_v2['images']['items'][0]['sources'][0]['url'],
                'title': clean_unicode_text(playlist_v2['name']),
                'owner': clean_unicode_text(playlist_v2['ownerV2']['data']['name']),
                'total': playlist_v2['content']['totalCount'],
                'duration': format_duration(total_duration_ms)
            },
            'track_list': track_list
        }
    
    except KeyError as e:
        raise ValueError(f"Failed to parse playlist data: {str(e)}")

def get_track_metadata(track_input: str) -> Dict[str, Any]:
    try:
        track_id = extract_spotify_id(track_input)
        song = Song()
        return extract_track_metadata(song, track_id)
    except Exception as e:
        raise ValueError(f"Error getting track metadata: {str(e)}")

def get_album_metadata(album_input: str) -> Dict[str, Any]:
    try:
        album_id = extract_spotify_id(album_input)
        album = PublicAlbum(album_id)
        return extract_album_metadata(album)
    except Exception as e:
        raise ValueError(f"Error getting album metadata: {str(e)}")

def get_playlist_metadata(playlist_input: str) -> Dict[str, Any]:
    try:
        playlist_id = extract_spotify_id(playlist_input)
        playlist = PublicPlaylist(playlist_id)
        return extract_playlist_metadata(playlist)
    except Exception as e:
        raise ValueError(f"Error getting playlist metadata: {str(e)}")

if __name__ == '__main__':
    try:
        track_url = "https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe"
        track_data = get_track_metadata(track_url)
        print("Track Data:", track_data)

        album_url = "https://open.spotify.com/album/4VZ7jhV0wHpoNPCB7Vmiml"
        album_data = get_album_metadata(album_url)
        print("Album Data:", album_data)

        playlist_url = "https://open.spotify.com/playlist/37i9dQZEVXbNG2KDcFcKOF"
        playlist_data = get_playlist_metadata(playlist_url)
        print("Playlist Data:", playlist_data)
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")

    if isinstance(sys.stdout, io.StringIO):
        print(sys.stdout.getvalue())
