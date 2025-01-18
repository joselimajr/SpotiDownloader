import sys
import os
import time
from dataclasses import dataclass
from datetime import datetime
import requests
import re
import asyncio

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QListWidget, QMessageBox, QTextEdit, QTabWidget,
    QAbstractItemView, QSpacerItem, QSizePolicy, QProgressBar,
    QButtonGroup, QRadioButton, QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize, QTimer, QTime, QSettings
from PyQt6.QtGui import QIcon, QTextCursor, QDesktopServices, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from mutagen.mp3 import MP3
from mutagen.id3 import APIC, TIT2, TPE1, TALB, TDRC, TSRC, COMM, error

from GetMetadata import get_track_metadata, get_album_metadata, get_playlist_metadata, extract_spotify_id
from GetToken import main as get_token

HEADERS = {
    'Host': 'api.spotifydown.com',
    'Referer': 'https://spotifydown.com/',
    'Origin': 'https://spotifydown.com',
}

def format_artists(artists_string):
    artists = [a.strip() for a in re.split(r'[,&]', artists_string) if a.strip()]
    return ", ".join(artists)

@dataclass
class Track:
    id: str
    title: str
    artists: str
    album: str
    cover_url: str
    track_number: int
    duration: str
    release_date: str
    isrc: str 

def handle_error_response(response):
    if isinstance(response, str):
        return response
        
    if response is None:
        return "Error: No response received"
        
    if not hasattr(response, 'status_code'):
        return "Error: Invalid response format"
    
    if response.status_code == 400:
        try:
            error_data = response.json()
            error_msg = error_data.get('error', '').lower()
            if 'header' in error_msg:
                return "Error: Invalid request. Please try downloading directly from spotifydown.com or try again later"
        except:
            pass
        return "Error: Invalid request. Please try again"
    elif response.status_code == 403:
        return "Error: Token has expired. Please update your token"
    elif response.status_code == 429:
        return "Error: Too many requests. Please try again later"
    elif response.status_code == 500:
        return "Error: Server is currently unavailable. Please try again later"
    elif response.status_code != 200:
        return f"Error: Unexpected error occurred (Status: {response.status_code})"
        
    try:
        data = response.json()
        if not data.get('success'):
            error_msg = data.get('error', 'Unknown error').lower()
            
            if 'header' in error_msg:
                return "Error: Invalid request. Please try downloading directly from spotifydown.com or try again later"
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                return "Error: Connection timed out. Please try again"
            elif 'token' in error_msg:
                return "Error: Token has expired. Please update your token"
            elif 'rate limit' in error_msg:
                return "Error: Too many requests. Please try again later"
            elif 'connection' in error_msg:
                return "Error: Connection failed. Please check your internet"
            else:
                return f"Error: {error_msg.capitalize()}"
                
        return None
    except Exception as e:
        if 'timeout' in str(e).lower():
            return "Error: Connection timed out. Please try again"
        elif 'connection' in str(e).lower():
            return "Error: Connection failed. Please check your internet"
        return f"Error: {str(e)}"

