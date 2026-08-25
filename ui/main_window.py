import os
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from exporter.fb2 import save_fb2
from scraper.api_client import ApiError, download_chapter, extract_slug, get_chapters


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Скачиватель ранобэ")
        self.setFixedSize(420, 260)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(QLabel("Ссылка на ранобэ:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://ranobelib.me/ru/book/...")
        layout.addWidget(self.url_input)

        layout.addWidget(QLabel("Номер тома:"))
        self.volume_input = QSpinBox()
        self.volume_input.setRange(1, 999)
        self.volume_input.setValue(1)
        layout.addWidget(self.volume_input)

        layout.addWidget(QLabel("Номер главы:"))
        self.chapter_input = QSpinBox()
        self.chapter_input.setRange(0, 99999)
        self.chapter_input.setValue(1)
        layout.addWidget(self.chapter_input)

        self.download_btn = QPushButton("Скачать")
        self.download_btn.clicked.connect(self._on_download)
        layout.addWidget(self.download_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self._set_status("")

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _set_loading(self, loading: bool):
        self.download_btn.setEnabled(not loading)
        self.url_input.setEnabled(not loading)
        self.volume_input.setEnabled(not loading)
        self.chapter_input.setEnabled(not loading)

    def _on_download(self):
        url = self.url_input.text().strip()
        chapter = self.chapter_input.value()
        volume = self.volume_input.value()

        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите ссылку на ранобэ")
            return

        if "ranobelib.me" not in url:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Неверный формат ссылки. Укажите ссылку вида: https://ranobelib.me/ru/book/...",
            )
            return

        self._set_loading(True)
        self._set_status("Загрузка...")

        thread = threading.Thread(target=self._download, args=(url, chapter, volume), daemon=True)
        thread.start()

    def _download(self, url: str, chapter: int, volume: int):
        try:
            slug = extract_slug(url)
            chapters = get_chapters(slug)
            book_title, text, image_urls = download_chapter(slug, chapters, chapter, volume)
            filepath = save_fb2(volume, chapter, book_title, text, image_urls)
            filename = os.path.basename(filepath)
            self._finish(f"Сохранено: {filename}")
        except ApiError as e:
            self._finish(str(e), is_error=True)
        except Exception as e:
            self._finish(f"Неизвестная ошибка: {e}", is_error=True)

    def _finish(self, message: str, is_error: bool = False):
        if is_error:
            QMessageBox.critical(self, "Ошибка", message)
            self._set_status("")
        else:
            self._set_status(message)
        self._set_loading(False)
