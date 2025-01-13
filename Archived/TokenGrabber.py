import sys
import os
import asyncio
import zendriver as zd
import re
import random
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QPushButton, QTextEdit, QComboBox,
                            QLabel, QHBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QCursor

SPOTIFY_URLS = [
    "https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe",
    "https://open.spotify.com/track/4wJ5Qq0jBN4ajy7ouZIV1c",
    "https://open.spotify.com/track/6dOtVTDdiauQNBQEDOtlAB",
    "https://open.spotify.com/track/7uoFMmxln0GPXQ0AcCBXRq",
    "https://open.spotify.com/track/2HRqTpkrJO5ggZyyK6NPWz"
]

class GrabberThread(QThread):
    token_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    def run(self):
        try:
            selected_url = random.choice(SPOTIFY_URLS)
            self.status_update.emit("Fetching Token...")
            asyncio.run(self.fetch_token(selected_url))
        except Exception as e:
            self.error_occurred.emit(str(e))

    async def wait_for_element(self, page, selector, timeout=30000):
        try:
            element = await page.wait_for(selector, timeout=timeout)
            return element
        except asyncio.TimeoutError:
            raise Exception(f"Timeout waiting for element: {selector}")
        except Exception as e:
            raise Exception(f"Error finding element {selector}: {str(e)}")

    async def wait_for_token(self, page, max_attempts=10, check_interval=0.5):
        for _ in range(max_attempts):
            requests = await page.evaluate("window.requests")
            for req in requests:
                if "api.spotifydown.com/download" in req['url']:
                    token_match = re.search(r'token=(.+)$', req['url'])
                    if token_match:
                        return token_match.group(1)
            await asyncio.sleep(check_interval)
        raise Exception("Token not found within timeout period")

    async def fetch_token(self, url):
        browser = await zd.start()
        try:
            page = await browser.get("https://spotifydown.com/en")
            
            await page.evaluate("""
                window.requests = [];
                const originalFetch = window.fetch;
                window.fetch = function() {
                    return new Promise((resolve, reject) => {
                        originalFetch.apply(this, arguments)
                            .then(response => {
                                window.requests.push({
                                    url: response.url,
                                    status: response.status,
                                    headers: Object.fromEntries(response.headers.entries())
                                });
                                resolve(response);
                            })
                            .catch(reject);
                    });
                };
            """)
            
            await asyncio.sleep(self.delay)
            
            input_element = await self.wait_for_element(page, ".searchInput")
            await input_element.send_keys(url)
            
            submit_button = await self.wait_for_element(page, "button.flex.justify-center.items-center.bg-button")
            await submit_button.click()
            
            download_selector = "div.flex.items-center.justify-end button.w-24.sm\\:w-32.mt-2.p-2.cursor-pointer.bg-button.rounded-full.text-gray-100.hover\\:bg-button-active"
            download_button = await self.wait_for_element(page, download_selector)
            await download_button.click()
            
            token = await self.wait_for_token(page)
            if token:
                self.token_ready.emit(token)
            else:
                raise Exception("No token found in requests")
                
        finally:
            await browser.stop()

class Grabber(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Token Grabber")
        self.setFixedSize(400, 180)

        icon_path = os.path.join(os.path.dirname(__file__), "token.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        speed_layout = QHBoxLayout()
        speed_label = QLabel("Speed:")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["Normal", "Slow"])
        self.speed_combo.setFixedWidth(100)
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_combo)
        speed_layout.addStretch()

        self.action_button = QPushButton("Get Token")
        self.action_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.action_button.setFixedWidth(100)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.action_button)
        button_layout.addStretch()

        self.token_display = QTextEdit()
        self.token_display.setReadOnly(True)

        layout.addLayout(speed_layout)
        layout.addWidget(self.token_display)
        layout.addLayout(button_layout)

        self.action_button.clicked.connect(self.handle_button_click)

        self.thread = None
        self.current_token = None
        self.is_error_state = False
        
        self.button_timer = QTimer()
        self.button_timer.setSingleShot(True)
        self.button_timer.timeout.connect(self.reset_button_text)

    def get_selected_delay(self):
        speed = self.speed_combo.currentText()
        return 10 if speed == "Slow" else 5

    def handle_button_click(self):
        if self.is_error_state:
            self.is_error_state = False
            self.action_button.setText("Get Token")
            self.start_token_fetch()
        elif self.current_token is None:
            self.start_token_fetch()
        else:
            self.copy_token()

    def start_token_fetch(self):
        self.action_button.setEnabled(False)
        self.token_display.clear()
        self.token_display.setPlaceholderText("Initializing...")
        
        delay = self.get_selected_delay()
        self.thread = GrabberThread(delay)
        self.thread.token_ready.connect(self.on_token_ready)
        self.thread.error_occurred.connect(self.on_error)
        self.thread.status_update.connect(self.on_status_update)
        self.thread.finished.connect(self.on_thread_complete)
        self.thread.start()

    def on_token_ready(self, token):
        self.current_token = token
        self.token_display.setPlaceholderText("")
        self.token_display.setText(token)
        self.action_button.setText("Copy Token")
        self.is_error_state = False

    def on_error(self, error_message):
        self.token_display.setPlaceholderText("")
        self.token_display.setText(f"Error: {error_message}")
        self.action_button.setEnabled(True)
        self.current_token = None
        self.action_button.setText("Retry")
        self.is_error_state = True

    def on_status_update(self, message):
        self.token_display.setPlaceholderText("")
        self.token_display.setText(message)

    def on_thread_complete(self):
        self.action_button.setEnabled(True)

    def copy_token(self):
        if self.current_token:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.current_token)
            self.action_button.setText("Token Copied!")
            self.current_token = None
            self.token_display.clear()
            self.token_display.setPlaceholderText("Token Copied!")
            self.button_timer.start(1000)
    
    def reset_button_text(self):
        self.action_button.setText("Get Token")
        self.token_display.setPlaceholderText("")

def main():
    app = QApplication(sys.argv)
    window = Grabber()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
