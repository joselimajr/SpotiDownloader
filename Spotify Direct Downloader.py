import sys
import os
import re
import unicodedata
from datetime import datetime
from configparser import ConfigParser
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox, 
    QFileDialog, QProgressBar, QListWidget, QListWidgetItem, QAbstractItemView,
    QCheckBox, QTabWidget, QMessageBox, QTextBrowser
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QFont, QIcon, QCursor, QDesktopServices, QPixmap, QColor, QTextCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView

import requests
from spotify_dl import (
    get_spotify_track, get_spotify_album, get_spotify_playlist, 
    download_track, DOWNLOADER_OPTIONS, DOWNLOADER_LUCIDA_FILE_FORMATS,
    DOWNLOADER_SPOTIFYDOWN, DOWNLOADER_LUCIDA
)

# Add new constant for Yank downloader
DOWNLOADER_YANK = "yank"

def clean_filename(filename):
    # Replace emojis and other non-ASCII characters with a space
    filename = ''.join(char if ord(char) < 128 else ' ' for char in filename)
    
    # Normalize Unicode characters
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')
    
    # Replace invalid characters for Windows filenames with a hyphen
    filename = re.sub(r'[<>:"/\\|?*]', '-', filename)
    
    # Remove leading and trailing whitespace and hyphens
    filename = filename.strip().strip('-')
    
    # Replace multiple consecutive hyphens with a single hyphen
    filename = re.sub(r'-+', '-', filename)
    
    # Replace multiple spaces with a single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Limit the length to 255 characters (maximum allowed in most file systems)
    return filename[:255]

class DownloadThread(QThread):
    update_progress = pyqtSignal(int, int)
    update_log = pyqtSignal(str, int, int)
    finished = pyqtSignal()

    def __init__(self, tracks, output_dir, downloader, file_type, album_name=None, playlist_name=None):
        super().__init__()
        self.tracks = tracks
        self.output_dir = output_dir
        self.downloader = downloader
        self.file_type = file_type
        self.stop_flag = False
        self.pause_flag = False
        self.total_tracks = len(tracks)
        self.album_name = album_name
        self.playlist_name = playlist_name

    def run(self):
        if self.album_name:
            folder_name = clean_filename(self.album_name)
            output_dir = os.path.join(self.output_dir, folder_name)
        elif self.playlist_name:
            folder_name = clean_filename(self.playlist_name)
            output_dir = os.path.join(self.output_dir, folder_name)
        else:
            # For single tracks, use the main output directory
            output_dir = self.output_dir

        os.makedirs(output_dir, exist_ok=True)

        for i, track in enumerate(self.tracks, 1):
            if self.stop_flag:
                break
            while self.pause_flag:
                if self.stop_flag:
                    break
                self.msleep(100)
            if self.stop_flag:
                break
            try:
                self.update_log.emit(f"Downloading : {track.title} - {track.artist}", i, self.total_tracks)
                if self.downloader == DOWNLOADER_YANK:
                    # Implement Yank downloader logic here
                    track_id = track.id
                    yank_url = f"https://yank.g3v.co.uk/track/{track_id}"
                    # You'll need to implement the actual download logic here
                    # This is just a placeholder
                    response = requests.get(yank_url)
                    if response.status_code == 200:
                        # Save the content to a file
                        file_name = clean_filename(f"{track.title} - {track.artist}.mp3")
                        file_path = os.path.join(output_dir, file_name)
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                    else:
                        raise Exception(f"Failed to download from Yank. Status code: {response.status_code}")
                else:
                    # Existing download logic for other downloaders
                    download_track(
                        track=track,
                        spotify_dl_cfg=ConfigParser(),
                        out_file_title=clean_filename(f"{track.title} - {track.artist}"),
                        output_dir=output_dir,
                        create_dir=True,
                        downloader=self.downloader,
                        file_type=self.file_type,
                        interactive=False,
                        duplicate_download_handling="skip",
                        skip_duplicates=True
                    )
                if self.stop_flag:
                    break
                self.update_log.emit(f"Downloaded: {track.title} - {track.artist}", i, self.total_tracks)
            except Exception as e:
                if "Skipping download" in str(e):
                    self.update_log.emit(f"Skipping download of {track.title} - {track.artist}: {str(e)}", i, self.total_tracks)
                else:
                    self.update_log.emit(f"Error downloading {track.title} - {track.artist}: {str(e)}", i, self.total_tracks)
            self.update_progress.emit(i, self.total_tracks)
        self.finished.emit()

    def stop(self):
        self.stop_flag = True

    def pause(self):
        self.pause_flag = True

    def resume(self):
        self.pause_flag = False

