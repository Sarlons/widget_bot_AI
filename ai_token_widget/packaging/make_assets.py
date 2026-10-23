"""Generate the Windows icon and version resources used by PyInstaller.

The build script calls this before PyInstaller so the executable metadata and
the installer icon always match ``ai_token_widget.__version__``. Keeping the
assets generated avoids committing binary files and stale version strings.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

PACKAGING = Path(__file__).resolve().parent
PROJECT = PACKAGING.parent
sys.path.insert(0, str(PROJECT.parent))

from ai_token_widget import __version__  # noqa: E402

ACCENT = QColor("#4ade80")
BACKGROUND = QColor("#14161b")
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _render_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        margin = max(1, round(size * 0.08))
        painter.setBrush(ACCENT)
        painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
        inner = round(size * 0.30)
        painter.setBrush(BACKGROUND)
        painter.drawEllipse(inner, inner, size - 2 * inner, size - 2 * inner)
    finally:
        painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Qt could not encode the icon as PNG")
    finally:
        buffer.close()
    return bytes(data)


def write_icon(path: Path) -> None:
    images = [(size, _png_bytes(_render_icon(size))) for size in ICON_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    for size, data in images:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        offset += len(data)
        payload += data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes(entries) + bytes(payload))


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits) if digits else 0)
    parts.extend([0] * (4 - len(parts)))
    return tuple(parts[:4])  # type: ignore[return-value]


def _version_info(version: str, *, description: str, internal: str, original: str) -> str:
    numbers = _version_tuple(version)
    dotted = ".".join(str(number) for number in numbers)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'AI Token Widget'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{dotted}'),
         StringStruct('InternalName', '{internal}'),
         StringStruct('OriginalFilename', '{original}'),
         StringStruct('ProductName', 'AI Token Widget'),
         StringStruct('ProductVersion', '{dotted}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    output = Path(arguments[0]) if arguments else PACKAGING / "assets"
    output.mkdir(parents=True, exist_ok=True)

    application = QGuiApplication.instance() or QGuiApplication([])
    try:
        write_icon(output / "icon.ico")
    finally:
        if QGuiApplication.instance() is application:
            application.quit()

    (output / "version_info_widget.txt").write_text(
        _version_info(
            __version__,
            description="AI Token Widget",
            internal="AITokenWidget",
            original="AITokenWidget.exe",
        ),
        encoding="utf-8",
    )
    (output / "version_info_bridge.txt").write_text(
        _version_info(
            __version__,
            description="AI Token Widget Claude quota bridge",
            internal="AITokenWidgetBridge",
            original="AITokenWidgetBridge.exe",
        ),
        encoding="utf-8",
    )
    print(f"generated packaging assets for {__version__} in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
