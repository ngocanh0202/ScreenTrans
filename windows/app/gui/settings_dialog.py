"""Windows settings window: translation style (per game), text size, long translations, model, hotkeys.

App-wide choices are stored in data_dir/settings.json and override windows/config.yaml.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QRadioButton, QSpinBox, QVBoxLayout, QWidget)

from app.gui.overlay import FONT

FILE = "settings.json"
SCALES = [(0.8, "80%"), (1.0, "100%"), (1.25, "125%"), (1.5, "150%")]
MODELS = [("vinai-en2vi", "vinai-en2vi (chất lượng cao)"), ("opus-mt-en-vi", "opus-mt-en-vi (nhanh, nhẹ)")]
ENGINES = [("local", "Model trên máy"), ("gemini", "Gemini"), ("openai", "OpenAI"), ("claude", "Claude"),
           ("kaggle", "Kaggle (server riêng)")]
DAILY_LIMIT = 50000


@dataclass
class SettingsValues:
    style: str             # "match" (like the game) | "classic" (white on dark) — for the current game
    text_scale: float
    long_text: str         # "grow" | "shrink"
    model: str
    hotkeys: dict[str, str] = field(default_factory=dict)  # shown only
    ocr: str = "windows"   # OCR engine for the current game (one-shot translations)
    engine: str = "local"  # translation engine for the current game
    llm_models: dict[str, str] = field(default_factory=dict)  # engine -> model name (empty: the default)
    kaggle_url: str = ""
    daily_limit: int = DAILY_LIMIT  # characters sent to remote engines per day
    keys: dict[str, str] = field(default_factory=dict)  # keys the user typed now (never the saved ones)
    saved_keys: tuple[str, ...] = ()  # engines with a saved key (shown as such, never displayed)
    used_today: int = 0


def load_settings(data_dir: Path) -> dict:
    try:
        data = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data_dir: Path, values: dict) -> None:
    path = Path(data_dir) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=1), encoding="utf-8")


class SettingsDialog(QDialog):
    def __init__(self, values: SettingsValues, game: str = "", parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Cài đặt — ScreenTrans")
        self.setFont(QFont(FONT, 10))
        self._hotkeys = dict(values.hotkeys)

        def pair(a: str, b: str):
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            ra, rb = QRadioButton(a), QRadioButton(b)
            group = QButtonGroup(box)
            group.addButton(ra)
            group.addButton(rb)
            row.addWidget(ra)
            row.addWidget(rb)
            row.addStretch(1)
            return box, ra, rb

        style_box, self.like_game, self.readable = pair("Giống game", "Dễ đọc (chữ trắng nền tối)")
        (self.readable if values.style == "classic" else self.like_game).setChecked(True)
        self.scale = QComboBox()
        for v, label in SCALES:
            self.scale.addItem(label, v)
        self.scale.setCurrentIndex(max(0, self.scale.findData(values.text_scale)))
        long_box, self.grow, self.shrink = pair("Kéo dài khung", "Thu nhỏ chữ")
        (self.shrink if values.long_text == "shrink" else self.grow).setChecked(True)
        from app.ocr import engines

        self.ocr = QComboBox()
        notes = []
        for e in engines.WINDOWS:  # only the engines this platform can run
            self.ocr.addItem(e.label, e.name)
            ok = engines.available(e.name)
            self.ocr.model().item(self.ocr.count() - 1).setEnabled(ok)
            notes.append(f"• {e.label}: {e.note}" + ("" if ok else " Chưa có trong bản này (cần cài thêm ~190 MB, xem windows/requirements-rapidocr.txt)."))
        self._ocr_ok = {e.name for e in engines.WINDOWS if engines.available(e.name)}
        wanted = values.ocr if values.ocr in self._ocr_ok else "windows"  # a saved engine missing here: the default
        self.ocr.setCurrentIndex(max(0, self.ocr.findData(wanted)))
        self.ocr_note = QLabel("\n".join(notes))
        self.ocr_note.setWordWrap(True)
        self.ocr_note.setStyleSheet("color: #666;")
        self._llm(values)
        self.model = QComboBox()
        for v, label in MODELS:
            self.model.addItem(label, v)
        self.model.setCurrentIndex(max(0, self.model.findData(values.model)))

        form = QFormLayout()
        form.addRow(f"Kiểu bản dịch{f' ({game})' if game else ''}:", style_box)
        form.addRow("Cỡ chữ bản dịch:", self.scale)
        form.addRow("Khi bản dịch dài:", long_box)
        form.addRow("Model dịch:", self.model)
        form.addRow(f"Bộ OCR{f' ({game})' if game else ''}:", self.ocr)
        form.addRow("", self.ocr_note)
        form.addRow(f"Dịch bằng{f' ({game})' if game else ''}:", self.engine)
        form.addRow("Key / token:", self.key)
        form.addRow("Tên model:", self.llm_model)
        form.addRow("URL server Kaggle:", self.kaggle_url)
        form.addRow("Giới hạn mỗi ngày:", self.limit)
        form.addRow("", self.usage_label)
        form.addRow("", self.privacy)
        for name, combo in values.hotkeys.items():
            form.addRow(f"{name}:", QLabel(combo))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> SettingsValues:
        return SettingsValues(
            style="classic" if self.readable.isChecked() else "match",
            text_scale=float(self.scale.currentData()),
            long_text="shrink" if self.shrink.isChecked() else "grow",
            model=str(self.model.currentData()),
            hotkeys=self._hotkeys,
            ocr=str(self.ocr.currentData()) if self.ocr.currentData() in self._ocr_ok else "windows",
            engine=str(self.engine.currentData()),
            llm_models=self._models_now(),
            kaggle_url=self.kaggle_url.text().strip(),
            daily_limit=int(self.limit.value()),
            keys=self._keys_now(),
            saved_keys=self._saved_keys,
            used_today=self._used_today,
        )

    # ---- remote translation engines -------------------------------------------------------------------
    def _llm(self, values: SettingsValues) -> None:
        from app.translate.remote import DEFAULT_MODELS, NAMES

        self._defaults, self._names = DEFAULT_MODELS, NAMES
        self._models = dict(values.llm_models)
        self._typed: dict[str, str] = {}
        self._saved_keys, self._used_today = tuple(values.saved_keys), values.used_today
        self.engine = QComboBox()
        for v, label in ENGINES:
            self.engine.addItem(label, v)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.llm_model = QLineEdit()
        self.kaggle_url = QLineEdit(values.kaggle_url)
        self.kaggle_url.setPlaceholderText("https://….ngrok-free.app")
        self.limit = QSpinBox()
        self.limit.setRange(1000, 10_000_000)
        self.limit.setSingleStep(10_000)
        self.limit.setSuffix(" ký tự")
        self.limit.setValue(values.daily_limit)
        self.usage_label = QLabel(f"Đã dùng hôm nay: {values.used_today} ký tự")
        self.usage_label.setStyleSheet("color: #666;")
        self.privacy = QLabel()
        self.privacy.setWordWrap(True)
        self.privacy.setStyleSheet("color: #a15c00;")
        self._shown_engine = ""
        self.engine.setCurrentIndex(max(0, self.engine.findData(values.engine)))
        self.engine.currentIndexChanged.connect(lambda _: self._show_engine())
        self._show_engine()

    def _remember_fields(self) -> None:
        e = self._shown_engine
        if e in self._names:
            if self.key.text().strip():
                self._typed[e] = self.key.text().strip()
            self._models[e] = self.llm_model.text().strip()

    def _show_engine(self) -> None:
        self._remember_fields()
        e = str(self.engine.currentData())
        self._shown_engine = e
        remote = e in self._names
        for w in (self.key, self.llm_model, self.limit):
            w.setEnabled(remote)
        self.kaggle_url.setEnabled(e == "kaggle")
        self.key.setText(self._typed.get(e, ""))
        self.key.setPlaceholderText("•••• (đã lưu — nhập để thay)" if e in self._saved_keys else
                                    ("Dán key vào đây" if remote else ""))
        self.llm_model.setText(self._models.get(e) or self._defaults.get(e, "") if remote else "")
        self.privacy.setText(f"Chữ trong game sẽ được gửi tới {self._names[e]} để dịch (tính phí theo tài khoản "
                             f"của bạn). Lỗi / hết hạn mức → tự dùng model trên máy." if remote else "")
        self.privacy.setHidden(not remote)

    def _models_now(self) -> dict[str, str]:
        self._remember_fields()
        return {e: m for e, m in self._models.items() if m}

    def _keys_now(self) -> dict[str, str]:
        self._remember_fields()
        return dict(self._typed)
