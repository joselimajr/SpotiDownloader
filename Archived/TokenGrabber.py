import sys
import os
import asyncio
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, 
                            QVBoxLayout, QWidget, QTextEdit)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon, QCursor
import zendriver as zd

class TokenWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.token = ""
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Token Grabber")
        self.setFixedSize(400, 150)

        icon_path = os.path.join(os.path.dirname(__file__), "token.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(5)
        
        self.token_display = QTextEdit()
        self.token_display.setReadOnly(True)
        self.token_display.setPlaceholderText("Token will appear here...")
        self.token_display.setMaximumHeight(100)
        layout.addWidget(self.token_display)
        
        self.token_button = QPushButton("Get Token")
        self.token_button.setFixedWidth(100)
        self.token_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.token_button.clicked.connect(self.handle_button_click)
        layout.addWidget(self.token_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        layout.setContentsMargins(5, 5, 5, 5)
        
    async def get_token(self):
        browser = await zd.start()
        try:
            page = await browser.get("https://spotifydown.com/")
            token = await wait_for_turnstile_token(page)
            return token
        finally:
            await browser.stop()
            
    def handle_button_click(self):
        if self.token_button.text() == "Get Token":
            self.token_button.setEnabled(False)
            self.token_display.clear()
            self.token_display.setPlaceholderText("Getting token...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.token = loop.run_until_complete(self.get_token())
            self.token_display.setText(self.token)
            self.token_button.setText("Copy Token")
            self.token_button.setEnabled(True)
        elif self.token_button.text() == "Copy Token":
            clipboard = QApplication.clipboard()
            clipboard.setText(self.token)
            self.token_button.setText("Token Copied!")
            QTimer.singleShot(1000, self.reset_button)
            
    def reset_button(self):
        self.token = ""
        self.token_display.clear()
        self.token_display.setPlaceholderText("Token will appear here...")
        self.token_button.setText("Get Token")

async def wait_for_turnstile_token(page):
    max_attempts = 20
    attempts = 0
    while attempts < max_attempts:
        element = await page.query_selector('input[name="cf-turnstile-response"]')
        if element:
            attrs = element.attrs
            if attrs and 'value' in attrs:
                return attrs['value']
        await asyncio.sleep(0.5)
        attempts += 1
    raise TimeoutError("Turnstile element not found within timeout period")

def main():
    app = QApplication(sys.argv)
    window = TokenWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
