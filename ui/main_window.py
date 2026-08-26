import os
import threading

from PyQt6.QtCore import Qt, pyqtSignal
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
from scraper.api_client import (
    ApiError,
    download_chapter,
    extract_slug,
    get_all_chapter_ints,
    get_chapters,
)


class MainWindow(QMainWindow):
    _done = pyqtSignal(str, bool)

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

        layout.addWidget(QLabel("Номер главы (пусто — все главы тома):"))
        self.chapter_input = QLineEdit()
        self.chapter_input.setPlaceholderText("Оставить пустым для скачивания всех глав")
        layout.addWidget(self.chapter_input)

        self.download_btn = QPushButton("Скачать")
        self.download_btn.clicked.connect(self._on_download)
        layout.addWidget(self.download_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self._set_status("")
        self._done.connect(self._finish)

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _set_loading(self, loading: bool):
        self.download_btn.setEnabled(not loading)
        self.url_input.setEnabled(not loading)
        self.volume_input.setEnabled(not loading)
        self.chapter_input.setEnabled(not loading)

    def _on_download(self):
        url = self.url_input.text().strip()
        chapter_text = self.chapter_input.text().strip()
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

        chapter = None
        if chapter_text:
            try:
                chapter = int(chapter_text)
            except ValueError:
                QMessageBox.warning(self, "Ошибка", "Номер главы должен быть целым числом")
                return

        self._set_loading(True)
        self._set_status("Загрузка...")

        thread = threading.Thread(target=self._download, args=(url, chapter, volume), daemon=True)
        thread.start()

    def _download(self, url: str, chapter: int | None, volume: int):
        try:
            slug = extract_slug(url)
            chapters = get_chapters(slug)

            if chapter is not None:
                book_title, chapter_name, elements = download_chapter(slug, chapters, chapter, volume)
                filepath = save_fb2(volume, chapter, book_title, elements, chapter_name=chapter_name)
                filename = os.path.basename(filepath)
                self._done.emit(f"Сохранено: {filename}", False)
            else:
                chapter_ints = get_all_chapter_ints(chapters, volume)
                if not chapter_ints:
                    raise ApiError(f"В томе {volume} нет глав")
                saved = []
                for ch_int in chapter_ints:
                    book_title, chapter_name, elements = download_chapter(slug, chapters, ch_int, volume)
                    filepath = save_fb2(volume, ch_int, book_title, elements, chapter_name=chapter_name)
                    saved.append(os.path.basename(filepath))
                self._done.emit(f"Сохранено файлов: {len(saved)}", False)
        except ApiError as e:
            self._done.emit(str(e), True)
        except Exception as e:
            self._done.emit(f"Неизвестная ошибка: {e}", True)

    def _finish(self, message: str, is_error: bool = False):
        if is_error:
            QMessageBox.critical(self, "Ошибка", message)
            self._set_status("")
        else:
            self._set_status(message)
        self._set_loading(False)