class ColoredLabel(QLabel):
    clicked = pyqtSignal(object)

    def __init__(self, text, color, parent=None):
        super().__init__(text, parent)
        self.default_color = color
        self.hover_color = self.get_hover_color(color)
        self.clicked_color = self.get_clicked_color(color)
        self.is_clicked = False
        self.setStyleSheet(f"background-color: {color}; color: black; padding: 2px;")

    def get_hover_color(self, color):
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"#{max(r-30,0):02x}{max(g-30,0):02x}{max(b-30,0):02x}"

    def get_clicked_color(self, color):
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"#{max(r-60,0):02x}{max(g-60,0):02x}{max(b-60,0):02x}"

    def enterEvent(self, event):
        if not self.is_clicked:
            self.setStyleSheet(f"background-color: {self.hover_color}; color: black; padding: 2px;")

    def leaveEvent(self, event):
        if not self.is_clicked:
            self.setStyleSheet(f"background-color: {self.default_color}; color: black; padding: 2px;")

    def mousePressEvent(self, event):
        self.clicked.emit(self)
        super().mousePressEvent(event)

    def set_clicked(self, is_clicked):
        self.is_clicked = is_clicked
        if is_clicked:
            self.setStyleSheet(f"background-color: {self.clicked_color}; color: black; padding: 2px;")
        else:
            self.setStyleSheet(f"background-color: {self.default_color}; color: black; padding: 2px;")

class SpotifyDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Direct Downloader")
        self.setGeometry(100, 100, 600, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.downloader_display = {
            DOWNLOADER_YANK: "Yank",  # Add Yank to the downloader options
            DOWNLOADER_SPOTIFYDOWN: "SpotifyDown",
            DOWNLOADER_LUCIDA: "Lucida"
        }

        self.init_ui()
        self.load_history()

        self.set_icon()
        self.center()

        self.spotify_token = None
        self.download_button.setEnabled(False)
        self.current_clicked_label = None

        self.download_status = {}
        self.failed_downloads = 0
        self.successful_downloads = 0

    def init_ui(self):
        self.create_url_input()
        self.create_output_directory()
        self.create_track_list()
        self.create_options()
        self.create_action_buttons()
        self.create_progress_bar()
        self.create_tabs()

    def create_url_input(self):
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("Input URL"), 1)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Spotify URL (track, album, or playlist)")
        self.fetch_button = self.create_button("Fetch", color="green")
        self.fetch_button.clicked.connect(self.fetch_tracks)
        self.fetch_button.setFixedSize(80, 22)
        url_layout.addWidget(self.url_input, 4)
        url_layout.addWidget(self.fetch_button, 1)
        self.layout.addLayout(url_layout)

    def create_output_directory(self):
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Directory"), 1)
        self.output_dir = QLineEdit()
        default_output_dir = os.path.join(str(Path.home()), "Music", "Spotify Direct Downloader")
        if not os.path.exists(default_output_dir):
            os.makedirs(default_output_dir)
        self.output_dir.setText(default_output_dir)
        self.browse_button = self.create_button("Browse", color="green")
        self.browse_button.clicked.connect(self.browse_or_open_output_dir)
        self.browse_button.setFixedSize(80, 22)
        output_layout.addWidget(self.output_dir, 4)
        output_layout.addWidget(self.browse_button, 1)
        self.layout.addLayout(output_layout)

    def browse_or_open_output_dir(self):
        if self.browse_button.text() == "Browse":
            self.browse_output_dir()
        else:
            self.open_output_dir()

    def create_track_list(self):
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layout.addWidget(self.track_list, 1)

    def create_options(self):
        options_layout = QHBoxLayout()
        
        self.download_all_checkbox = QCheckBox("Download All")
        self.download_all_checkbox.setChecked(False)
        options_layout.addWidget(self.download_all_checkbox)
        
        options_layout.addSpacing(30)

        options_layout.addWidget(QLabel("Downloader"))
        self.downloader_combo = QComboBox()
        for key, value in self.downloader_display.items():
            icon_path = os.path.join(os.path.dirname(__file__), f"{value}.png")
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    self.downloader_combo.addItem(icon, value, key)
                    print(f"Icon loaded successfully for {value}")
                else:
                    print(f"Failed to load icon for {value}")
                    self.downloader_combo.addItem(value, key)
            else:
                print(f"Icon file not found for {value}")
                self.downloader_combo.addItem(value, key)
        
        # Set Yank as the default downloader
        self.downloader_combo.setCurrentText(self.downloader_display[DOWNLOADER_YANK])
        self.downloader_combo.currentTextChanged.connect(self.on_downloader_changed)
        self.downloader_combo.setFixedWidth(150)
        options_layout.addWidget(self.downloader_combo)
        options_layout.addSpacing(20)

        self.format_label = QLabel("Format")
        options_layout.addWidget(self.format_label)
        self.format_combo = QComboBox()
        self.format_combo.addItems(DOWNLOADER_LUCIDA_FILE_FORMATS)
        self.format_combo.setCurrentText("original")
        self.format_combo.setFixedWidth(150)
        options_layout.addWidget(self.format_combo)

        options_layout.addStretch(1)
        self.layout.addLayout(options_layout)

        self.on_downloader_changed(self.downloader_display[DOWNLOADER_YANK])

    def create_action_buttons(self):
        action_layout = QHBoxLayout()
        self.download_button = self.create_button("Download", color="green")
        self.download_button.clicked.connect(self.start_download)
        self.pause_resume_button = self.create_button("Pause", color="red")
        self.pause_resume_button.clicked.connect(self.toggle_pause_resume)
        self.pause_resume_button.setEnabled(False)
        self.stop_button = self.create_button("Stop", color="red")
        self.stop_button.clicked.connect(self.stop_download)
        self.stop_button.setEnabled(False)
        self.reset_button = self.create_button("Reset", color="red")
        self.reset_button.clicked.connect(self.reset_ui)
        action_layout.addWidget(self.download_button)
        action_layout.addWidget(self.pause_resume_button)
        action_layout.addWidget(self.stop_button)
        action_layout.addWidget(self.reset_button)
        self.layout.addLayout(action_layout)

    def create_progress_bar(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        self.done_label = QLabel("DONE")
        self.done_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_label.setStyleSheet("font-weight: bold; color: #1ed760")
        self.done_label.setVisible(False)
        self.layout.addWidget(self.done_label)

    def create_tabs(self):
        self.tab_widget = QTabWidget()
        
        self.create_log_tab()
        self.create_history_tab()
        self.create_lucida_stats_tab()
        self.create_about_tab()

        self.layout.addWidget(self.tab_widget, 2)

    def create_log_tab(self):
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier"))
        self.tab_widget.addTab(self.log_text, "Log")

    def create_history_tab(self):
        self.history_widget = QWidget()
        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_list = QListWidget()
        self.history_layout.addWidget(self.history_list)
        
        self.create_history_buttons()
        self.create_sort_buttons()
        
        self.tab_widget.addTab(self.history_widget, "History")

    def create_history_buttons(self):
        history_buttons_layout = QHBoxLayout()
        self.delete_history_button = self.create_button("Delete", color="red")
        self.delete_history_button.clicked.connect(self.delete_history)
        self.clear_all_history_button = self.create_button("Clear", color="red")
        self.clear_all_history_button.clicked.connect(self.clear_all_history)
        history_buttons_layout.addWidget(self.delete_history_button)
        history_buttons_layout.addWidget(self.clear_all_history_button)
        self.history_layout.addLayout(history_buttons_layout)

    def create_sort_buttons(self):
        sort_layout = QHBoxLayout()
        self.sort_date_button = QPushButton("Sort by Date")
        self.sort_title_button = QPushButton("Sort by Title")        
        self.sort_track_button = QPushButton("Sort by Track")
        self.sort_album_button = QPushButton("Sort by Album")
        self.sort_playlist_button = QPushButton("Sort by Playlist")
        self.sort_date_button.clicked.connect(lambda: self.sort_history("Date"))
        self.sort_title_button.clicked.connect(lambda: self.sort_history("Title"))        
        self.sort_track_button.clicked.connect(lambda: self.sort_history("Track"))
        self.sort_album_button.clicked.connect(lambda: self.sort_history("Album"))
        self.sort_playlist_button.clicked.connect(lambda: self.sort_history("Playlist"))
        sort_layout.addWidget(self.sort_date_button)
        sort_layout.addWidget(self.sort_title_button)
        sort_layout.addWidget(self.sort_track_button)
        sort_layout.addWidget(self.sort_album_button)
        sort_layout.addWidget(self.sort_playlist_button)
        self.history_layout.insertLayout(0, sort_layout)

        self.sort_order = {'Date': Qt.SortOrder.DescendingOrder, 'Title': Qt.SortOrder.AscendingOrder}

    def create_lucida_stats_tab(self):
        self.lucida_stats_widget = QWidget()
        self.lucida_stats_layout = QVBoxLayout(self.lucida_stats_widget)
        self.lucida_stats_webview = QWebEngineView()
        self.lucida_stats_webview.load(QUrl("https://lucida.to/stats/"))
        
        self.lucida_stats_webview.page().profile().setHttpUserAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1")
        
        self.lucida_stats_layout.addWidget(self.lucida_stats_webview)
        self.tab_widget.addTab(self.lucida_stats_widget, "Lucida Stats")

    def create_about_tab(self):
        self.about_text = QTextBrowser()
        self.about_text.setOpenExternalLinks(True)
        self.about_text.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        self.about_text.setHtml("""
            <h2 style="color: #1ed760; margin: 0;">Spotify Direct Downloader</h2>
            <p style="margin: 0;">
                This powerful application allows you to effortlessly download your favorite tracks, albums, and playlists
                <strong>directly</strong> from Spotify in high quality.
            </p>

            <h3 style="color: #d72f1e; margin: 0;">Warning!</h3>
            <p style="margin: 0;">
                Sometimes Lucida servers have problems, always check Lucida Stats before using it, Yank or SpotifyDown is highly recommended.
            </p>

            <h3 style="color: #d72f1e; margin: 0;">Credits</h3>
            <p style="margin: 0;">
                <strong>spotify_dl Creator</strong> MattJaccino &#128187;
                <a href="https://github.com/MattJaccino/spotify-downloader"
                    style="color: #1ed760;">GitHub</a>
            </p>
            <p style="margin: 0;">
                <strong>Yank Creator</strong> G3VV &#128187;
                <a href="https://github.com/G3VV/Yank"
                    style="color: #1ed760;">GitHub</a>
            </p>
            <p style="margin: 0;">
                <strong>GUI Creator</strong> afkarxyz &#128187;
                <a href="https://github.com/afkarxyz" style="color: #1ed760;">GitHub</a> &#128250;
                <a href="https://www.youtube.com/channel/UCLPfgkXWjm0qK479Nr1PqBg" style="color: #d72f1e;">YouTube</a>
            </p>
        """)
        self.tab_widget.addTab(self.about_text, "About")

    def set_icon(self):
        self.icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(self.icon_path):
            icon = QIcon(self.icon_path)
            self.setWindowIcon(icon)
        else:
            print("Warning: Icon file 'icon.svg' not found.")

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def create_button(self, text, color=None):
        button = QPushButton(text)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        if color == "green":
            base_color = "#1ed760"
            hover_color = "#18ac4c"
            pressed_color = "#0f6b30"
        elif color == "red":
            base_color = "#d72f1e"
            hover_color = "#ac2518"
            pressed_color = "#6b170f"
        else:
            base_color = "#f0f0f0"
            hover_color = "#e0e0e0"
            pressed_color = "#d0d0d0"
        
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {base_color};
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                color: {'white' if color else 'black'};
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
            QPushButton:disabled {{
                background-color: #cccccc;
                color: #666666;
            }}
        """)
        return button

    def get_spotify_token(self):
        try:
            token_resp = requests.get("https://open.spotify.com/get_access_token")
            self.spotify_token = token_resp.json()['accessToken']
        except Exception as e:
            self.log_text.append(f"Error getting Spotify token: {str(e)}")
            self.spotify_token = None

    def fetch_tracks(self):
        url = self.url_input.text()
        self.track_list.clear()
        self.log_text.clear()

        self.get_spotify_token()
        if not self.spotify_token:
            self.log_text.append("Failed to get Spotify token. Please try again.")
            return

        try:
            if "/track/" in url:
                self.fetch_track(url)
            elif "/album/" in url:
                self.fetch_album(url)
            elif "/playlist/" in url:
                self.fetch_playlist(url)
            else:
                raise ValueError("Invalid Spotify URL")

            track_count = len(self.tracks)
            if track_count == 1:
                self.log_text.append("Fetched 1 track")
            else:
                self.log_text.append(f"Fetched {track_count} tracks")
            self.download_button.setEnabled(True)
        except Exception as e:
            self.log_text.append(f"Error fetching tracks: {str(e)}")
            self.download_button.setEnabled(False)

    def fetch_track(self, url):
        track = get_spotify_track(url.split('/')[-1].split('?')[0], self.spotify_token)
        self.track_list.addItem(f"1. {track.title} - {track.artist}")
        self.tracks = [track]
        self.log_text.append(f"Fetched track: {track.title} - {track.artist}")
        self.add_to_history(url, "Track", f"{track.title} - {track.artist}")

    def fetch_album(self, url):
        album = get_spotify_album(url.split('/')[-1].split('?')[0], self.spotify_token)
        for i, track in enumerate(album.tracks, 1):
            self.track_list.addItem(f"{i}. {track.title} - {track.artist}")
        self.tracks = album.tracks
        self.album_name = album.title  # Store the album name
        track_count = len(self.tracks)
        if track_count == 1:
            self.log_text.append(f"Fetched album with 1 track: {album.title} - {album.artist}")
        else:
            self.log_text.append(f"Fetched album with {track_count} tracks: {album.title} - {album.artist}")
        self.add_to_history(url, "Album", album.title)

    def fetch_playlist(self, url):
        playlist = get_spotify_playlist(url.split('/')[-1].split('?')[0], self.spotify_token)
        for i, track in enumerate(playlist.tracks, 1):
            self.track_list.addItem(f"{i}. {track.title} - {track.artist}")
        self.tracks = playlist.tracks
        self.playlist_name = playlist.name  # Store the playlist name
        track_count = len(self.tracks)
        if track_count == 1:
            self.log_text.append(f"Fetched playlist with 1 track: {playlist.name} - {playlist.owner}")
        else:
            self.log_text.append(f"Fetched playlist with {track_count} tracks: {playlist.name} - {playlist.owner}")
        self.add_to_history(url, "Playlist", playlist.name)

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir.setText(dir_path)

    def open_output_dir(self):
        output_dir = self.output_dir.text()
        if os.path.exists(output_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))
        else:
            QMessageBox.warning(self, "Directory Not Found", "The output directory does not exist.")

    def start_download(self):
        try:
            if len(self.tracks) == 1 or self.download_all_checkbox.isChecked():
                self.tracks_to_download = self.tracks
            else:
                selected_items = self.track_list.selectedItems()
                if not selected_items:
                    self.log_text.append("No tracks selected. Please select tracks or check 'Download All'.")
                    return
                selected_indices = [self.track_list.row(item) for item in selected_items]
                self.tracks_to_download = [self.tracks[i] for i in selected_indices]

            total_tracks = len(self.tracks_to_download)
            self.log_text.append(f"[0/{total_tracks}] Starting download...")

            downloader_display = self.downloader_combo.currentText()
            downloader_actual = self.downloader_combo.currentData()
            self.log_text.append(f"Using downloader: {downloader_display}")
            
            # Reset download counters
            self.failed_downloads = 0
            self.successful_downloads = 0

            album_name = getattr(self, 'album_name', None)
            playlist_name = getattr(self, 'playlist_name', None)

            # For single tracks, set both album_name and playlist_name to None
            if len(self.tracks_to_download) == 1:
                album_name = None
                playlist_name = None

            self.download_thread = DownloadThread(
                self.tracks_to_download,
                self.output_dir.text(),
                downloader_actual,
                self.format_combo.currentText() if downloader_actual != DOWNLOADER_SPOTIFYDOWN else "mp3",
                album_name,
                playlist_name
            )
            self.download_thread.update_progress.connect(self.update_progress)
            self.download_thread.update_log.connect(self.update_log)
            self.download_thread.finished.connect(self.download_finished)
            
            self.set_download_ui_state(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setMaximum(len(self.tracks_to_download))
            
            # Clear previous download status
            self.download_status.clear()
            
            self.download_thread.start()
        except Exception as e:
            import traceback
            error_msg = f"Error in start_download: {str(e)}\n{traceback.format_exc()}"
            self.log_text.append(error_msg)
            print(error_msg)  # This will print to console if run from command line

    def set_download_ui_state(self, is_downloading):
        self.download_button.setEnabled(not is_downloading)
        self.pause_resume_button.setEnabled(is_downloading)
        self.stop_button.setEnabled(is_downloading)
        self.fetch_button.setEnabled(not is_downloading)
        self.reset_button.setEnabled(not is_downloading)
        self.progress_bar.setVisible(is_downloading)
        self.done_label.setVisible(False)
        
        # Reset pause/resume button text when stopping
        if not is_downloading:
            self.pause_resume_button.setText("Pause")

    def toggle_pause_resume(self):
        if not hasattr(self, 'download_thread'):
            return

        if self.pause_resume_button.text() == "Pause":
            self.download_thread.pause()
            self.pause_resume_button.setText("Resume")
            self.log_text.append("Download paused")
        else:
            self.download_thread.resume()
            self.pause_resume_button.setText("Pause")
            self.log_text.append("Download resumed")

    def stop_download(self):
        if hasattr(self, 'download_thread'):
            self.download_thread.stop()
            self.log_text.append("Stopping download...")
            self.download_thread.wait()  # Wait for the thread to finish
            self.download_finished()  # Call this manually since the thread might not emit the finished signal

    def update_progress(self, current, total):
        self.progress_bar.setValue(current)

    def get_overall_status(self):
        total_downloads = self.successful_downloads + self.failed_downloads
        if total_downloads == 0:
            return None  # Return None instead of "N/A"
        elif self.successful_downloads == total_downloads:
            return "Completed"
        elif self.failed_downloads == total_downloads:
            return "Failed"
        else:
            return "Partial"

    def update_done_label(self):
        status = self.get_overall_status()
        if status is None:
            self.done_label.setVisible(False)
            return
        
        self.done_label.setText(status)
        if status == "Completed":
            self.done_label.setStyleSheet("font-weight: bold; color: #1ed760")
        elif status == "Partial":
            self.done_label.setStyleSheet("font-weight: bold; color: #FFA500")
        else:  # Failed
            self.done_label.setStyleSheet("font-weight: bold; color: #d72f1e")
        self.done_label.setVisible(True)
        QTimer.singleShot(1000, lambda: self.done_label.setVisible(False))

    def update_log(self, message, current, total):
        track_id = f"[{current}/{total}]"
        status = None
        text_color = QColor("white")  # Default color
        error_color = QColor("#d72f1e")  # Specified red color for errors

        if "Downloading :" in message:
            status = "Downloading"
            # Extract the track title from the message
            track_title = message.split("Downloading : ")[1]
            # Limit title to 50 characters and add ellipsis if longer
            track_title = (track_title[:47] + '...') if len(track_title) > 50 else track_title
        elif "Downloaded:" in message:
            status = "Downloaded"
            self.successful_downloads += 1
        elif "Error downloading" in message or "Unable to locate token" in message:
            status = "Failed"
            text_color = error_color
            self.failed_downloads += 1
        elif "Skipping download" in message:
            status = "Skipped"

        if status:
            key = f"{current}/{total}"
            if status == "Failed":
                # Remove any existing "Downloading" log entry
                self.remove_downloading_log(track_id)
            
            if key not in self.download_status or self.download_status[key] != status:
                if status in ["Failed", "Downloaded", "Skipped"]:
                    # Remove any existing "Downloading" log entry
                    self.remove_downloading_log(track_id)
                
                log_message = f"{track_id} {status}"
                if status == "Downloading":
                    log_message += f": {track_title}"
                
                self.log_text.setTextColor(text_color)
                self.log_text.moveCursor(QTextCursor.MoveOperation.End)
                if self.log_text.toPlainText() and not self.log_text.toPlainText().endswith('\n'):
                    self.log_text.insertPlainText('\n')
                self.log_text.insertPlainText(log_message)
                self.log_text.setTextColor(QColor("white"))  # Reset to default color
                self.download_status[key] = status

    def remove_downloading_log(self, track_id):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        while not cursor.atEnd():
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            if cursor.selectedText().startswith(track_id) and "Downloading" in cursor.selectedText():
                cursor.removeSelectedText()
                cursor.deleteChar()  # Remove the newline
                break
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock)

    def download_finished(self):
        self.set_download_ui_state(False)
        self.log_text.append("Download finished")
        
        self.update_done_label()
        
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.browse_button.setText("Open")
        self.browse_button.setStyleSheet("""
            QPushButton {
                background-color: #1ed760;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                color: white;
            }
            QPushButton:hover {
                background-color: #18ac4c;
            }
            QPushButton:pressed {
                background-color: #0f6b30;
            }
        """)
        
        # Reset the counters
        self.failed_downloads = 0
        self.successful_downloads = 0

        # Clear the download thread reference
        if hasattr(self, 'download_thread'):
            del self.download_thread

    def reset_ui(self):
        self.url_input.clear()
        self.track_list.clear()
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.done_label.setVisible(False)
        self.downloader_combo.setCurrentText(self.downloader_display[DOWNLOADER_YANK])
        self.download_button.setEnabled(False)
        self.pause_resume_button.setEnabled(False)
        self.pause_resume_button.setText("Pause")
        self.browse_button.setText("Browse")
        self.browse_button.setStyleSheet("""
            QPushButton {
                background-color: #1ed760;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                color: white;
            }
            QPushButton:hover {
                background-color: #18ac4c;
            }
            QPushButton:pressed {
                background-color: #0f6b30;
            }
        """)
        if hasattr(self, 'lucida_stats_webview'):
            self.lucida_stats_webview.load(QUrl("https://lucida.to/stats/"))

    def on_downloader_changed(self, index):
        downloader = self.downloader_combo.currentData()
        is_lucida = downloader == DOWNLOADER_LUCIDA
        self.format_label.setVisible(is_lucida)
        self.format_combo.setVisible(is_lucida)

    def add_to_history(self, url, type, title, date=None, save=True):
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole)['url'] == url:
                return
        
        color = self.get_color_for_history(type)
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        label = ColoredLabel(f"{date} - {type}: {title} ({url})", color)
        label.clicked.connect(self.on_history_item_clicked)
        item = QListWidgetItem(self.history_list)
        item.setSizeHint(label.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, {"url": url, "type": type, "title": title, "date": date})
        
        self.history_list.insertItem(0, item)
        self.history_list.setItemWidget(item, label)
        if save:
            self.save_history()

    def on_history_item_clicked(self, clicked_label):
        if self.current_clicked_label:
            self.current_clicked_label.set_clicked(False)
        clicked_label.set_clicked(True)
        self.current_clicked_label = clicked_label
        
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            if self.history_list.itemWidget(item) == clicked_label:
                self.add_to_url(item)
                break

    def load_history(self):
        try:
            with open('spotify_ddl_history.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    try:
                        date, rest = line.split(' - ', 1)
                        type_info, title_url = rest.split(': ', 1)
                        title, url = title_url.rsplit(' (', 1)
                        url = url.rstrip(')')
                        self.add_to_history(url, type_info, title, date, save=False)
                    except ValueError:
                        print(f"Ignoring malformed history entry: {line}")
        except FileNotFoundError:
            print("History file not found. Starting with an empty history.")
        except Exception as e:
            print(f"Error loading history: {str(e)}")

        self.history_list.itemClicked.connect(self.add_to_url)

    def sort_history(self, sort_type):
        items = []
        for i in range(self.history_list.count()):
            item = self.history_list.takeItem(0)
            items.append(item)
        
        if sort_type in ['Date', 'Title']:
            self.sort_order[sort_type] = Qt.SortOrder.DescendingOrder if self.sort_order[sort_type] == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
            
            reverse = self.sort_order[sort_type] == Qt.SortOrder.DescendingOrder
            if sort_type == 'Date':
                items.sort(key=lambda x: x.data(Qt.ItemDataRole.UserRole)['date'], reverse=reverse)
            else:  # Title
                items.sort(key=lambda x: x.data(Qt.ItemDataRole.UserRole)['title'].lower(), reverse=reverse)
        else:
            items.sort(key=lambda x: (x.data(Qt.ItemDataRole.UserRole)['type'] != sort_type, 
                                    x.data(Qt.ItemDataRole.UserRole)['type'],
                                    x.data(Qt.ItemDataRole.UserRole)['title']))
        
        for item in items:
            self.history_list.addItem(item)
            data = item.data(Qt.ItemDataRole.UserRole)
            label = ColoredLabel(f"{data['date']} - {data['type']}: {data['title']} ({data['url']})",
                                self.get_color_for_history(data['type']))
            self.history_list.setItemWidget(item, label)

    def save_history(self):
        try:
            with open('spotify_ddl_history.txt', 'w', encoding='utf-8') as f:
                for i in range(self.history_list.count()):
                    item = self.history_list.item(i)
                    data = item.data(Qt.ItemDataRole.UserRole)
                    f.write(f"{data['date']} - {data['type']}: {data['title']} ({data['url']})\n")
            print("History saved successfully")
        except Exception as e:
            print(f"Error saving history: {str(e)}")

    def add_to_url(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.url_input.setText(data['url'])
        
        color = self.get_color_for_type(data['type'])
        
        def flash_color():
            self.url_input.setStyleSheet(f"color: {color};")
            QTimer.singleShot(250, reset_color)
        
        def reset_color():
            self.url_input.setStyleSheet("color: white;")
        
        QTimer.singleShot(0, flash_color)

    def get_color_for_history(self, type):
        if type == "Track":
            return "#d4e6f4"  # Light Blue
        elif type == "Album":
            return "#d2f7df"  # Light Green
        elif type == "Playlist":
            return "#f7d5d2"  # Light Red
        else:
            return "#000000"  # Black for unknown types

    def get_color_for_type(self, type):
        if type == "Track":
            return "#69aadb"  # Light Blue
        elif type == "Album":
            return "#61e38f"  # Light Green
        elif type == "Playlist":
            return "#e36d61"  # Light Red
        else:
            return "#000000"  # Black for unknown types
        
    def delete_history(self):
        for item in self.history_list.selectedItems():
            self.history_list.takeItem(self.history_list.row(item))
        self.save_history()

    def clear_all_history(self):
        reply = QMessageBox.question(self, 'Clear All History',
                                    'Are you sure you want to clear all history?',
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.history_list.clear()
            self.save_history()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SpotifyDownloaderGUI()
    window.show()
    sys.exit(app.exec())
