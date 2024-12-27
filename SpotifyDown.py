import sys
import os
from dataclasses import dataclass
from datetime import datetime
import json
import requests
import re
import asyncio

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QListWidget, QMessageBox, QTextEdit, QTabWidget,
    QAbstractItemView, QSpacerItem, QSizePolicy, QProgressBar, QHBoxLayout,
    QButtonGroup, QRadioButton, QCheckBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize, QTimer, QTime
from PyQt6.QtGui import QIcon, QTextCursor, QDesktopServices, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from mutagen.mp3 import MP3
from mutagen.id3 import APIC, TIT2, TPE1, TALB, TRCK, error

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

def handle_error_response(response):
    if isinstance(response, str):
        return response
        
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
    name = ''.join(char for char in name if ord(char) < 128 and char.isprintable())
    
    name = re.sub(r'\|', ' ', name)
    
    name = re.sub(r'[<>:"/\\?*]', '_', name)
    
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str, list)
    progress = pyqtSignal(str, int)
    token_error = pyqtSignal()
    
    def __init__(self, tracks, outpath, token, is_single_track=False, is_album=False, is_playlist=False, album_or_playlist_name='', artist_title_radio=False, album_folder_check=False, max_retries=3):
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

    def calculate_progress(self, track_index, sub_progress):
        total_tracks = len(self.tracks)
        track_weight = 100.0 / total_tracks
        base_progress = track_index * track_weight
        current_track_progress = (sub_progress / 100.0) * track_weight
        new_progress = int(base_progress + current_track_progress)
        
        if new_progress < self.last_emitted_progress:
            return self.last_emitted_progress
        
        self.last_emitted_progress = new_progress
        return new_progress

    def get_track_filepath(self, track):
        if self.artist_title_radio:
            filename = f"{track.artists} - {track.title}.mp3"
        else:
            filename = f"{track.title} - {track.artists}.mp3"
        filename = sanitize_filename(filename)
        
        if self.album_folder_check and track.album:
            album_folder = sanitize_filename(track.album)
            album_path = os.path.join(self.outpath, album_folder)
            os.makedirs(album_path, exist_ok=True)
            return os.path.join(album_path, filename)
        
        return os.path.join(self.outpath, filename)

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

    def run(self):
        try:
            total_tracks = len(self.tracks)
            failed_tracks = 0
            self.last_emitted_progress = 0
            download_attempted = False
            first_attempt = True
            
            for i, track in enumerate(self.tracks):
                if self.is_stopped:
                    return

                filepath = self.get_track_filepath(track)
                if os.path.exists(filepath):
                    self.skipped_tracks.append((track.title, track.artists))
                    self.progress.emit(
                        f"Skipped existing file ({i+1}/{total_tracks}): {track.title} - {track.artists}", 
                        self.calculate_progress(i+1, 0)
                    )
                    continue

                download_attempted = True
                retry_count = 0
                success = False
                last_progress = 0

                while retry_count < self.MAX_RETRIES and not success:
                    try:
                        while self.is_paused:
                            if self.is_stopped:
                                return
                            self.msleep(100)

                        self.progress.emit(
                            f"Starting download ({i+1}/{total_tracks}): {track.title} - {track.artists}", 
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
                            if first_attempt and (response.status_code == 403 or "token" in error_msg.lower()):
                                self.token_error.emit()
                                return
                            raise Exception(error_msg)

                        first_attempt = False
                        data = response.json()

                        self.progress.emit("Downloading audio...", self.calculate_progress(i, 50))
                        last_progress = 50
                        audio_response = requests.get(data['link'], timeout=self.TIMEOUT)
                        if audio_response.status_code != 200:
                            error_detail = f"Failed to download audio file - Status code: {audio_response.status_code}"
                            if audio_response.text:
                                error_detail += f" - Response: {audio_response.text}"
                            raise Exception(error_detail)

                        self.progress.emit("Saving file...", self.calculate_progress(i, 75))
                        last_progress = 75
                        with open(filepath, 'wb') as f:
                            f.write(audio_response.content)
                        
                        self.progress.emit(f"Adding metadata...", self.calculate_progress(i, 90))
                        last_progress = 90
                        self.add_metadata(filepath, track)

                        self.progress.emit(
                            f"Successfully downloaded: {track.title}", 
                            self.calculate_progress(i, 100)
                        )
                        success = True
                        self.msleep(500)
                        
                    except Exception as e:
                        retry_count += 1
                        error_msg = self.handle_download_error(e, track)
                        
                        if retry_count < self.MAX_RETRIES:
                            self.progress.emit(
                                f"Error: {error_msg}. Retry attempt {retry_count} of {self.MAX_RETRIES}...", 
                                self.calculate_progress(i, last_progress)
                            )
                            self.msleep(1000)
                        else:
                            failed_tracks += 1
                            self.failed_tracks.append((track.title, track.artists, error_msg))
                            if download_attempted and failed_tracks == total_tracks - len(self.skipped_tracks):
                                if not first_attempt:
                                    self.token_error.emit()
                                return

            if not self.is_stopped:
                if failed_tracks == 0:
                    success_message = "Download completed successfully!"
                    self.finished.emit(True, success_message, self.failed_tracks)
                else:
                    partial_success_message = f"Download completed with {failed_tracks} failed tracks"
                    self.finished.emit(True, partial_success_message, self.failed_tracks)

        except Exception as e:
            self.finished.emit(False, self.simplify_error_message(e), self.failed_tracks)

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
            audio.tags.add(TRCK(encoding=3, text=str(track.track_number)))
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Cover',
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
        self.tracks = []
        self.album_or_playlist_name = ''
        self.reset_state()
        
        self.load_config()
        
        self.elapsed_time = QTime(0, 0, 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        
        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self.on_cover_loaded)
        
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
        self.last_token = ""
        self.last_output_path = os.path.expanduser("~\\Music")
        self.filename_format = "title_artist"
        self.use_album_folder = False
        self.retry_count = 3
        
        cache_path = os.path.join(self.get_base_path(), ".spotifydown")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    self.last_token = data.get("token", self.last_token)
                    self.last_output_path = data.get("output_path", self.last_output_path)
                    self.filename_format = data.get("filename_format", "title_artist")
                    self.use_album_folder = data.get("use_album_folder", False)
                    self.retry_count = data.get("retry_count", 3)
            except:
                pass

    def save_config(self):
        try:
            cache_path = os.path.join(self.get_base_path(), ".spotifydown")
            data = {
                "token": self.token_input.text().strip(),
                "output_path": self.output_dir.text().strip(),
                "filename_format": "artist_title" if self.artist_title_radio.isChecked() else "title_artist",
                "use_album_folder": self.album_folder_check.isChecked(),
                "retry_count": int(self.retry_dropdown.currentText())
            }
            with open(cache_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def save_format_settings(self):
        self.save_config()
        QMessageBox.information(self, "Success", "Format settings saved successfully!")

    def initUI(self):
        self.setWindowTitle('SpotifyDown GUI')
        self.setFixedWidth(650)
        self.setFixedHeight(500)
        
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.main_layout = QVBoxLayout()
        
        self.setup_spotify_section()
        self.setup_token_section()
        self.setup_output_section()
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
        
        self.setup_button(self.paste_btn, "paste.svg", "Paste URL from clipboard", self.paste_url)
        
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
        self.token_input.setPlaceholderText("Please enter the Token value")
        self.token_input.setClearButtonEnabled(True)
        
        self.token_save_icon_btn = QPushButton()
        self.token_save_btn = QPushButton('Get Token')
        
        self.setup_button(self.token_save_icon_btn, "save.svg", "Save token", self.save_token)
        
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
                self.save_config()
                QMessageBox.information(self, "Success", "Token fetched and saved successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to fetch token")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch token: {str(e)}")

    def get_token(self):
        asyncio.run(self._fetch_token())

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

        format_layout = QHBoxLayout()
        format_layout.setSpacing(5)
        format_label = QLabel('Settings:')
        format_label.setFixedWidth(100)
        
        self.retry_label = QLabel('Retry:')
        self.retry_dropdown = QComboBox()
        for i in range(1, 11):
            self.retry_dropdown.addItem(str(i))
        self.retry_dropdown.setCurrentText(str(self.retry_count))
        self.retry_dropdown.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_dropdown.setFixedWidth(75)
        self.retry_dropdown.currentTextChanged.connect(self.save_config)
        
        format_options_layout = QHBoxLayout()
        format_options_layout.setSpacing(5)
        
        self.format_group = QButtonGroup(self)
        self.title_artist_radio = QRadioButton('Title - Artist')
        self.title_artist_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_artist_radio.toggled.connect(self.save_config)
        
        self.artist_title_radio = QRadioButton('Artist - Title')
        self.artist_title_radio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist_title_radio.toggled.connect(self.save_config)
        
        if self.filename_format == "artist_title":
            self.artist_title_radio.setChecked(True)
        else:
            self.title_artist_radio.setChecked(True)
                
        self.format_group.addButton(self.title_artist_radio)
        self.format_group.addButton(self.artist_title_radio)
        
        self.album_folder_check = QCheckBox('Album Folder')
        self.album_folder_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.album_folder_check.setChecked(self.use_album_folder)
        self.album_folder_check.toggled.connect(self.save_config)
        
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.retry_label)
        format_layout.addWidget(self.retry_dropdown)
        format_layout.addSpacing(8)
        format_layout.addWidget(self.title_artist_radio)
        format_layout.addSpacing(2)
        format_layout.addWidget(self.artist_title_radio)
        format_layout.addSpacing(8)
        format_layout.addWidget(self.album_folder_check)
        format_layout.addStretch(1)
        
        self.main_layout.addLayout(format_layout)
    
    def setup_tabs(self):
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.setup_tracks_tab()
        self.setup_process_tab()
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

    def setup_about_tab(self):
        about_tab = QWidget()
        about_layout = QVBoxLayout()
        about_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.setSpacing(3)

        title_label = QLabel("SpotifyDown GUI")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2DC261;")
        about_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        desc_label = QLabel(
            "SpotifyDown GUI is a graphical user interface for downloading\n"
            "Spotify tracks, albums, and playlists using the API provided by spotifydown.com"
        )
        desc_label.setStyleSheet("color: #888; font-size: 13px; margin: 10px;")
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
            label.setStyleSheet("color: #888; font-weight: bold;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            section_layout.addWidget(label)

            button = QPushButton("Click Here!")
            button.setFixedWidth(150)
            button.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #888;
                    border: 1px solid #888;
                    padding: 6px;
                    border-radius: 15px;
                }
                QPushButton:hover {
                    background-color: #424242;
                }
                QPushButton:pressed {
                    background-color: #575757;
                }
            """)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, url=url: QDesktopServices.openUrl(QUrl(url)))
            section_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

            about_layout.addWidget(section_widget)
            
            if sections.index((title, url)) < len(sections) - 1:
                spacer = QSpacerItem(20, 6, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                about_layout.addItem(spacer)

        footer_label = QLabel("v1.7 | December 2024")
        footer_label.setStyleSheet("font-size: 12px; color: #888; margin-top: 10px;")
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
                background-color: #424242;
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: #575757;
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
        self.save_config()
        QMessageBox.information(self, "Success", "Saved successfully!")

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
            metadata = get_track_metadata(track_id)
            
            formatted_artists = format_artists(metadata['artist'])
            
            self.tracks = [Track(
                id=track_id,
                title=metadata['title'],
                artists=formatted_artists,
                album=metadata['album'],
                cover_url=metadata['cover'],
                track_number=1,
                duration=metadata.get('duration', '0:00')
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
            if '/album/' in url:
                metadata = get_album_metadata(item_id)
                self.is_album = True
                self.is_playlist = False
                self.album_or_playlist_name = metadata['album_info']['title']
                tracks_data = metadata['track_list']
            elif '/playlist/' in url:
                metadata = get_playlist_metadata(item_id)
                self.is_album = False
                self.is_playlist = True
                self.album_or_playlist_name = metadata['playlist_info']['title']
                tracks_data = metadata['track_list']
            else:
                raise ValueError("Invalid URL: must be an album or playlist")

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
                    duration=track.get('duration', '0:00')
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
            self.type_label.setText(f"<b>Track</b> {duration}")
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
            int(self.retry_dropdown.currentText())
        )
        self.worker.finished.connect(self.on_download_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.token_error.connect(self.show_token_error)
        self.worker.start()
        self.start_timer()
        self.update_ui_for_download_start()

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
            selected_indices = []
            for item in self.track_list.selectedItems():
                track_num = int(item.text().split('.')[0]) - 1
                selected_indices.append(track_num)
            
            self.tracks = [track for i, track in enumerate(self.tracks) if i not in selected_indices]
            
            for item in self.track_list.selectedItems()[::-1]:
                self.track_list.takeItem(self.track_list.row(item))
            
            self.track_list.clear()
            for i, track in enumerate(self.tracks, 1):
                self.track_list.addItem(f"{i}. {track.title} - {track.artists} - {track.duration}")

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
