import sys, os, configparser
from dataclasses import dataclass
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QFileDialog, 
                             QListWidget, QMessageBox, QTextEdit, QComboBox, QTabWidget, QAbstractItemView, QSpacerItem, 
                             QSizePolicy, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QIcon, QTextCursor, QDesktopServices
from spddl import get_track_info, get_album_info, get_playlist_info, download_track_spotifydown, download_track_yank, sanitize_filename, Song

def configure_io_encoding():
    try:
        if sys.stdout: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, IOError):
        if sys.stdout: sys.stdout.encoding = 'utf-8'
        if sys.stderr: sys.stderr.encoding = 'utf-8'

configure_io_encoding()

@dataclass
class HistoryItem:
    url: str
    title: str
    artist: str
    type: str
    date: str

class DownloadWorker(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str, int)
    
    def __init__(self, tracks, outpath, download_method, is_album=False, is_playlist=False, album_or_playlist_name=''):
        super().__init__()
        self.tracks = tracks
        self.outpath = outpath
        self.download_method = download_method
        self.is_album = is_album
        self.is_playlist = is_playlist
        self.album_or_playlist_name = album_or_playlist_name
        self.is_paused = False
        self.is_stopped = False

    def run(self):
        try:
            total_tracks = len(self.tracks)
            for i, track in enumerate(self.tracks):
                while self.is_paused:
                    if self.is_stopped: return
                    self.msleep(100)
                if self.is_stopped: return
                if self.download_method == "spotifydown":
                    download_track_spotifydown(track, self.outpath)
                else:
                    download_track_yank(track, self.outpath)
                progress_percentage = int((i + 1) / total_tracks * 100)
                self.progress.emit(f"Downloaded: {track.title} - {track.artists}", progress_percentage)
            self.finished.emit(True, "Download completed successfully!")
        except Exception as e:
            self.finished.emit(False, str(e))

    def pause(self): self.is_paused = True
    def resume(self): self.is_paused = False
    def stop(self): 
        self.is_stopped = True
        self.is_paused = False

class spddlGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.tracks = []
        self.album_or_playlist_name = ''
        self.is_album = self.is_playlist = self.is_single_track = False
        self.history = []
        self.load_history()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('spddl GUI')
        self.setFixedSize(650, 400)
        self.icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))
        else:
            print("Warning: Icon file 'icon.svg' not found.")
        
        main_layout = QVBoxLayout()
        
        # Spotify URL input
        spotify_layout = QHBoxLayout()
        spotify_label = QLabel('Spotify URL:')
        spotify_label.setFixedWidth(100)
        self.spotify_url = QLineEdit()
        self.fetch_btn = QPushButton('Fetch')
        self.fetch_btn.clicked.connect(self.fetch_tracks)
        spotify_layout.addWidget(spotify_label)
        spotify_layout.addWidget(self.spotify_url)
        spotify_layout.addWidget(self.fetch_btn)
        main_layout.addLayout(spotify_layout)

        # Output directory
        output_layout = QHBoxLayout()
        output_label = QLabel('Output Directory:')
        output_label.setFixedWidth(100)
        self.output_dir = QLineEdit()
        self.output_dir.setText(os.path.expanduser("~\\Music"))
        self.output_browse = QPushButton('Browse')
        self.output_browse.clicked.connect(self.browse_output)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_dir)
        output_layout.addWidget(self.output_browse)
        main_layout.addLayout(output_layout)

        # Server selection
        server_layout = QHBoxLayout()
        server_label = QLabel('Server:')
        server_label.setFixedWidth(100)
        self.server_select = QComboBox()
        spotifydown_icon = QIcon(os.path.join(os.path.dirname(__file__), "SpotifyDown.png"))
        yank_icon = QIcon(os.path.join(os.path.dirname(__file__), "Yank.png"))
        self.server_select.addItem(spotifydown_icon, "SpotifyDown (320 kbps)")
        self.server_select.addItem(yank_icon, "Yank (128 kbps)")
        server_layout.addWidget(server_label)
        server_layout.addWidget(self.server_select)
        main_layout.addLayout(server_layout)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Tracks tab
        tracks_tab = QWidget()
        tracks_layout = QVBoxLayout()
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tracks_layout.addWidget(self.track_list)
        
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
        
        tracks_layout.addLayout(self.btn_layout)
        tracks_tab.setLayout(tracks_layout)
        self.tab_widget.addTab(tracks_tab, "Tracks")

        self.hide_track_buttons()

        # Process tab
        self.process_tab = QWidget()
        process_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        control_layout = QHBoxLayout()
        self.stop_btn = QPushButton('Stop')
        self.pause_resume_btn = QPushButton('Pause')
        self.stop_btn.clicked.connect(self.stop_download)
        self.pause_resume_btn.clicked.connect(self.toggle_pause_resume)
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.pause_resume_btn)
        process_layout.addWidget(self.log_output)
        process_layout.addWidget(self.progress_bar)
        process_layout.addLayout(control_layout)
        self.process_tab.setLayout(process_layout)
        self.tab_widget.addTab(self.process_tab, "Process")

        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        sort_layout = QHBoxLayout()
        sort_label = QLabel("Sort by:")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Title", "Artist", "Type", "Date"])
        self.sort_combo.currentIndexChanged.connect(self.sort_history)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_combo)
        sort_layout.addStretch()
        history_layout.addLayout(sort_layout)
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.load_history_item)
        history_layout.addWidget(self.history_list)
        history_tab.setLayout(history_layout)
        self.tab_widget.addTab(history_tab, "History")
        self.update_history_list()

        # About tab
        about_tab = QWidget()
        about_layout = QVBoxLayout()
        about_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.setSpacing(10)

        title_label = QLabel("About spddl GUI")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
        about_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        sections = [
            ("Please report any issues or suggestions on the repository.", "https://github.com/afkarxyz/spddl-GUI"),
            ("Visit our YouTube channel for informative videos.", "https://www.youtube.com/channel/UCLPfgkXWjm0qK479Nr1PqBg"),
            ("Learn more about spddl.", "https://github.com/afkarxyz/spddl")
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

        footer_label = QLabel("spddl GUI v1.0 October 2024 | Developed with ❤️ by afkarxyz")
        footer_label.setStyleSheet("font-size: 11px; color: #888;")
        about_layout.addWidget(footer_label, alignment=Qt.AlignmentFlag.AlignCenter)

        about_tab.setLayout(about_layout)
        self.tab_widget.addTab(about_tab, "About")

        self.setLayout(main_layout)

    def browse_output(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory: self.output_dir.setText(directory)

    def fetch_tracks(self):
        url = self.spotify_url.text()
        if not url:
            QMessageBox.warning(self, 'Warning', 'Please enter a Spotify URL.')
            return

        try:
            if "album" in url:
                self.tracks, self.album_or_playlist_name = get_album_info(url)
                self.is_album, self.is_playlist, self.is_single_track = True, False, False
                item_type = "Album"
            elif "playlist" in url:
                self.tracks, self.album_or_playlist_name = get_playlist_info(url)
                self.is_album, self.is_playlist, self.is_single_track = False, True, False
                item_type = "Playlist"
            else:
                track_info = get_track_info(url)
                self.tracks = [Song(
                    title=track_info['metadata']['title'],
                    artists=track_info['metadata']['artists'],
                    album=track_info['metadata'].get('album', 'Unknown Album'),
                    cover=track_info['metadata'].get('cover', ''),
                    link=url
                )]
                self.is_album, self.is_playlist, self.is_single_track = False, False, True
                self.album_or_playlist_name = f"{self.tracks[0].title} - {self.tracks[0].artists}"
                item_type = "Track"

            self.track_list.clear()
            for i, track in enumerate(self.tracks, 1):
                self.track_list.addItem(f"{i}. {track.title} - {track.artists}")
            
            self.add_to_history(url, self.album_or_playlist_name, item_type)
            
            QMessageBox.information(self, 'Success', f'Fetched {len(self.tracks)} track{"" if len(self.tracks) == 1 else "s"}.')
            
            self.update_button_states()
            self.tab_widget.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'An error occurred: {str(e)}')

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
        self.download_tracks(range(self.track_list.count()))

    def download_tracks(self, indices):
        self.log_output.clear()
        outpath = self.output_dir.text()
        if not os.path.exists(outpath):
            QMessageBox.warning(self, 'Warning', 'Invalid output directory.')
            return

        tracks_to_download = [self.tracks[i] for i in indices]
        download_method = "spotifydown" if self.server_select.currentIndex() == 0 else "yank"

        if self.is_album or self.is_playlist:
            folder_name = sanitize_filename(self.album_or_playlist_name)
            outpath = os.path.join(outpath, folder_name)
            os.makedirs(outpath, exist_ok=True)

        self.worker = DownloadWorker(tracks_to_download, outpath, download_method, 
                                    self.is_album, self.is_playlist, self.album_or_playlist_name)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.progress.connect(self.update_progress)
        self.worker.start()

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
        self.progress_bar.setValue(percentage)

    def stop_download(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
        self.on_download_finished(True, "Download stopped by user.")

    def toggle_pause_resume(self):
        if hasattr(self, 'worker'):
            if self.worker.is_paused:
                self.worker.resume()
                self.pause_resume_btn.setText('Pause')
            else:
                self.worker.pause()
                self.pause_resume_btn.setText('Resume')

    def update_log(self, message):
        self.log_output.append(message)
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)

    def on_download_finished(self, success, message):
        self.download_selected_btn.setEnabled(not self.is_single_track)
        self.download_all_btn.setEnabled(True)
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')

        if success:
            QMessageBox.information(self, 'Success', message)
        else:
            QMessageBox.critical(self, 'Error', f'An error occurred: {message}')

    def remove_selected_tracks(self):
        if not self.is_single_track:
            for item in self.track_list.selectedItems()[::-1]:
                self.track_list.takeItem(self.track_list.row(item))

    def clear_tracks(self):
        self.track_list.clear()
        self.tracks.clear()
        self.is_single_track = False
        self.hide_track_buttons()
        self.spotify_url.clear()
        self.output_dir.setText(os.path.expanduser("~\\Music"))
        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.stop_btn.hide()
        self.pause_resume_btn.hide()
        self.pause_resume_btn.setText('Pause')

    def add_to_history(self, url, title, item_type):
        current_date = datetime.now().strftime("%d-%m-%Y")
        artist = ""
        
        if item_type in ["Album", "Playlist"]:
            if self.tracks:
                artist = self.tracks[0].artists
        elif item_type == "Track":
            parts = title.rsplit(" - ", 1)
            title, artist = parts if len(parts) > 1 else (title, "Unknown Artist")
        
        new_item = HistoryItem(url, title, artist, item_type, current_date)
        
        self.history = [item for item in self.history if item.url != new_item.url]
        self.history.insert(0, new_item)
        self.history = self.history[:20]
        self.save_history()

    def sort_history(self):
        sort_option = self.sort_combo.currentText()
        key_func = {
            "Title": lambda x: x.title.lower(),
            "Artist": lambda x: x.artist.lower(),
            "Type": lambda x: x.type.lower(),
            "Date": lambda x: datetime.strptime(x.date, "%d-%m-%Y")
        }
        reverse = sort_option == "Date"
        self.history.sort(key=key_func[sort_option], reverse=reverse)
        self.update_history_list()

    def update_history_list(self):
        self.history_list.clear()
        for i, item in enumerate(self.history, 1):
            display_text = f"{i}. {item.type} | {item.date} | {item.title}"
            if item.artist:
                display_text += f" ({item.artist})"
            self.history_list.addItem(display_text)

    def load_history_item(self, item):
        index = self.history_list.row(item)
        history_item = self.history[index]
        self.spotify_url.setText(history_item.url)

    def save_history(self):
        config = configparser.ConfigParser()
        config['HISTORY'] = {f'item_{i}': f'{item.url}||{item.title}||{item.artist}||{item.type}||{item.date}'
                             for i, item in enumerate(self.history)}
        with open('spddl.ini', 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    def load_history(self):
        config = configparser.ConfigParser()
        config.read('spddl.ini', encoding='utf-8')
        if 'HISTORY' in config:
            self.history = []
            for _, value in config['HISTORY'].items():
                try:
                    url, title, artist, item_type, date = value.split('||')
                    self.history.append(HistoryItem(url, title, artist, item_type, date))
                except ValueError:
                    print(f"Error parsing history item: {value}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = spddlGUI()
    ex.show()
    sys.exit(app.exec())    
