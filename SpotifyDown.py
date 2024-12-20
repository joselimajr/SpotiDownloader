import sys
import os
from dataclasses import dataclass
from datetime import datetime
import json
import requests
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QFileDialog, QListWidget, QMessageBox, QTextEdit, QTabWidget,
    QAbstractItemView, QSpacerItem, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize, QTimer, QTime
from PyQt6.QtGui import QIcon, QTextCursor, QDesktopServices, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from mutagen.mp3 import MP3
from mutagen.id3 import APIC, TIT2, TPE1, TALB, TRCK, error

CUSTOM_HEADER = {
    'Host': 'api.spotifydown.com',
    'Referer': 'https://spotifydown.com/',
    'Origin': 'https://spotifydown.com',
}

@dataclass
class Track:
    id: str
    title: str
    artists: str
    album: str
    cover_url: str
    track_number: int

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str, list)
    progress = pyqtSignal(str, int)
    token_error = pyqtSignal()
    
    def __init__(self, tracks, outpath, token, is_single_track=False, is_album=False, is_playlist=False, album_or_playlist_name=''):
        super().__init__()
        self.tracks = tracks
        self.outpath = outpath
        self.token = token
        self.is_single_track = is_single_track
        self.is_album = is_album
        self.is_playlist = is_playlist
        self.album_or_playlist_name = album_or_playlist_name
        self.is_paused = False
        self.is_stopped = False
        self.failed_tracks = []

    def run(self):
        try:
            total_tracks = len(self.tracks)
            failed_tracks = 0
            
            for i, track in enumerate(self.tracks):
                while self.is_paused:
                    if self.is_stopped:
                        return
                    self.msleep(100)
                if self.is_stopped:
                    return

                self.progress.emit(f"Starting download ({i+1}/{total_tracks}): {track.title} - {track.artists}", 0)
                
                try:
                    self.download_and_process_track(track, self.outpath)
                    progress = int((i + 1) / total_tracks * 100)
                    self.progress.emit(f"Downloaded successfully", progress)
                except Exception as e:
                    failed_tracks += 1
                    self.failed_tracks.append((track.title, track.artists, str(e)))
                    if "token expired" in str(e).lower() or failed_tracks == total_tracks:
                        self.token_error.emit()
                        return
                    continue

            if not self.is_stopped:
                success_message = "Download completed!"
                if self.failed_tracks:
                    success_message += f"\n\nFailed downloads: {len(self.failed_tracks)} tracks"
                self.finished.emit(True, success_message, self.failed_tracks)
                
        except Exception as e:
            self.finished.emit(False, str(e), self.failed_tracks)

    def download_and_process_track(self, track, outpath):
        response = requests.get(
            f"https://api.spotifydown.com/download/{track.id}?token={self.token}", 
            headers=CUSTOM_HEADER
        )
        data = response.json()
        
        if not data.get('success'):
            raise Exception(data.get('error', 'Download failed'))

        filename = f"{track.title} - {track.artists}.mp3"
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filepath = os.path.join(outpath, filename)

        audio_response = requests.get(data['link'])
        if audio_response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(audio_response.content)
            
            self.progress.emit(f"Adding metadata: {track.title}", 50)
            self.add_metadata(filepath, track)
        else:
            raise Exception("Failed to download audio file")

    def add_metadata(self, filepath: str, track: Track):
        try:
            cover_response = requests.get(track.cover_url)
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

            audio.tags.add(TIT2(encoding=3, text=track.title))
            audio.tags.add(TPE1(encoding=3, text=track.artists))
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
        self.is_album = self.is_playlist = self.is_single_track = False
        
        self.load_config()
        
        self.elapsed_time = QTime(0, 0, 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        
        self.initUI()
        
        if hasattr(self, 'last_token') and self.token_input:
            self.token_input.setText(self.last_token)

    def get_base_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def load_config(self):
        try:
            cache_path = os.path.join(self.get_base_path(), ".cache")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    self.last_token = data.get("token", "")
                    self.last_output_path = data.get("output_path", os.path.expanduser("~\\Music"))
            else:
                self.last_token = ""
                self.last_output_path = os.path.expanduser("~\\Music")
        except Exception:
            self.last_token = ""
            self.last_output_path = os.path.expanduser("~\\Music")

    def save_config(self):
        try:
            cache_path = os.path.join(self.get_base_path(), ".cache")
            data = {
                "token": self.token_input.text().strip(),
                "output_path": self.output_dir.text().strip()
            }
            with open(cache_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def initUI(self):
        self.setWindowTitle('SpotifyDown GUI')
        self.setFixedWidth(650)
        self.setMinimumHeight(400)
        
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
        
        self.paste_btn = QPushButton()
        self.setup_button(self.paste_btn, "paste.svg", "Paste URL from clipboard", self.paste_url)
        
        self.fetch_btn = QPushButton('Fetch')
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
        
        self.token_paste_btn = QPushButton()
        self.setup_button(self.token_paste_btn, "paste.svg", "Paste token from clipboard", self.paste_token)
        
        self.token_save_btn = QPushButton('Save')
        self.token_save_btn.clicked.connect(self.save_token)
        
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_input)
        token_layout.addWidget(self.token_paste_btn)
        token_layout.addWidget(self.token_save_btn)
        self.main_layout.addLayout(token_layout)

    def setup_output_section(self):
        output_layout = QHBoxLayout()
        output_label = QLabel('Output Directory:')
        output_label.setFixedWidth(100)
        self.output_dir = QLineEdit()
        self.output_dir.setText(self.last_output_path)
        
        self.open_dir_btn = QPushButton()
        self.setup_button(self.open_dir_btn, "folder.svg", "Open output directory", self.open_output_dir)
        
        self.output_browse = QPushButton('Browse')
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
        self.setup_about_tab()

    def setup_tracks_tab(self):
        tracks_tab = QWidget()
        tracks_layout = QVBoxLayout()

        self.setup_info_widget()
        tracks_layout.addWidget(self.info_widget)

        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tracks_layout.addWidget(self.track_list)
        
        self.setup_track_buttons()
        tracks_layout.addLayout(self.btn_layout)

        tracks_tab.setLayout(tracks_layout)
        self.tab_widget.addTab(tracks_tab, "Tracks")

        self.hide_track_buttons()

    def setup_info_widget(self):
        self.info_widget = QWidget()
        info_layout = QHBoxLayout()
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(80, 80)
        self.cover_label.setScaledContents(True)
        info_layout.addWidget(self.cover_label)

        text_info_layout = QVBoxLayout()
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.title_label.setWordWrap(True)
        
        self.artists_label = QLabel()
        self.artists_label.setWordWrap(True)
        
        self.release_date_label = QLabel()
        self.release_date_label.setWordWrap(True)
        
        self.type_label = QLabel()
        self.type_label.setStyleSheet("font-size: 12px;")
        
        text_info_layout.addWidget(self.title_label)
        text_info_layout.addWidget(self.artists_label)
        text_info_layout.addWidget(self.release_date_label)
        text_info_layout.addWidget(self.type_label)
        text_info_layout.addStretch()

        info_layout.addLayout(text_info_layout, 1)
        self.info_widget.setLayout(info_layout)
        self.info_widget.setFixedHeight(100)
        self.info_widget.hide()

    def setup_track_buttons(self):
        self.btn_layout = QHBoxLayout()
        self.download_selected_btn = QPushButton('Download Selected')
        self.download_all_btn = QPushButton('Download All')
        self.remove_btn = QPushButton('Remove Selected')
        self.clear_btn = QPushButton('Clear All')
        for btn in [self.download_selected_btn, self.download_all_btn, self.remove_btn, self.clear_btn]:
            btn.setFixedWidth(150)
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
        about_layout.setSpacing(10)

        title_label = QLabel("SpotifyDown GUI")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
        about_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        sections = [
            ("Report Issues", "https://github.com/afkarxyz/SpotifyDown-GUI/issues"),
            ("YouTube", "https://www.youtube.com/channel/UCLPfgkXWjm0qK479Nr1PqBg"),
            ("About", "https://github.com/afkarxyz/SpotifyDown-GUI")
        ]

        for title, url in sections:
            section_widget = QWidget()
            section_layout = QVBoxLayout(section_widget)
            section_layout.setSpacing(5)
            section_layout.setContentsMargins(0, 0, 0, 0)

            label = QLabel(title)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            section_layout.addWidget(label)

            button = QPushButton("Click Here!")
            button.setStyleSheet("""
                QPushButton {
                    background-color: #2c2c2c;
                    color: white;
                    border: 1px solid #3f3f3f;
                    padding: 5px 10px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #3f3f3f;
                }
            """)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _, url=url: QDesktopServices.openUrl(QUrl(url)))
            section_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

            about_layout.addWidget(section_widget)
            
            if sections.index((title, url)) < len(sections) - 1:
                spacer = QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                about_layout.addItem(spacer)

        footer_label = QLabel("v1.0 December 2024 | Developed with ❤️ by afkarxyz")
        footer_label.setStyleSheet("font-size: 11px; color: #888;")
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
            self.save_config()

    def save_token(self):
        self.save_config()
        QMessageBox.information(self, "Success", "Settings saved successfully!")

    def show_token_error(self):
        QMessageBox.warning(self, "Error", "Token has expired. Please update your token.")
        self.stop_download()

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

        self.reset_info_widget()
        self.clear_tracks()

        try:
            if '/track/' in url:
                self.fetch_single_track(url)
            else:
                self.fetch_multiple_tracks(url)
                
            self.update_button_states()
            self.tab_widget.setCurrentIndex(0)
            self.reset_window_size()
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    def fetch_single_track(self, url):
        track_id = url.split("/")[-1].split("?")[0]
        metadata_response = requests.get(
            f"https://api.spotifydown.com/metadata/track/{track_id}",
            headers=CUSTOM_HEADER
        )
        metadata = metadata_response.json()
        
        if metadata.get('success', False):
            self.tracks = [Track(
                id=track_id,
                title=metadata['title'],
                artists=metadata['artists'],
                album=metadata.get('album', 'Unknown Album'),
                cover_url=metadata.get('cover', ''),
                track_number=1
            )]
            self.is_single_track = True
            self.is_album = self.is_playlist = False
            self.album_or_playlist_name = f"{self.tracks[0].title} - {self.tracks[0].artists}"
            self.update_display_after_fetch(metadata)
        else:
            raise Exception("Failed to fetch track metadata")

    def fetch_multiple_tracks(self, url):
        mode = 'playlist' if '/playlist/' in url else 'album'
        item_id = url.split("/")[-1].split("?")[0]
        
        metadata_response = requests.get(
            f"https://api.spotifydown.com/metadata/{mode}/{item_id}",
            headers=CUSTOM_HEADER
        )
        metadata = metadata_response.json()
        self.album_or_playlist_name = metadata.get('title', 'Unknown Album')
        
        self.tracks = []
        offset = 0
        total_tracks = None
        
        while True:
            try:
                response = requests.get(
                    f"https://api.spotifydown.com/tracklist/{mode}/{item_id}?offset={offset}",
                    headers=CUSTOM_HEADER
                )
                data = response.json()
                
                if total_tracks is None:
                    total_tracks = data.get('total', 0)
                
                track_list = data.get('trackList', [])
                if not track_list:
                    break
                
                for track in track_list:
                    self.tracks.append(Track(
                        id=track['id'],
                        title=track['title'],
                        artists=track['artists'],
                        album=self.album_or_playlist_name,
                        cover_url=track.get('cover', metadata.get('cover', '')),
                        track_number=len(self.tracks) + 1
                    ))
                
                if total_tracks > 0:
                    progress = min(100, int((len(self.tracks) / total_tracks) * 100))
                    self.statusBar().showMessage(f'Fetching tracks... {progress}%')
                
                if len(track_list) < 100:
                    break
                
                offset += 100
                
            except Exception as e:
                raise Exception(f"Error fetching tracks: {str(e)}")
        
        self.is_album = (mode == 'album')
        self.is_playlist = (mode == 'playlist')
        self.is_single_track = False
        
        if hasattr(self, 'statusBar'):
            self.statusBar().clearMessage()
        
        self.update_display_after_fetch(metadata)

    def update_display_after_fetch(self, metadata):
        if self.is_single_track:
            self.track_list.hide()
        else:
            self.track_list.show()
            self.track_list.clear()
            for i, track in enumerate(self.tracks, 1):
                self.track_list.addItem(f"{i}. {track.title} - {track.artists}")
        
        self.update_info_widget(metadata)
        self.update_button_states()
        self.tab_widget.setCurrentIndex(0)
        self.reset_window_size()

    def update_info_widget(self, metadata):
        self.title_label.setText(metadata['title'])
        self.artists_label.setText(metadata['artists'])
        
        if metadata.get('releaseDate'):
            release_date = datetime.strptime(metadata['releaseDate'], "%Y-%m-%d")
            formatted_date = release_date.strftime("%d-%m-%Y")
            self.release_date_label.setText(f"<b>Released</b> {formatted_date}")
            self.release_date_label.show()
        else:
            self.release_date_label.hide()
        
        if self.is_single_track:
            self.type_label.setText("Track")
        elif self.is_album:
            self.type_label.setText("Album")
        elif self.is_playlist:
            self.type_label.setText("Playlist")
        
        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self.on_cover_loaded)
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
            self.clear_btn.setText('Clear')
        else:
            self.download_selected_btn.show()
            self.remove_btn.show()
            self.download_all_btn.setText('Download All')
            self.clear_btn.setText('Clear All')
        
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
            self.download_tracks([self.track_list.row(item) for item in selected_items])

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

        if self.is_single_track:
            tracks_to_download = self.tracks
        else:
            tracks_to_download = [self.tracks[i] for i in indices]

        if self.is_album or self.is_playlist:
            folder_name = re.sub(r'[<>:"/\\|?*]', '_', self.album_or_playlist_name)
            outpath = os.path.join(outpath, folder_name)
            os.makedirs(outpath, exist_ok=True)

        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "Error", "Please enter a token")
            return

        try:
            self.worker = DownloadWorker(tracks_to_download, outpath, token,
                                        self.is_single_track, self.is_album, self.is_playlist, 
                                        self.album_or_playlist_name)
            self.worker.finished.connect(self.on_download_finished)
            self.worker.progress.connect(self.update_progress)
            self.worker.token_error.connect(self.show_token_error)
            self.worker.start()
            self.start_timer()
            
            self.update_ui_for_download_start()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while starting the download: {str(e)}")

    def update_ui_for_download_start(self):
        self.download_selected_btn.setEnabled(False)
        self.download_all_btn.setEnabled(False)
        self.stop_btn.show()
        self.pause_resume_btn.show()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        
        self.tab_widget.setCurrentWidget(self.process_tab)

    def update_progress(self, message, percentage):
        self.log_output.append(message)
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)
        if percentage > 0:
            self.progress_bar.setValue(percentage)

    def stop_download(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
        self.stop_timer()
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
            self.log_output.append(f"\nStatus: {message}")
            if failed_tracks:
                self.log_output.append("\nFailed downloads:")
                for title, artists, error in failed_tracks:
                    self.log_output.append(f"• {title} - {artists}")
                    self.log_output.append(f"  Error: {error}\n")
            
            if message != "Download stopped by user.":
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Download Complete")
                msg_box.setText(message)
                msg_box.setIcon(QMessageBox.Icon.Information)
                msg_box.exec()
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
            for item in self.track_list.selectedItems()[::-1]:
                self.track_list.takeItem(self.track_list.row(item))

    def clear_tracks(self):
        self.track_list.clear()
        self.tracks.clear()
        self.is_album = self.is_playlist = self.is_single_track = False
        self.album_or_playlist_name = ''
        self.hide_track_buttons()
        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')
        self.reset_info_widget()
        self.spotify_url.clear()
        self.reset_window_size()

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

    def reset_window_size(self):
        self.resize(self.width(), 365)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SpotifyDownGUI()
    ex.show()
    sys.exit(app.exec())
