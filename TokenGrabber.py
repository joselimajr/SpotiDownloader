import sys
import os
import asyncio
import zendriver as zd
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QPushButton, QTextEdit, QMessageBox, QComboBox,
                            QLabel, QHBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

class GrabberThread(QThread):
    token_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    def run(self):
        try:
            asyncio.run(self.fetch_token())
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

    async def fetch_token(self):
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
            await input_element.send_keys("https://open.spotify.com/track/2plbrEY59IikOBgBGLjaoe")
            
            submit_button = await self.wait_for_element(page, "button.flex.justify-center.items-center.bg-button")
            await submit_button.click()
            
            download_selector = "div.flex.items-center.justify-end button.w-24.sm\\:w-32.mt-2.p-2.cursor-pointer.bg-button.rounded-full.text-gray-100.hover\\:bg-button-active"
            download_button = await self.wait_for_element(page, download_selector)
            await download_button.click()
            
            await page.sleep(1)
            
            requests = await page.evaluate("window.requests")
            
            token_found = False
            for req in requests:
                if "api.spotifydown.com/download" in req['url']:
                    token_match = re.search(r'token=(.+)$', req['url'])
                    if token_match:
                        token = token_match.group(1)
                        self.token_ready.emit(token)
                        token_found = True
                        break
            
            if not token_found:
                raise Exception("No token found in requests")
                
        finally:
            await browser.stop()

class Grabber(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Token Grabber")
        self.setFixedSize(400, 200)

        icon_path = os.path.join(os.path.dirname(__file__), "token.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        mode_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Normal", "Slow"])
        self.mode_combo.setFixedWidth(100)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()

        self.action_button = QPushButton("Get Token")
        self.action_button.setFixedWidth(100)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.action_button)
        button_layout.addStretch()

        self.token_display = QTextEdit()
        self.token_display.setReadOnly(True)

        layout.addLayout(mode_layout)
        layout.addWidget(self.token_display)
        layout.addLayout(button_layout)

        self.action_button.clicked.connect(self.handle_button_click)

        self.thread = None
        self.current_token = None
        
        self.button_timer = QTimer()
        self.button_timer.setSingleShot(True)
        self.button_timer.timeout.connect(self.reset_button_text)

    def get_selected_delay(self):
        mode = self.mode_combo.currentText()
        return 10 if mode == "Slow" else 5

    def handle_button_click(self):
        if self.current_token is None:
            self.start_token_fetch()
        else:
            self.copy_token()

    def start_token_fetch(self):
        self.action_button.setEnabled(False)
        self.token_display.clear()
        self.token_display.setPlaceholderText("Fetching token... Please wait...")
        
        delay = self.get_selected_delay()
        self.thread = GrabberThread(delay)
        self.thread.token_ready.connect(self.on_token_ready)
        self.thread.error_occurred.connect(self.on_error)
        self.thread.finished.connect(self.on_thread_complete)
        self.thread.start()

    def on_token_ready(self, token):
        self.current_token = token
        self.token_display.setPlaceholderText("")
        self.token_display.setText(token)
        self.action_button.setText("Copy Token")

    def on_error(self, error_message):
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")
        self.token_display.setPlaceholderText("")
        self.action_button.setEnabled(True)
        self.current_token = None
        self.action_button.setText("Get Token")

    def on_thread_complete(self):
        self.action_button.setEnabled(True)

    def copy_token(self):
        if self.current_token:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.current_token)
            self.action_button.setText("Token Copied!")
            
            self.current_token = None
            self.button_timer.start(500)
    
    def reset_button_text(self):
        self.action_button.setText("Get Token")

def main():
    app = QApplication(sys.argv)
    window = Grabber()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
