"""Обработка записей встреч (SRC-REC): определение типа, транскрибация, извлечение кадров.

Транскрипт — производное (БИТ Ньютон; нужен NEWTON_TOKEN). Кадры извлекаются условно (для встреч с
демонстрацией системы). Видеоанализ ресурсоёмкий — поголовно не применяется.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from capabilities.extract.secrets import get_secret

VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

_KEYWORDS = {
    "демо-систем": ["покажу", "демонстрац", "на экране", "в системе", "открыва", "нажима",
                    "вкладк", "реквизит", "форму", "интерфейс"],
    "процессы-asis": ["процесс", "шаг", "этап", "сначала", "потом", "передаём", "согласова", "маршрут"],
    "стейкхолдеры": ["стратег", "цел", "видение", "приоритет", "зачем нам", "руководств"],
    "оргвстреча": ["статус", "установочн", "план работ", "сроки проекта", "повестк", "орг"],
}


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _unlink(path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _format_transcript(raw: str) -> str:
    """Привести вывод newton к читаемому markdown. diarize даёт JSON со спикерами → строки «Спикер: …»."""
    raw = (raw or "").strip()
    if raw.startswith("[") and '"speaker"' in raw[:300]:
        import json
        try:
            lines = []
            for s in json.loads(raw):
                sp = s.get("speaker", "")
                txt = (s.get("text") or "").strip()
                st = s.get("start")
                tc = f" [{int(st) // 60:02d}:{int(st) % 60:02d}]" if isinstance(st, (int, float)) else ""
                lines.append(f"**{sp}**{tc}: {txt}")
            return "\n\n".join(lines)
        except Exception:
            return raw
    return raw


def detect_type(transcript: str) -> str:
    """Определить тип встречи по транскрипту (эвристика по ключевым словам)."""
    text = (transcript or "").lower()
    best, score = "прочее", 0
    for mtype, kws in _KEYWORDS.items():
        s = sum(text.count(k) for k in kws)
        if s > score:
            best, score = mtype, s
    return best if score > 0 else "прочее"


def transcribe(media_path) -> tuple[str, bool, str]:
    """Транскрибировать запись. Возвращает (текст, readable, note)."""
    p = Path(media_path)
    if not _have("newton"):
        return "", False, "нужен инструмент транскрибации (БИТ Ньютон)"
    token = get_secret("NEWTON_TOKEN")
    if not token:
        return "", False, "нужен NEWTON_TOKEN для транскрибации (БИТ Ньютон)"

    audio, tmp_audio = p, None
    if p.suffix.lower() in VIDEO:
        if not _have("ffmpeg"):
            return "", False, "нужен ffmpeg для извлечения аудио из видео"
        tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_audio.close()
        try:
            subprocess.run(["ffmpeg", "-y", "-i", str(p), "-ar", "16000", "-ac", "1", tmp_audio.name],
                           check=True, capture_output=True, timeout=900,
                           env=dict(os.environ, NEWTON_TOKEN=token))
            audio = Path(tmp_audio.name)
        except Exception:
            _unlink(tmp_audio.name)
            return "", False, "не удалось извлечь аудио (ffmpeg)"

    # newton пишет результат в файл (-o); в stdout — только статус. Движок diarize даёт спикеров,
    # v3 — запасной (RU). Берём первый непустой результат.
    out = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    out.close()
    text, note = "", ""
    try:
        for engine in ("diarize", "v3"):
            try:
                subprocess.run(["newton", "transcribe", str(audio), "-e", engine, "-l", "ru",
                                "-o", out.name], check=True, capture_output=True, timeout=1800,
                               env=dict(os.environ, NEWTON_TOKEN=token))
                text = Path(out.name).read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    break
            except Exception as exc:  # noqa: BLE001
                note = f"ошибка транскрибации (newton/{engine}): {exc}"
    finally:
        _unlink(out.name)
        if tmp_audio:
            _unlink(tmp_audio.name)

    if text:
        return _format_transcript(text), True, ""
    return "", False, note or "пустой результат транскрибации"


def frames_dir(workspace, src_code: str) -> Path:
    """Путь к папке кадров узла записи по конвенции спеки 06-f: `<workspace>/Источники/_кадры/<код-узла>/`.

    Создаёт папку и возвращает путь. Вызывается навыком `analyze-meeting` по согласию
    пользователя («разобрать на кадры?»), не самим `extract_frames`.
    """
    d = Path(workspace) / "Источники" / "_кадры" / src_code
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_frames(video_path, out_dir, every_sec: int = 30) -> list[Path]:
    """Извлечь кадры из видео (для протокола демо-встречи). Пусто, если нет ffmpeg/ошибка."""
    if not _have("ffmpeg"):
        return []
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(video_path), "-vf", f"fps=1/{every_sec}",
                        str(out / "кадр-%03d.jpg")], check=True, capture_output=True, timeout=900)
    except Exception:
        return []
    return sorted(out.glob("кадр-*.jpg"))