def sanitize_filename(name: str) -> str:
    invalid_chars = '<>:"/\\?*|'
    trans_table = str.maketrans(invalid_chars, '_' * len(invalid_chars))
    
    name = ''.join(char for char in name if ord(char) < 128 and char.isprintable())
    
    return ' '.join(name.translate(trans_table).split())

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str, list)
    progress = pyqtSignal(str, int)
    detailed_progress = pyqtSignal(str, float, float, float)
    token_error = pyqtSignal()
    
    def __init__(self, tracks, outpath, token, is_single_track=False, is_album=False, is_playlist=False, 
                 album_or_playlist_name='', artist_title_radio=False, album_folder_check=False, 
                 max_retries=3):
        super().__init__()
        self.tracks = tracks
        self.outpath = outpath
        self.token = token
        self.is_single_track = is_single_track
        self.is_album = is_album
        self.is_playlist = is_playlist
        self.album_or_playlist_name = album_or_playlist_name
        self.artist_title_radio = artist_title_radio
        self.album_folder_check = album_folder_check
        self.is_paused = False
        self.is_stopped = False
        self.failed_tracks = []
        self.skipped_tracks = []
        self.MAX_RETRIES = max_retries
        self.TIMEOUT = 5
        self.last_emitted_progress = 0
        self.total_processed = 0
        self.current_download_start = 0
        self.last_downloaded = 0
        self.last_speed_update = 0
        self.remaining_tracks = []

    def validate_token(self):
        try:
            if not self.tracks:
                return True
                
            response = requests.get(
                f"https://api.spotifydown.com/download/{self.tracks[0].id}?token={self.token}",
                headers=HEADERS,
                timeout=self.TIMEOUT
            )
            return not (response.status_code == 403 or 'token' in response.text.lower())
        except Exception as e:
            return '403' not in str(e) and 'token' not in str(e).lower()

    def calculate_progress(self, track_index, sub_progress):
        total_remaining = len(self.remaining_tracks)
        if total_remaining == 0:
            return 100
        progress = ((track_index * 100) + sub_progress) / total_remaining
        new_progress = int(progress)
        
        if new_progress > self.last_emitted_progress:
            self.last_emitted_progress = new_progress
            return new_progress
        return self.last_emitted_progress

    def get_track_filepath(self, track):
        if self.artist_title_radio:
            filename = f"{track.artists} - {track.title}.mp3"
        else:
            filename = f"{track.title} - {track.artists}.mp3"
        filename = sanitize_filename(filename)
        
        if self.album_folder_check and self.is_playlist and track.album:
            album_folder = sanitize_filename(track.album)
            album_path = os.path.join(self.outpath, album_folder)
            os.makedirs(album_path, exist_ok=True)
            return os.path.join(album_path, filename)
        
        return os.path.join(self.outpath, filename)

    def scan_existing_files(self):
        existing_files = []
        for idx, track in enumerate(self.tracks):
            filepath = self.get_track_filepath(track)
            if os.path.exists(filepath):
                existing_files.append(track)
                self.skipped_tracks.append((idx + 1, track.title, track.artists))
        return existing_files

    def simplify_error_message(self, error):
        error_str = str(error).lower()
        
        if 'timeout' in error_str or 'timed out' in error_str:
            return "Connection timed out"
        if 'missing required request header' in error_str or 'header' in error_str:
            return "Invalid request. Please try downloading directly from spotifydown.com or try again later"
        if 'status code: 400' in error_str:
            return "Invalid request"
        if 'status code: 403' in error_str:
            return "Token expired"
        if 'status code: 429' in error_str:
            return "Too many requests"
        if 'status code: 500' in error_str:
            return "Server error"
        if 'connectionerror' in error_str:
            return "Connection failed"
            
        return str(error)

    def handle_download_error(self, error, track):
        simplified_error = self.simplify_error_message(error)
        
        all_invalid_headers = (len(self.failed_tracks) > 0 and 
            all('header' in err[2].lower() or 'invalid request' in err[2].lower() 
                for err in self.failed_tracks))
        
        if ('header' in simplified_error.lower() or 'invalid request' in simplified_error.lower()) and all_invalid_headers:
            return "Invalid request. Please try downloading directly from spotifydown.com or try again later"
        
        report_error = simplified_error
        
        if isinstance(error, requests.exceptions.Timeout):
            return "Connection timed out"
        elif isinstance(error, requests.exceptions.ConnectionError):
            return "Connection failed"
        elif isinstance(error, requests.exceptions.RequestException):
            if hasattr(error, 'response'):
                error_response = handle_error_response(error.response)
                if error_response and '403' not in error_response:
                    return f"Download failed: {error_response}"
        
        if self.is_single_track and '403' not in report_error:
            return f"Download failed: {report_error}"
        
        return report_error

    def format_size(self, size_bytes):
        units = ['B', 'KB', 'MB', 'GB']
        index = 0
        while size_bytes >= 1024 and index < len(units) - 1:
            size_bytes /= 1024
            index += 1
        return f"{size_bytes:.2f}{units[index]}"

    def format_speed(self, speed_bytes):
        speed_bits = speed_bytes * 8
        
        if speed_bits >= 1024 * 1024:
            speed_mbps = speed_bits / (1024 * 1024)
            return f"{speed_mbps:.2f}Mbps"
        else:
            speed_kbps = speed_bits / 1024
            return f"{speed_kbps:.2f}Kbps"
    
    def get_file_size(self, url):
        response = requests.head(url, timeout=self.TIMEOUT)
        return int(response.headers.get('content-length', 0))

    def download_with_progress(self, url, expected_size):
        response = requests.get(url, stream=True, timeout=self.TIMEOUT)
        response.raise_for_status()
        
        self.current_download_start = time.time()
        self.last_downloaded = 0
        self.last_speed_update = self.current_download_start
        
        downloaded_size = 0
        chunk_size = 8192
        chunks = []

        for chunk in response.iter_content(chunk_size=chunk_size):
            if self.is_stopped:
                return None
                
            while self.is_paused:
                if self.is_stopped:
                    return None
                self.msleep(100)
                self.current_download_start = time.time()
                
            if chunk:
                chunks.append(chunk)
                downloaded_size += len(chunk)
                current_time = time.time()
                time_diff = current_time - self.last_speed_update
                
                if time_diff >= 0.5 or downloaded_size >= expected_size:
                    speed = (downloaded_size - self.last_downloaded) / time_diff
                    self.detailed_progress.emit(
                        f"Downloading",
                        downloaded_size,
                        expected_size,
                        speed
                    )
                    self.last_downloaded = downloaded_size
                    self.last_speed_update = current_time

        if downloaded_size > self.last_downloaded:
            self.detailed_progress.emit(
                f"Downloading",
                downloaded_size,
                expected_size,
                0
            )

        return b''.join(chunks)

    def run(self):
        try:
            if not self.validate_token():
                self.token_error.emit()
                return

            total_tracks = len(self.tracks)
            failed_tracks = 0
            self.last_emitted_progress = 0
            self.total_processed = 0
            download_attempted = False

            existing_files = self.scan_existing_files()
            if existing_files:
                skip_message = "Skipping existing files:"
                for idx, title, artists in self.skipped_tracks:
                    skip_message += f"\n{idx}. {title} - {artists}"
                self.progress.emit(skip_message, 0)
                self.msleep(1000)
            
            self.remaining_tracks = [t for t in self.tracks if t not in existing_files]
            remaining_count = len(self.remaining_tracks)
            
            if remaining_count == 0:
                self.progress.emit("All files already exist! Nothing to download.", 100)
                self.finished.emit(True, "All files already exist", [])
                return
            
            self.progress.emit(f"Starting download of {remaining_count} files out of {total_tracks} total tracks", 0)
            self.msleep(1000)

            for i, track in enumerate(self.remaining_tracks):
                if self.is_stopped:
                    return

                filepath = self.get_track_filepath(track)
                download_attempted = True
                retry_count = 0
                success = False
                last_progress = 0

                while not success and retry_count <= self.MAX_RETRIES:
                    try:
                        while self.is_paused:
                            if self.is_stopped:
                                return
                            self.msleep(100)

                        if retry_count > 0:
                            self.progress.emit(
                                f"Retry attempt {retry_count} of {self.MAX_RETRIES} for: {track.title}", 
                                self.calculate_progress(i, last_progress)
                            )
                            self.msleep(1000)
                        else:
                            self.progress.emit(
                                f"Starting download ({i+1}/{remaining_count}): {track.title} - {track.artists}", 
                                self.calculate_progress(i, last_progress)
                            )
                            self.msleep(500)
                        
                        self.progress.emit("Getting download link...", self.calculate_progress(i, 25))
                        last_progress = 25
                        
                        response = requests.get(
                            f"https://api.spotifydown.com/download/{track.id}?token={self.token}", 
                            headers=HEADERS,
                            timeout=self.TIMEOUT
                        )
                        
                        error_msg = handle_error_response(response)
                        if error_msg:
                            raise Exception(error_msg)

                        data = response.json()
                        
                        expected_size = self.get_file_size(data['link'])
                        
                        self.progress.emit(
                            f"Downloading track {i+1}/{total_tracks}: {track.title}",
                            self.calculate_progress(i, 50)
                        )
                        last_progress = 50
                        
                        audio_content = self.download_with_progress(data['link'], expected_size)
                        if audio_content is None:
                            return
                            
                        self.progress.emit("Saving file...", self.calculate_progress(i, 75))
                        last_progress = 75
                        with open(filepath, 'wb') as f:
                            f.write(audio_content)
                        
                        self.progress.emit(f"Adding metadata...", self.calculate_progress(i, 90))
                        last_progress = 90
                        self.add_metadata(filepath, track)

                        progress = ((i + 1) * 100) // remaining_count
                        self.progress.emit(
                            f"Successfully downloaded: {track.title}", 
                            progress
                        )
                        success = True
                        self.total_processed += 1

                    except Exception as e:
                        retry_count += 1
                        error_msg = self.handle_download_error(e, track)
                        
                        if '403' in str(e) or 'token' in str(e).lower():
                            self.token_error.emit()
                            return
                            
                        if retry_count > self.MAX_RETRIES:
                            failed_tracks += 1
                            self.failed_tracks.append((track.title, track.artists, error_msg))
                            self.total_processed += 1
                            
                            self.progress.emit(
                                f"Failed to download: {track.title}", 
                                self.calculate_progress(i+1, 100)
                            )
                            
                            if download_attempted and failed_tracks == total_tracks - len(self.skipped_tracks):
                                self.progress.emit("All downloads failed", 100)
                                self.finished.emit(False, error_msg, self.failed_tracks)
                                return
                            break
                        else:
                            self.progress.emit(
                                f"Error: {error_msg}. Retry attempt {retry_count} of {self.MAX_RETRIES}...", 
                                self.calculate_progress(i, last_progress)
                            )
                            self.msleep(1000)
                        pass

            if not self.is_stopped:
                self.progress.emit("Finalizing...", 100)
                if failed_tracks == 0:
                    success_message = "Download completed successfully!"
                    self.finished.emit(True, success_message, self.failed_tracks)
                else:
                    partial_success_message = f"Download completed with {failed_tracks} failed tracks"
                    self.finished.emit(True, partial_success_message, self.failed_tracks)

        except Exception as e:
            if '403' in str(e) or 'token' in str(e).lower():
                self.token_error.emit()
            else:
                self.progress.emit("Error occurred", 100)
                self.finished.emit(False, self.simplify_error_message(e), self.failed_tracks)
            pass
        
    def add_metadata(self, filepath: str, track: Track):
        try:
            cover_response = requests.get(track.cover_url, timeout=self.TIMEOUT)
            if cover_response.status_code != 200:
                return
            cover_data = cover_response.content

            try:
                audio = MP3(filepath)
                if audio.tags is None:
                    audio.add_tags()
            except error:
                audio = MP3(filepath)
                audio.add_tags()

            formatted_artists = format_artists(track.artists)
            
            audio.tags.add(TIT2(encoding=3, text=track.title))
            audio.tags.add(TPE1(encoding=3, text=formatted_artists))
            audio.tags.add(TALB(encoding=3, text=track.album))
            
            if track.release_date:
                audio.tags.add(TDRC(encoding=3, text=track.release_date))
                
            if track.isrc:
                audio.tags.add(TSRC(encoding=3, text=track.isrc))
                
            audio.tags.add(COMM(
                encoding=3,
                lang='eng',
                desc='',
                text='github.com/afkarxyz/SpotifyDown-GUI'
            ))
            
            audio.tags.add(
                APIC(
                    encoding=1,
                    mime='image/jpeg',
                    type=3,
                    desc='',
                    data=cover_data
                )
            )

            audio.save()
        except Exception as e:
            print(f"Error adding metadata: {str(e)}")

    def pause(self):
        self.is_paused = True
        self.progress.emit("Download process paused.", 0)

    def resume(self):
        self.is_paused = False
        self.progress.emit("Download process resumed.", 0)

    def stop(self): 
        self.is_stopped = True
        self.is_paused = False

class SpotifyDownGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('SpotifyDown', 'GUI')
        self.tracks = []
        self.album_or_playlist_name = ''
        self.reset_state()
        
        self.elapsed_time = QTime(0, 0, 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        
        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self.on_cover_loaded)
        
        self.token_input = None
        self.output_dir = None
        self.artist_title_radio = None
        self.album_folder_check = None
        self.retry_dropdown = None
        
        self.last_token = ''
        self.last_output_path = os.path.expanduser("~\\Music")
        self.filename_format = 'title_artist'
        self.use_album_folder = False
        self.retry_count = 3
        
        self.load_config()
        
        self.initUI()
        
        if hasattr(self, 'last_token') and self.token_input:
            self.token_input.setText(self.last_token)

    def reset_state(self):
        self.tracks.clear()
        self.is_album = self.is_playlist = self.is_single_track = False
        self.album_or_playlist_name = ''

    def reset_ui(self):
        if hasattr(self, 'search_input'):
            self.search_input.clear()
            self.search_input.hide()
        if hasattr(self, 'original_items'):
            delattr(self, 'original_items')
        self.track_list.clear()
        self.track_list.hide()
        self.log_output.clear()
        self.log_output.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')
        self.reset_info_widget()
        self.spotify_url.clear()
        self.hide_track_buttons()

    def get_base_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def load_config(self):
        self.last_token = self.settings.value('token', '')
        self.last_output_path = self.settings.value('output_path', os.path.expanduser("~\\Music"))
        self.filename_format = self.settings.value('filename_format', 'title_artist')
        self.use_album_folder = self.settings.value('use_album_folder', False, type=bool)
        self.retry_count = self.settings.value('retry_count', 3, type=int)

    def save_config(self):
        if all(hasattr(self, attr) and getattr(self, attr) is not None 
            for attr in ['output_dir', 'artist_title_radio', 'album_folder_check', 'retry_dropdown']):
            self.settings.setValue('output_path', self.output_dir.text().strip())
            self.settings.setValue('filename_format', 'artist_title' if self.artist_title_radio.isChecked() else 'title_artist')
            self.settings.setValue('use_album_folder', self.album_folder_check.isChecked())
            self.settings.setValue('retry_count', int(self.retry_dropdown.currentText()))
            self.settings.sync()

    def save_format_settings(self):
        self.save_config()
        QMessageBox.information(self, "Success", "Format settings saved successfully!")

    def initUI(self):
        self.setWindowTitle('SpotifyDown')
        self.setFixedWidth(650)
        self.setFixedHeight(410)
        
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.main_layout = QVBoxLayout()
        
        self.setup_spotify_section()
        self.setup_token_section()
        self.setup_tabs()
        
        self.setLayout(self.main_layout)

    def setup_spotify_section(self):
        spotify_layout = QHBoxLayout()
        spotify_label = QLabel('Spotify URL:')
        spotify_label.setFixedWidth(100)
        
        self.spotify_url = QLineEdit()
        self.spotify_url.setPlaceholderText("Please enter the Spotify URL")
        self.spotify_url.setClearButtonEnabled(True)
        
        self.paste_btn = QPushButton()
        self.fetch_btn = QPushButton('Fetch')
        
        self.setup_button(self.paste_btn, "paste.svg", "Paste URL", self.paste_url)
        
        self.paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.fetch_btn.clicked.connect(self.fetch_tracks)
        
        spotify_layout.addWidget(spotify_label)
        spotify_layout.addWidget(self.spotify_url)
        spotify_layout.addWidget(self.paste_btn)
        spotify_layout.addWidget(self.fetch_btn)
        self.main_layout.addLayout(spotify_layout)

    def setup_token_section(self):
        token_layout = QHBoxLayout()
        token_label = QLabel('Token:')
        token_label.setFixedWidth(100)
        
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Please enter the Token")
        self.token_input.setClearButtonEnabled(True)
        self.token_input.textChanged.connect(self.handle_token_clear)
        
        self.token_save_icon_btn = QPushButton()
        self.token_save_btn = QPushButton('Get Token')
        
        self.setup_button(self.token_save_icon_btn, "save.svg", "Save Token", self.save_token)
        
        self.token_save_icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.token_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.token_save_btn.clicked.connect(self.get_token)
        
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_input)
        token_layout.addWidget(self.token_save_icon_btn)
        token_layout.addWidget(self.token_save_btn)
        self.main_layout.addLayout(token_layout)

    async def _fetch_token(self):
        try:
            token = await get_token()
            if token:
                self.token_input.setText(token)
                QMessageBox.information(self, "Success", "Token fetched successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to fetch token")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch token: {str(e)}")

    def get_token(self):
        asyncio.run(self._fetch_token())
        
    def handle_token_clear(self, text):
        if not text:
            self.settings.remove('token')
            self.settings.sync()
            self.last_token = ''
            
    def setup_output_section(self):
        output_layout = QHBoxLayout()
        output_label = QLabel('Output Directory:')
        output_label.setFixedWidth(100)
        
        self.output_dir = QLineEdit()
        self.output_dir.setText(self.last_output_path)
        self.output_dir.textChanged.connect(self.save_config)
        
        self.open_dir_btn = QPushButton()
        self.output_browse = QPushButton('Browse')
        
        self.setup_button(self.open_dir_btn, "folder.svg", "Open output directory", self.open_output_dir)
        
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_browse.clicked.connect(self.browse_output)
        
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_dir)
        output_layout.addWidget(self.open_dir_btn)
        output_layout.addWidget(self.output_browse)
        
        self.main_layout.addLayout(output_layout)
    
    def setup_tabs(self):
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.setup_tracks_tab()
        self.setup_process_tab()
        self.setup_settings_tab()
        self.setup_about_tab()

    def filter_tracks(self):
        search_text = self.search_input.text().lower()
        
        if not hasattr(self, 'original_items'):
            self.original_items = [self.track_list.item(i).text() 
                                for i in range(self.track_list.count())]
        
        self.track_list.clear()
        
        for item_text in self.original_items:
            if search_text in item_text.lower():
                self.track_list.addItem(item_text)

    def setup_info_widget(self):
        self.info_widget = QWidget()
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(9, 9, 9, 9)
        
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(80, 80)
        self.cover_label.setScaledContents(True)
        info_layout.addWidget(self.cover_label)

        right_side_layout = QVBoxLayout()
        right_side_layout.setSpacing(5)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.title_label.setWordWrap(True)
        right_side_layout.addWidget(self.title_label)
        
        self.artists_label = QLabel()
        self.artists_label.setWordWrap(True)
        
        self.release_date_label = QLabel()
        self.release_date_label.setWordWrap(True)
        
        self.type_label = QLabel()
        self.type_label.setStyleSheet("font-size: 12px;")
        
        right_side_layout.addWidget(self.artists_label)
        right_side_layout.addWidget(self.release_date_label)
        right_side_layout.addWidget(self.type_label)
        right_side_layout.addStretch()

        info_layout.addLayout(right_side_layout, 1)
        self.info_widget.setLayout(info_layout)
        self.info_widget.setFixedHeight(100)
        self.info_widget.hide()
        
        self.search_widget = QWidget()
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(9, 0, 9, 5)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tracks...")
        self.search_input.textChanged.connect(self.filter_tracks)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.hide()
        
        search_layout.addWidget(self.search_input)
        self.search_widget.setLayout(search_layout)

    def setup_tracks_tab(self):
        tracks_tab = QWidget()
        tracks_layout = QVBoxLayout()
        tracks_layout.setSpacing(5)

        self.info_container = QWidget()
        info_container_layout = QVBoxLayout()
        info_container_layout.setSpacing(0)
        info_container_layout.setContentsMargins(0, 0, 0, 0)

        self.setup_info_widget()
        info_container_layout.addWidget(self.info_widget)
        info_container_layout.addWidget(self.search_widget)
        
        self.info_container.setLayout(info_container_layout)
        
        tracks_layout.addStretch()
        tracks_layout.addWidget(self.info_container)
        
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_list.hide()
        tracks_layout.addWidget(self.track_list)
        
        self.setup_track_buttons()
        tracks_layout.addLayout(self.btn_layout)
        
        tracks_layout.addStretch()
        
        tracks_layout.setContentsMargins(9, 9, 9, 9)
        tracks_tab.setLayout(tracks_layout)
        self.tab_widget.addTab(tracks_tab, "Dashboard")
        self.hide_track_buttons()

    def setup_track_buttons(self):
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setContentsMargins(0, 5, 0, 0)
        
        self.download_selected_btn = QPushButton('Download Selected')
        self.download_all_btn = QPushButton('Download All')
        self.remove_btn = QPushButton('Remove Selected')
        self.clear_btn = QPushButton('Clear')
        
        self.original_button_width = 150
        
        for btn in [self.download_selected_btn, self.download_all_btn, self.remove_btn, self.clear_btn]:
            btn.setFixedWidth(self.original_button_width)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.download_selected_btn.clicked.connect(self.download_selected)
        self.download_all_btn.clicked.connect(self.download_all)
        self.remove_btn.clicked.connect(self.remove_selected_tracks)
        self.clear_btn.clicked.connect(self.clear_tracks)
        
        self.btn_layout.addStretch()
        for btn in [self.download_selected_btn, self.download_all_btn, self.remove_btn, self.clear_btn]:
            self.btn_layout.addWidget(btn)
        self.btn_layout.addStretch()

    def setup_process_tab(self):
        self.process_tab = QWidget()
        process_layout = QVBoxLayout()
        process_layout.setSpacing(5)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.hide()
        process_layout.addWidget(self.log_output)
        
        progress_time_layout = QVBoxLayout()
        progress_time_layout.setSpacing(2)
        
        self.progress_bar = QProgressBar()
        progress_time_layout.addWidget(self.progress_bar)
        
        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_time_layout.addWidget(self.time_label)
        
        process_layout.addLayout(progress_time_layout)
        
        control_layout = QHBoxLayout()
        self.stop_btn = QPushButton('Stop')
        self.pause_resume_btn = QPushButton('Pause')
        
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_resume_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.stop_btn.clicked.connect(self.stop_download)
        self.pause_resume_btn.clicked.connect(self.toggle_pause_resume)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.pause_resume_btn)
        
        process_layout.addLayout(control_layout)
        
        self.process_tab.setLayout(process_layout)
        
        self.tab_widget.addTab(self.process_tab, "Process")
        
        self.progress_bar.hide()
        self.time_label.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()

    def setup_settings_tab(self):
        settings_tab = QWidget()
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(10)
        settings_layout.setContentsMargins(9, 9, 9, 9)

        output_group = QWidget()
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(5)
        
        output_label = QLabel('Output Directory')
        output_label.setStyleSheet("font-weight: bold; color: palette(text);")
        output_layout.addWidget(output_label)
        
        output_dir_layout = QHBoxLayout()
        self.output_dir = QLineEdit()
        self.output_dir.setText(self.last_output_path)
        self.output_dir.textChanged.connect(self.save_config)
        
        self.open_dir_btn = QPushButton()
        self.output_browse = QPushButton('Browse')
        
        self.setup_button(self.open_dir_btn, "folder.svg", "Open output directory", self.open_output_dir)
        
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_browse.clicked.connect(self.browse_output)
        
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir)
        output_dir_layout.addWidget(self.open_dir_btn)
        output_dir_layout.addWidget(self.output_browse)
        output_layout.addLayout(output_dir_layout)
        
        settings_layout.addWidget(output_group)
        
        download_group = QWidget()
        download_layout = QVBoxLayout(download_group)
        download_layout.setSpacing(5)
        
        download_label = QLabel('Download Settings')
        download_label.setStyleSheet("font-weight: bold; color: palette(text);")
        download_layout.addWidget(download_label)
        
        retry_layout = QHBoxLayout()
        self.retry_label = QLabel('Maximum Retry Attempts:')
        self.retry_label.setStyleSheet("color: palette(text);")
        self.retry_dropdown = QComboBox()
        for i in range(0, 11):
            self.retry_dropdown.addItem(str(i))
        self.retry_dropdown.setCurrentText(str(self.retry_count))
        self.retry_dropdown.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_dropdown.setFixedWidth(75)
        self.retry_dropdown.currentTextChanged.connect(self.save_config)
        
        retry_layout.addWidget(self.retry_label)
        retry_layout.addWidget(self.retry_dropdown)
        retry_layout.addStretch()
        download_layout.addLayout(retry_layout)
        
        settings_layout.addWidget(download_group)
        
        file_group = QWidget()
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(5)
        
        file_label = QLabel('File Settings')
        file_label.setStyleSheet("font-weight: bold; color: palette(text);")
        file_layout.addWidget(file_label)
        
        format_layout = QHBoxLayout()
        format_label = QLabel('Filename Format:')
        format_label.setStyleSheet("color: palette(text);")
        
        self.format_group = QButtonGroup(self)
        self.title_artist_radio = QRadioButton('Title - Artist')
        self.title_artist_radio.setStyleSheet("color: palette(text);")
        self.title_artist_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_artist_radio.toggled.connect(self.save_config)
        
        self.artist_title_radio = QRadioButton('Artist - Title')
        self.artist_title_radio.setStyleSheet("color: palette(text);")
        self.artist_title_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist_title_radio.toggled.connect(self.save_config)
        
        if self.filename_format == "artist_title":
            self.artist_title_radio.setChecked(True)
        else:
            self.title_artist_radio.setChecked(True)
        
        self.format_group.addButton(self.title_artist_radio)
        self.format_group.addButton(self.artist_title_radio)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.title_artist_radio)
        format_layout.addWidget(self.artist_title_radio)
        format_layout.addStretch()
        file_layout.addLayout(format_layout)
        
        folder_label = QLabel('Folder Organization:')
        folder_label.setStyleSheet("color: palette(text);")
        file_layout.addWidget(folder_label)
        
        self.album_folder_check = QCheckBox('Create Album Subfolders for Playlist Downloads')
        self.album_folder_check.setStyleSheet("color: palette(text);")
        self.album_folder_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.album_folder_check.setChecked(self.use_album_folder)
        self.album_folder_check.toggled.connect(self.save_config)
        file_layout.addWidget(self.album_folder_check)
        
        settings_layout.addWidget(file_group)
        
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        
        self.reset_default_btn = QPushButton('Reset Default')
        self.reset_default_btn.setFixedWidth(120)
        self.reset_default_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_default_btn.clicked.connect(self.reset_default_settings)
        reset_layout.addWidget(self.reset_default_btn)
        reset_layout.addStretch()
        settings_layout.addLayout(reset_layout)
        
        settings_layout.addStretch()
        settings_tab.setLayout(settings_layout)
        self.tab_widget.addTab(settings_tab, "Settings")

    def reset_default_settings(self):
        default_music_path = os.path.expanduser("~\\Music")
        self.output_dir.setText(default_music_path)
        self.title_artist_radio.setChecked(True)
        self.album_folder_check.setChecked(False)
        self.retry_dropdown.setCurrentText('3')
        
        self.settings.setValue('output_path', default_music_path)
        self.settings.setValue('filename_format', 'title_artist')
        self.settings.setValue('use_album_folder', False)
        self.settings.setValue('retry_count', 3)
        self.settings.sync()
        
        QMessageBox.information(self, "Success", "Settings have been reset to default values!")
    
    def setup_about_tab(self):
        about_tab = QWidget()
        about_layout = QVBoxLayout()
        about_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.setSpacing(3)

        title_label = QLabel("SpotifyDown")
        title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2DC261;
        """)
        about_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(
            "SpotifyDown is a GUI tool for downloading Spotify tracks, albums, and playlists\n"
            "using the API provided by spotifydown.com"
        )
        desc_label.setStyleSheet("color: palette(text); font-size: 13px; margin: 10px;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(desc_label)

        sections = [
            ("Check for Updates", "https://github.com/afkarxyz/SpotifyDown-GUI/releases"),
            ("Report an Issue", "https://github.com/afkarxyz/SpotifyDown-GUI/issues"),
            ("SpotifyDown Site", "http://spotifydown.com/")
        ]

        for title, url in sections:
            section_widget = QWidget()
            section_layout = QVBoxLayout(section_widget)
            section_layout.setSpacing(3)
            section_layout.setContentsMargins(0, 0, 0, 0)

            label = QLabel(title)
            label.setStyleSheet("color: palette(text); font-weight: bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            section_layout.addWidget(label)

            button = QPushButton("Click Here!")
            button.setFixedWidth(150)
            button.setStyleSheet("""
                QPushButton {
                    background-color: palette(button);
                    color: palette(button-text);
                    border: 1px solid palette(mid);
                    padding: 6px;
                    border-radius: 15px;
                }
                QPushButton:hover {
                    background-color: palette(light);
                }
                QPushButton:pressed {
                    background-color: palette(midlight);
                }
            """)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, url=url: QDesktopServices.openUrl(QUrl(url)))
            section_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

            about_layout.addWidget(section_widget)
            
            if sections.index((title, url)) < len(sections) - 1:
                spacer = QSpacerItem(20, 6, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                about_layout.addItem(spacer)

        footer_label = QLabel("v2.5 | January 2025")
        footer_label.setStyleSheet("font-size: 12px; color: palette(text); margin-top: 10px;")
        about_layout.addWidget(footer_label, alignment=Qt.AlignmentFlag.AlignCenter)

        about_tab.setLayout(about_layout)
        self.tab_widget.addTab(about_tab, "About")

    def setup_button(self, button, icon_name, tooltip, callback):
        icon_path = os.path.join(os.path.dirname(__file__), icon_name)
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(24, 24)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                background-color: palette(light);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: palette(light);
            }
        """)

    def paste_url(self):
        clipboard = QApplication.clipboard()
        self.spotify_url.setText(clipboard.text().strip())

    def paste_token(self):
        clipboard = QApplication.clipboard()
        self.token_input.setText(clipboard.text().strip())

    def browse_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir.setText(directory)

    def save_token(self):
        token = self.token_input.text().strip()
        if token:
            self.settings.setValue('token', token)
            self.settings.sync()
            QMessageBox.information(self, "Success", "Token saved successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Please enter a token before saving.")

    def show_token_error(self):
        QMessageBox.warning(self, "Error", "Token has expired. Please update your token.")
        self.stop_download(is_token_error=True)
        self.download_selected_btn.setEnabled(True)
        self.download_all_btn.setEnabled(True)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')
        self.stop_timer()

    def open_output_dir(self):
        path = self.output_dir.text()
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, 'Warning', 'Output directory does not exist.')

    def fetch_tracks(self):
        url = self.spotify_url.text().strip()
        
        if not url:
            QMessageBox.warning(self, 'Warning', 'Please enter a Spotify URL.')
            return

        self.reset_state()
        self.reset_ui()

        try:
            if '/track/' in url:
                self.fetch_single_track(url)
            else:
                self.fetch_multiple_tracks(url)
            
            self.update_button_states()
            self.tab_widget.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch tracks: {str(e)}")

    def fetch_single_track(self, url):
        track_id = extract_spotify_id(url)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            metadata = loop.run_until_complete(get_track_metadata(track_id))
            loop.close()
            
            formatted_artists = format_artists(metadata['artist'])
            
            self.tracks = [Track(
                id=track_id,
                title=metadata['title'],
                artists=formatted_artists,
                album=metadata['album'],
                cover_url=metadata['cover'],
                track_number=1,
                duration=metadata.get('duration', '0:00'),
                release_date=metadata.get('release', ''),
                isrc=metadata.get('isrc', '')   
            )]
            self.is_single_track = True
            self.is_album = self.is_playlist = False
            self.album_or_playlist_name = f"{self.tracks[0].title} - {self.tracks[0].artists}"
            
            metadata['artist'] = formatted_artists
            
            self.update_display_after_fetch(metadata)
        except Exception as e:
            raise Exception(f"Failed to fetch track metadata: {str(e)}")

    def fetch_multiple_tracks(self, url):
        item_id = extract_spotify_id(url)
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if '/album/' in url:
                metadata = loop.run_until_complete(get_album_metadata(item_id))
                self.is_album = True
                self.is_playlist = False
                self.album_or_playlist_name = metadata['album_info']['title']
                tracks_data = metadata['track_list']
            elif '/playlist/' in url:
                metadata = loop.run_until_complete(get_playlist_metadata(item_id))
                self.is_album = False
                self.is_playlist = True
                self.album_or_playlist_name = metadata['playlist_info']['title']
                tracks_data = metadata['track_list']
            else:
                loop.close()
                raise ValueError("Invalid URL: must be an album or playlist")
                
            loop.close()

            self.tracks = []
            for i, track in enumerate(tracks_data, 1):
                album_name = track['album'] if self.is_playlist else self.album_or_playlist_name
                
                formatted_artists = format_artists(track['artist'])
                
                self.tracks.append(Track(
                    id=track['id'],
                    title=track['title'],
                    artists=formatted_artists,
                    album=album_name,
                    cover_url=track.get('cover', metadata['album_info']['cover'] if self.is_album else metadata['playlist_info']['cover']),
                    track_number=i,
                    duration=track.get('duration', '0:00'),
                    release_date=track.get('release', ''),
                    isrc=track.get('isrc', '')  
                ))

            self.is_single_track = False
            
            if self.is_album and 'artist' in metadata['album_info']:
                metadata['album_info']['artist'] = format_artists(metadata['album_info']['artist'])
                
            self.update_display_after_fetch(metadata['album_info'] if self.is_album else metadata['playlist_info'])
        
        except Exception as e:
            raise Exception(f"Error fetching tracks: {str(e)}")

    def update_display_after_fetch(self, metadata):
        self.track_list.setVisible(not self.is_single_track)
        self.info_container.layout().setContentsMargins(0, 0, 0, 20 if self.is_single_track else 0)
        
        if not self.is_single_track:
            self.track_list.clear()
            self.search_input.show()
            for i, track in enumerate(self.tracks, 1):
                self.track_list.addItem(f"{i}. {track.title} - {track.artists} - {track.duration}")
        else:
            self.search_input.hide()
            self.btn_layout.setContentsMargins(0, 0, 0, 0)
            self.btn_layout.setSpacing(10)
            
            for btn in [self.download_all_btn, self.clear_btn]:
                btn.setFixedWidth(120)
        
        self.update_info_widget(metadata)

    def update_info_widget(self, metadata):
        self.title_label.setText(metadata['title'])

        if self.is_playlist or self.is_album:
            owner = metadata.get('owner', 'Unknown')
            self.artists_label.setText(f"<b>Owner</b> {owner}")
        else:
            artists = format_artists(metadata.get('artist', 'Unknown'))
            artist_count = len(re.split(r'[,&]', metadata.get('artist', '')))
            label = "Artists" if artist_count > 1 else "Artist"
            self.artists_label.setText(f"<b>{label}</b> {artists}")
        
        if metadata.get('release'):
            release_date = datetime.strptime(metadata['release'], "%Y-%m-%d")
            formatted_date = release_date.strftime("%d-%m-%Y")
            self.release_date_label.setText(f"<b>Released</b> {formatted_date}")
            self.release_date_label.show()
        else:
            self.release_date_label.hide()
        
        if self.is_single_track:
            duration = self.tracks[0].duration if self.tracks else "0:00"
            self.type_label.setText(f"<b>Duration</b> {duration}")
        else:
            total_tracks = len(self.tracks)
            track_text = "1 track" if total_tracks == 1 else f"{total_tracks} tracks"
            
            if self.is_album:
                self.type_label.setText(f"<b>Album</b> {track_text}")
            elif self.is_playlist:
                self.type_label.setText(f"<b>Playlist</b> {track_text}")
        
        self.type_label.setStyleSheet("font-size: 12px;")
        
        self.network_manager.get(QNetworkRequest(QUrl(metadata['cover'])))
        
        self.info_widget.show()

    def reset_info_widget(self):
        self.title_label.clear()
        self.artists_label.clear()
        self.type_label.clear()
        self.release_date_label.clear()
        self.cover_label.clear()
        self.info_widget.hide()

    def on_cover_loaded(self, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.cover_label.setPixmap(pixmap)

    def update_button_states(self):
        if self.is_single_track:
            self.download_selected_btn.hide()
            self.remove_btn.hide()
            self.download_all_btn.setText('Download')
            self.clear_btn.setText('Cancel')
            
            self.btn_layout.setContentsMargins(0, 10, 0, 0)
            for btn in [self.download_all_btn, self.clear_btn]:
                btn.setFixedWidth(120)
        else:
            self.download_selected_btn.show()
            self.remove_btn.show()
            self.download_all_btn.setText('Download All')
            self.clear_btn.setText('Clear')
            
            self.btn_layout.setContentsMargins(0, 5, 0, 0)
            for btn in [self.download_selected_btn, self.download_all_btn, self.remove_btn, self.clear_btn]:
                btn.setFixedWidth(self.original_button_width)
        
        self.download_all_btn.show()
        self.clear_btn.show()
        
        self.download_selected_btn.setEnabled(True)
        self.download_all_btn.setEnabled(True)

    def hide_track_buttons(self):
        for btn in [self.download_selected_btn, self.download_all_btn, self.remove_btn, self.clear_btn]:
            btn.hide()

    def download_selected(self):
        if self.is_single_track:
            self.download_all()
        else:
            selected_items = self.track_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(self, 'Warning', 'Please select tracks to download.')
                return
                
            selected_texts = [item.text() for item in selected_items]
            
            original_indices = []
            for selected_text in selected_texts:
                track_num = int(selected_text.split('.')[0])
                original_indices.append(track_num - 1)
                
            self.download_tracks(original_indices)

    def download_all(self):
        if self.is_single_track:
            self.download_tracks([0])
        else:
            self.download_tracks(range(self.track_list.count()))

    def download_tracks(self, indices):
        self.log_output.clear()
        outpath = self.output_dir.text()
        if not os.path.exists(outpath):
            QMessageBox.warning(self, 'Warning', 'Invalid output directory.')
            return

        if not self.token_input.text().strip():
            QMessageBox.warning(self, "Error", "Please enter a token")
            return

        tracks_to_download = self.tracks if self.is_single_track else [self.tracks[i] for i in indices]

        if self.is_album or self.is_playlist:
            folder_name = sanitize_filename(self.album_or_playlist_name)
            outpath = os.path.join(outpath, folder_name)
            os.makedirs(outpath, exist_ok=True)

        try:
            self.start_download_worker(tracks_to_download, outpath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while starting the download: {str(e)}")
            
    def start_download_worker(self, tracks_to_download, outpath):
        self.worker = DownloadWorker(
            tracks_to_download, 
            outpath, 
            self.token_input.text().strip(),
            self.is_single_track, 
            self.is_album, 
            self.is_playlist, 
            self.album_or_playlist_name,
            self.artist_title_radio.isChecked(),
            self.album_folder_check.isChecked(),
            int(self.retry_dropdown.currentText()),
        )
        self.worker.finished.connect(self.on_download_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.detailed_progress.connect(self.update_detailed_progress)
        self.worker.token_error.connect(self.show_token_error)
        self.worker.start()
        self.start_timer()
        self.update_ui_for_download_start()

    def update_detailed_progress(self, message, downloaded_size, total_size, speed):
        if total_size > 0:
            progress = (downloaded_size / total_size) * 100
            downloaded_str = self.worker.format_size(downloaded_size)
            total_str = self.worker.format_size(total_size)
            speed_str = self.worker.format_speed(speed)
            
            progress_message = f"{message} : {progress:.1f}% | {downloaded_str}/{total_str} | Speed: {speed_str}"
            self.log_output.moveCursor(QTextCursor.MoveOperation.End)
            
            cursor = self.log_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            if cursor.selectedText().startswith("Downloading :"):
                cursor.removeSelectedText()
                if not cursor.atStart():
                    cursor.deletePreviousChar()
            self.log_output.append(progress_message)

    def update_ui_for_download_start(self):
        self.download_selected_btn.setEnabled(False)
        self.download_all_btn.setEnabled(False)
        self.stop_btn.show()
        self.pause_resume_btn.show()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.log_output.show()
        
        self.tab_widget.setCurrentWidget(self.process_tab)

    def update_progress(self, message, percentage):
        self.log_output.append(message)
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)
        if percentage > 0:
            self.progress_bar.setValue(percentage)

    def stop_download(self, is_token_error=False):
        if hasattr(self, 'worker'):
            self.worker.stop()
        self.stop_timer()
        if not is_token_error:
            self.on_download_finished(True, "Download stopped by user.", [])
        
    def on_download_finished(self, success, message, failed_tracks):
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')
        self.stop_timer()
        
        self.download_selected_btn.setEnabled(True)
        self.download_all_btn.setEnabled(True)
        
        if success:
            if message != "Download stopped by user.":
                self.log_output.append(f"\nStatus: {message}")
                if failed_tracks:
                    self.log_output.append("\nFailed downloads:")
                    for title, artists, error in failed_tracks:
                        self.log_output.append(f"• {title} - {artists}")
                        self.log_output.append(f"  Error: {error}\n")
                    
                    QMessageBox.warning(self, "Download Status", message)
                else:
                    QMessageBox.information(self, "Download Complete", message)
            elif message == "Download stopped by user.":
                self.log_output.append(f"\nStatus: {message}")
        else:
            self.log_output.append(f"Error: {message}")
            QMessageBox.critical(self, "Error", message)
    
    def toggle_pause_resume(self):
        if hasattr(self, 'worker'):
            if self.worker.is_paused:
                self.worker.resume()
                self.pause_resume_btn.setText('Pause')
                self.timer.start(1000)
            else:
                self.worker.pause()
                self.pause_resume_btn.setText('Resume')

    def remove_selected_tracks(self):
        if not self.is_single_track:
            selected_rows = sorted([self.track_list.row(item) 
                                for item in self.track_list.selectedItems()], 
                                reverse=True)
            
            for row in selected_rows:
                self.tracks.pop(row)
                self.track_list.takeItem(row)
            
            self.track_list.clear()
            self.track_list.addItems([f"{i}. {track.title} - {track.artists} - {track.duration}"
                                    for i, track in enumerate(self.tracks, 1)])

    def clear_tracks(self):
        if hasattr(self, 'original_items'):
            delattr(self, 'original_items')
        self.search_input.clear()
        self.reset_state()
        self.reset_ui()

    def update_timer(self):
        self.elapsed_time = self.elapsed_time.addSecs(1)
        self.time_label.setText(self.elapsed_time.toString("hh:mm:ss"))
    
    def start_timer(self):
        self.elapsed_time = QTime(0, 0, 0)
        self.time_label.setText("00:00:00")
        self.time_label.show()
        self.timer.start(1000)
    
    def stop_timer(self):
        self.timer.stop()
        self.time_label.hide()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SpotifyDownGUI()
    ex.show()
    sys.exit(app.exec())
