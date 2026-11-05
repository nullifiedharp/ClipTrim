"""
ClipTrim - a simple desktop video trimmer / cutter.
Split the video into parts, mark parts to remove, export the rest joined together.

Keys:  Space play/pause      P preview result from start
       S split at playhead   Del remove/restore part under playhead
       I remove everything before playhead   O remove everything after
       Ctrl+Z undo           Left/Right +-1s   Shift+Left/Right +-1 frame
       Ctrl+O open           Ctrl+E export
Timeline: drag split lines to adjust, right-click a part to remove/restore it.

Copyright (C) 2026 NullHarp
https://github.com/nullifiedharp/ClipTrim

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details. You should have received a copy of
the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
import os
import re
import sys
import bisect
import shutil
import tempfile
import subprocess

from PySide6.QtCore import Qt, QUrl, QProcess, Signal, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QKeySequence, QShortcut,
                           QDesktopServices, QIcon, QPalette)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QComboBox, QProgressBar, QMessageBox, QStackedWidget, QCheckBox,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

APP_VERSION = "1.1.0"
VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".ts", ".mts", ".m2ts")
MIN_PART = 50          # ms: smallest part we allow
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def find_ffmpeg():
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(base_dir(), name)
        if os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")


def probe(ffmpeg, path):
    """Returns (has_audio, start_time_seconds) from ffmpeg's file header dump."""
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True,
                           text=True, errors="ignore", timeout=20, creationflags=NO_WINDOW)
        m = re.search(r"start: (-?[\d.]+)", r.stderr)
        return "Audio:" in r.stderr, float(m.group(1)) if m else 0.0
    except Exception:
        return True, 0.0


def fmt(ms):
    ms = max(0, int(ms))
    h, m, s, r = ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000
    return f"{h}:{m:02d}:{s:02d}.{r:03d}" if h else f"{m:02d}:{s:02d}.{r:03d}"


class Timeline(QWidget):
    """
    The video is a list of parts: [start_ms, end_ms, keep].
    Splitting adds a boundary; parts can be kept or removed.
    """
    seek = Signal(int)
    changed = Signal()
    M = 12

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(60)
        self.setMouseTracking(True)
        self.duration = self.pos = 0
        self.segs = []
        self.keyframes = []
        self.undo_stack = []
        self._drag = None

    # ----- model -----
    def set_duration(self, d):
        self.duration = max(0, d)
        self.segs = [[0, self.duration, True]] if self.duration else []
        self.undo_stack.clear()
        self.changed.emit()
        self.update()

    def set_position(self, p):
        self.pos = p
        self.update()

    def push_undo(self):
        self.undo_stack.append([s[:] for s in self.segs])
        del self.undo_stack[:-100]

    def undo(self):
        if self.undo_stack:
            self.segs = self.undo_stack.pop()
            self._emit()

    def reset(self):
        if self.duration and (len(self.segs) > 1 or not self.segs[0][2]):
            self.push_undo()
            self.segs = [[0, self.duration, True]]
            self._emit()

    def _emit(self):
        self.changed.emit()
        self.update()

    def index_at(self, t):
        for i, (s, e, _) in enumerate(self.segs):
            if s <= t < e:
                return i
        return len(self.segs) - 1

    def _split(self, t):
        """Split at t (snapping to an existing boundary if close). Returns the boundary used."""
        t = max(0, min(int(t), self.duration))
        for b in [0, self.duration] + [s[0] for s in self.segs[1:]]:
            if abs(b - t) < MIN_PART:
                return b
        i = self.index_at(t)
        s, e, k = self.segs[i]
        self.segs[i:i + 1] = [[s, t, k], [t, e, k]]
        return t

    def split(self, t):
        if not self.duration:
            return
        self.push_undo()
        before = len(self.segs)
        self._split(t)
        if len(self.segs) == before:
            self.undo_stack.pop()
        self._emit()

    def toggle(self, t):
        if not self.duration:
            return
        self.push_undo()
        seg = self.segs[self.index_at(t)]
        seg[2] = not seg[2]
        self._emit()

    def mark_in(self, t):
        """Remove everything before t (moves a previous In point)."""
        if not self.duration:
            return
        self.push_undo()
        lead = 0
        for s, e, k in self.segs:
            if k:
                break
            lead = e
        b = self._split(t)
        for seg in self.segs:
            if seg[1] <= b:
                seg[2] = False
            elif seg[0] < lead:
                seg[2] = True
        self._emit()

    def mark_out(self, t):
        """Remove everything after t (moves a previous Out point)."""
        if not self.duration:
            return
        self.push_undo()
        trail = self.duration
        for s, e, k in reversed(self.segs):
            if k:
                break
            trail = s
        b = self._split(t)
        for seg in self.segs:
            if seg[0] >= b:
                seg[2] = False
            elif seg[1] > trail:
                seg[2] = True
        self._emit()

    def kept_ranges(self):
        out = []
        for s, e, k in self.segs:
            if not k:
                continue
            if out and out[-1][1] == s:
                out[-1][1] = e
            else:
                out.append([s, e])
        return [(s, e) for s, e in out if e - s >= MIN_PART]

    def next_kept_start(self, t):
        for s, e, k in self.segs:
            if k and e > t + 1 and e - s >= MIN_PART:
                return max(s, t)
        return None

    # ----- drawing -----
    def _x(self, ms):
        w = self.width() - 2 * self.M
        return self.M + (ms / self.duration * w if self.duration else 0)

    def _ms(self, x):
        w = max(1, self.width() - 2 * self.M)
        return int(min(max((x - self.M) / w, 0.0), 1.0) * self.duration)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h, top = self.height(), 14
        bh = h - 28
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a2a2e"))
        p.drawRoundedRect(QRectF(self.M, top, self.width() - 2 * self.M, bh), 4, 4)
        if not self.duration:
            return
        for s, e, k in self.segs:
            r = QRectF(self._x(s), top, self._x(e) - self._x(s), bh)
            if k:
                p.setBrush(QColor(77, 163, 255, 95))
                p.drawRect(r)
            else:
                p.setBrush(QColor(255, 70, 70, 45))
                p.drawRect(r)
                p.setBrush(QBrush(QColor(255, 90, 90, 150), Qt.BDiagPattern))
                p.drawRect(r)
        if self.keyframes:
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            for k in self.keyframes:
                x = self._x(k)
                p.drawLine(QPointF(x, top + bh - 5), QPointF(x, top + bh))
            p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e8e8ee"))
        for s, _, _ in self.segs[1:]:
            x = self._x(s)
            p.drawRect(QRectF(x - 1, top, 2, bh))
            p.drawRoundedRect(QRectF(x - 4, top - 7, 8, 7), 2, 2)
            p.drawRoundedRect(QRectF(x - 4, top + bh, 8, 7), 2, 2)
        px = self._x(self.pos)
        p.setPen(QPen(QColor("#ffd84d"), 2))
        p.drawLine(QPointF(px, 2), QPointF(px, h - 2))

    def _boundary_at(self, x):
        best, bd = None, 8
        for i in range(1, len(self.segs)):
            d = abs(x - self._x(self.segs[i][0]))
            if d <= bd:
                best, bd = i, d
        return best

    def mousePressEvent(self, e):
        if not self.duration:
            return
        x = e.position().x()
        if e.button() == Qt.RightButton:
            self.toggle(self._ms(x))
            return
        b = self._boundary_at(x)
        if b is not None:
            self.push_undo()
            self._drag = b
        else:
            self._drag = "seek"
            self.seek.emit(self._ms(x))

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if isinstance(self._drag, int):
            i = self._drag
            lo, hi = self.segs[i - 1][0] + MIN_PART, self.segs[i][1] - MIN_PART
            t = max(lo, min(self._ms(x), hi))
            self.segs[i - 1][1] = self.segs[i][0] = t
            self.seek.emit(t)
            self._emit()
        elif self._drag == "seek":
            self.seek.emit(self._ms(x))
        else:
            self.setCursor(Qt.SizeHorCursor if self.duration and self._boundary_at(x) else Qt.ArrowCursor)

    def mouseReleaseEvent(self, _):
        self._drag = None


class ClipTrim(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.setWindowTitle("ClipTrim")
        self.resize(1100, 720)
        self.setAcceptDrops(True)
        ico = os.path.join(base_dir(), "icon.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.src = None
        self.proc = None
        self.jobs = []
        self.tmpdir = None
        self.out_path = None
        self.has_audio = True
        self.start_time = 0.0
        self.kf_proc = None
        self.kf_buf = b""
        self.kf_found = set()
        self.keyframes = None      # sorted ms list once scanned
        self.ffmpeg = find_ffmpeg()

        # Player
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)

        self.hint = QLabel("Drop a video here\nor press Ctrl+O")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setStyleSheet("color:#888; font-size:20px; border:2px dashed #444; border-radius:12px;")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.hint)
        self.stack.addWidget(self.video)

        self.timeline = Timeline()

        def btn(text, slot, tip=""):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.NoFocus)  # keep Space/arrows for the shortcuts
            b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            return b

        self.b_open = btn("Open…", self.open_dialog, "Ctrl+O")
        self.b_play = btn("Play", self.toggle_play, "Space")
        self.b_preview = btn("Preview result  [P]", self.preview, "Play from the start, skipping removed parts")
        self.b_split = btn("✂ Split  [S]", lambda: self.timeline.split(self.player.position()),
                           "Split the video at the playhead")
        self.b_toggle = btn("Remove part  [Del]", lambda: self.timeline.toggle(self.player.position()),
                            "Remove or restore the part under the playhead (or right-click it)")
        self.b_in = btn("Cut before  [I]", lambda: self.timeline.mark_in(self.player.position()),
                        "Remove everything before the playhead")
        self.b_out = btn("Cut after  [O]", lambda: self.timeline.mark_out(self.player.position()),
                         "Remove everything after the playhead")
        self.b_undo = btn("Undo", self.timeline.undo, "Ctrl+Z")
        self.b_reset = btn("Reset", self.timeline.reset, "Clear all splits and cuts")
        self.chk_skip = QCheckBox("Skip removed parts while playing")
        self.chk_skip.setFocusPolicy(Qt.NoFocus)
        self.chk_skip.setChecked(True)
        self.lbl_time = QLabel("00:00.000 / 00:00.000")
        self.lbl_sum = QLabel("")
        self.lbl_sum.setStyleSheet("color:#4da3ff;")

        self.mode = QComboBox()
        self.mode.setFocusPolicy(Qt.NoFocus)
        self.mode.addItems([
            "Fast – no re-encode (instant; each kept piece starts at the next keyframe)",
            "Precise – re-encode to MP4 (frame-accurate, slower)",
        ])
        self.mode.currentIndexChanged.connect(self.on_changed)
        self.b_export = btn("Export  [Ctrl+E]", self.export)
        self.b_export.setStyleSheet("font-weight:bold;")
        self.b_cancel = btn("Cancel", self.cancel_export)
        self.b_cancel.hide()
        self.progress = QProgressBar()
        self.progress.hide()
        self.status = QLabel("" if self.ffmpeg else "⚠ ffmpeg not found – export disabled")

        row1 = QHBoxLayout()
        for w in (self.b_open, self.b_play, self.b_preview):
            row1.addWidget(w)
        row1.addSpacing(16)
        for w in (self.b_split, self.b_toggle, self.b_in, self.b_out, self.b_undo, self.b_reset):
            row1.addWidget(w)
        row1.addStretch()
        row1.addWidget(self.lbl_time)
        row2 = QHBoxLayout()
        row2.addWidget(self.lbl_sum)
        row2.addStretch()
        row2.addWidget(self.chk_skip)
        row3 = QHBoxLayout()
        row3.addWidget(self.mode, 1)
        row3.addWidget(self.b_export)
        row3.addWidget(self.b_cancel)

        lay = QVBoxLayout()
        lay.addWidget(self.stack, 1)
        lay.addWidget(self.timeline)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addLayout(row3)
        lay.addWidget(self.progress)
        lay.addWidget(self.status)
        central = QWidget()
        central.setLayout(lay)
        self.setCentralWidget(central)

        # Wiring
        self.player.durationChanged.connect(self.timeline.set_duration)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(
            lambda s: self.b_play.setText("Pause" if s == QMediaPlayer.PlayingState else "Play"))
        self.player.errorOccurred.connect(lambda _e, msg: self.status.setText(f"Playback error: {msg}"))
        self.timeline.seek.connect(self.player.setPosition)
        self.timeline.changed.connect(self.on_changed)

        for keys, fn in [
            ("Space", self.toggle_play), ("P", self.preview),
            ("S", lambda: self.timeline.split(self.player.position())),
            ("Delete", lambda: self.timeline.toggle(self.player.position())),
            ("Backspace", lambda: self.timeline.toggle(self.player.position())),
            ("I", lambda: self.timeline.mark_in(self.player.position())),
            ("O", lambda: self.timeline.mark_out(self.player.position())),
            ("Ctrl+Z", self.timeline.undo), ("Ctrl+O", self.open_dialog), ("Ctrl+E", self.export),
            ("Left", lambda: self.nudge(-1000)), ("Right", lambda: self.nudge(1000)),
            ("Shift+Left", lambda: self.nudge(-33)), ("Shift+Right", lambda: self.nudge(33)),
        ]:
            QShortcut(QKeySequence(keys), self, activated=fn)

        self.set_enabled(False)
        if path:
            self.load(path)

    # ---------- loading ----------
    def set_enabled(self, on):
        for w in (self.b_play, self.b_preview, self.b_split, self.b_toggle, self.b_in, self.b_out,
                  self.b_undo, self.b_reset, self.b_export):
            w.setEnabled(on)
        if not self.ffmpeg:
            self.b_export.setEnabled(False)

    def open_dialog(self):
        if self.proc:
            return
        start = os.path.dirname(self.src) if self.src else os.path.expanduser("~/Videos")
        exts = " ".join("*" + e for e in VIDEO_EXTS)
        path, _ = QFileDialog.getOpenFileName(self, "Open video", start, f"Videos ({exts});;All files (*.*)")
        if path:
            self.load(path)

    def load(self, path):
        if not os.path.isfile(path):
            return
        self.src = path
        self.has_audio, self.start_time = probe(self.ffmpeg, path) if self.ffmpeg else (True, 0.0)
        self.scan_keyframes()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.stack.setCurrentIndex(1)
        self.setWindowTitle(f"ClipTrim – {os.path.basename(path)}")
        self.set_enabled(True)
        self.player.pause()  # shows first frame
        if self.ffmpeg:
            self.status.setText("")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls and not self.proc:
            self.load(urls[0].toLocalFile())

    def scan_keyframes(self):
        """Background scan of exact video keyframe times (packet copy, no decoding)."""
        if self.kf_proc:
            self.kf_proc.finished.disconnect()
            self.kf_proc.kill()
            self.kf_proc.waitForFinished(2000)
        self.kf_proc, self.kf_buf, self.kf_found, self.keyframes = None, b"", set(), None
        self.kf_tb = None
        self.timeline.keyframes = []
        if not self.ffmpeg:
            return
        p = QProcess(self)
        p.setProgram(self.ffmpeg)
        # framecrc lists every packet; keyframe lines are the ones without an "F=0x.." flag field.
        p.setArguments(["-hide_banner", "-nostats", "-loglevel", "error", "-copyts", "-i", self.src,
                        "-map", "0:v:0", "-c", "copy", "-f", "framecrc", "-"])
        p.readyReadStandardOutput.connect(self.on_kf_data)
        p.finished.connect(self.on_kf_done)
        self.kf_proc = p
        p.start()

    def on_kf_data(self):
        if not self.kf_proc:
            return
        self.kf_buf += bytes(self.kf_proc.readAllStandardOutput())
        *lines, self.kf_buf = self.kf_buf.split(b"\n")
        for ln in lines:
            if ln.startswith(b"#tb 0:"):
                num, den = ln.split(b":", 1)[1].strip().split(b"/")
                self.kf_tb = int(num) / int(den)
            elif ln.startswith(b"0,") and b"F=0x" not in ln and self.kf_tb:
                try:
                    pts = int(ln.split(b",")[2])
                except (IndexError, ValueError):
                    continue
                self.kf_found.add(max(0.0, (pts * self.kf_tb - self.start_time) * 1000))

    def on_kf_done(self, code, _status):
        self.on_kf_data()
        self.kf_proc = None
        self.keyframes = sorted(self.kf_found) if code == 0 and self.kf_found else None
        self.timeline.keyframes = self.keyframes or []
        self.timeline.update()
        self.on_changed()

    def snap_to_keyframes(self, ranges):
        """Fast mode: move each piece's start forward to a keyframe so removed content can't leak in."""
        if self.kf_proc:
            self.status.setText("Finishing keyframe scan…")
            QApplication.processEvents()
            self.kf_proc.waitForFinished(120000)
            if self.kf_proc:
                self.on_kf_done(1, None)
        kf = self.keyframes
        if not kf:
            return ranges, 0
        out, lost = [], 0
        for s, e in ranges:
            if s <= 1:
                out.append((s, e))
                continue
            i = bisect.bisect_left(kf, s - 1)
            if i >= len(kf) or kf[i] >= e - MIN_PART:
                lost += e - s
                continue
            lost += kf[i] - s
            out.append((kf[i], e))
        return out, lost

    # ---------- playback ----------
    def toggle_play(self):
        if not self.src:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def preview(self):
        ranges = self.timeline.kept_ranges()
        if not self.src or not ranges:
            return
        self.chk_skip.setChecked(True)
        self.player.setPosition(ranges[0][0])
        self.player.play()

    def nudge(self, ms):
        if self.src:
            self.player.setPosition(max(0, min(self.player.position() + ms, self.player.duration())))

    def on_position(self, pos):
        self.timeline.set_position(pos)
        self.lbl_time.setText(f"{fmt(pos)} / {fmt(self.player.duration())}")
        tl = self.timeline
        if (self.chk_skip.isChecked() and self.player.playbackState() == QMediaPlayer.PlayingState
                and tl.segs and not tl.segs[tl.index_at(pos)][2]):
            nxt = tl.next_kept_start(pos)
            if nxt is None:
                self.player.pause()
            elif nxt > pos:
                self.player.setPosition(nxt)

    def on_changed(self):
        tl = self.timeline
        if not tl.duration:
            self.lbl_sum.setText("")
            return
        ranges = tl.kept_ranges()
        kept = sum(e - s for s, e in ranges)
        self.lbl_sum.setText(
            f"{len(tl.segs)} part{'s' if len(tl.segs) != 1 else ''}   ·   "
            f"Keeping {fmt(kept)}   ·   Removing {fmt(tl.duration - kept)}   ·   "
            f"Output joins {len(ranges)} piece{'s' if len(ranges) != 1 else ''}"
            + self._fast_note(ranges))

    def _fast_note(self, ranges):
        if self.mode.currentIndex() != 0 or self.keyframes is None:
            return ""
        snapped, lost = self.snap_to_keyframes(ranges)
        if not lost:
            return ""
        return f"   ·   Fast mode drops {fmt(lost)} to reach keyframes"

    # ---------- export ----------
    def _enc_args(self, out_path):
        a = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
        if self.has_audio:
            a += ["-c:a", "aac", "-b:a", "192k"]
        return a + self._tail(out_path)

    @staticmethod
    def _tail(out_path):
        a = []
        if out_path.lower().endswith((".mp4", ".mov", ".m4v")):
            a += ["-movflags", "+faststart"]
        return a + ["-progress", "pipe:1", "-nostats", out_path]

    def _copy_args(self, s, e, out_path):
        ss = s / 1000 + (0.0005 if s > 0 else 0)  # land on the keyframe at s, not the one before
        return (["-hide_banner", "-y", "-ss", f"{ss:.6f}", "-i", self.src, "-t", f"{(e - s) / 1000:.6f}",
                 "-map", "0:v:0?", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero"]
                + self._tail(out_path))

    def _precise_args(self, ranges, out_path):
        # One seeked input per kept piece; trim/atrim cut by timestamp (exact even on .ts/.mts),
        # input -t is only a loose read bound so ffmpeg doesn't decode to the end of the file.
        args = ["-hide_banner", "-y"]
        for s, e in ranges:
            args += ["-ss", f"{s / 1000:.3f}", "-t", f"{(e - s) / 1000 + 2:.3f}", "-i", self.src]
        n, a = len(ranges), self.has_audio
        parts, labels = [], ""
        for i, (s, e) in enumerate(ranges):
            d = f"{(e - s) / 1000:.3f}"
            parts.append(f"[{i}:v:0]trim=duration={d},setpts=PTS-STARTPTS[v{i}]")
            labels += f"[v{i}]"
            if a:
                parts.append(f"[{i}:a:0]atrim=duration={d},asetpts=PTS-STARTPTS[a{i}]")
                labels += f"[a{i}]"
        fc = ";".join(parts) + ";" + labels + f"concat=n={n}:v=1:a={1 if a else 0}[v]" + ("[a]" if a else "")
        args += ["-filter_complex", fc, "-map", "[v]"] + (["-map", "[a]"] if a else [])
        return args + self._enc_args(out_path)

    def build_jobs(self, ranges, out_path, fast):
        """Returns list of (ffmpeg args, weight_ms)."""
        total = sum(e - s for s, e in ranges)
        if not fast:
            return [(self._precise_args(ranges, out_path), total)]
        if len(ranges) == 1:
            s, e = ranges[0]
            return [(self._copy_args(s, e, out_path), total)]
        self.tmpdir = tempfile.mkdtemp(prefix="cliptrim_")
        jobs, lines = [], []
        for i, (s, e) in enumerate(ranges):
            part = os.path.join(self.tmpdir, f"part{i:03d}.mkv")
            jobs.append((self._copy_args(s, e, part), e - s))
            lines.append("file '" + part.replace("\\", "/").replace("'", "'\\''") + "'")
        lst = os.path.join(self.tmpdir, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        jobs.append((["-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                      "-map", "0", "-c", "copy"] + self._tail(out_path), total))
        return jobs

    def export(self):
        if not self.src or not self.ffmpeg or self.proc:
            return
        ranges = self.timeline.kept_ranges()
        if not ranges:
            QMessageBox.warning(self, "ClipTrim", "Every part is marked as removed – nothing to export.")
            return
        self.player.pause()
        fast = self.mode.currentIndex() == 0
        if fast:
            ranges, _ = self.snap_to_keyframes(ranges)
            if not ranges:
                QMessageBox.warning(self, "ClipTrim", "The kept parts are shorter than the gaps between "
                                    "keyframes. Use Precise mode for this edit.")
                return
        base, ext = os.path.splitext(self.src)
        out_ext = ext if fast else ".mp4"
        tag = "_trim" if len(ranges) == 1 else "_edit"
        default, n = f"{base}{tag}{out_ext}", 2
        while os.path.exists(default):
            default, n = f"{base}{tag}{n}{out_ext}", n + 1
        path, _ = QFileDialog.getSaveFileName(self, "Save video", default,
                                              f"Video (*{out_ext});;All files (*.*)")
        if not path:
            return
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(self.src)):
            QMessageBox.warning(self, "ClipTrim", "Pick a different name than the original file.")
            return

        self.out_path = path
        self.jobs = self.build_jobs(ranges, path, fast)
        self.total_w = sum(w for _, w in self.jobs) or 1
        self.done_w = 0
        self.progress.setValue(0)
        self.progress.show()
        self.b_cancel.show()
        self.b_export.setEnabled(False)
        self.b_open.setEnabled(False)
        self.status.setText("Exporting…")
        self.run_next()

    def run_next(self):
        if not self.jobs:
            self.finish(True)
            return
        args, self.cur_w = self.jobs.pop(0)
        self.err = b""
        self.proc = QProcess(self)
        self.proc.setProgram(self.ffmpeg)
        self.proc.setArguments(args)
        self.proc.readyReadStandardOutput.connect(self.on_progress)
        self.proc.readyReadStandardError.connect(self.on_stderr)
        self.proc.finished.connect(self.on_finished)
        self.proc.start()

    def on_stderr(self):
        if self.proc:
            self.err = (self.err + bytes(self.proc.readAllStandardError()))[-4000:]

    def on_progress(self):
        if not self.proc:
            return
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="ignore")
        for line in data.splitlines():
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    cur = min(int(line.split("=", 1)[1]) / 1000, self.cur_w)
                    self.progress.setValue(int((self.done_w + max(cur, 0)) / self.total_w * 100))
                except ValueError:
                    pass

    def on_finished(self, code, _status):
        self.on_stderr()
        self.proc = None
        if code != 0:
            self.finish(False)
            return
        self.done_w += self.cur_w
        self.run_next()

    def cleanup_tmp(self):
        if self.tmpdir:
            shutil.rmtree(self.tmpdir, ignore_errors=True)
            self.tmpdir = None

    def cancel_export(self):
        if not self.proc and not self.jobs:
            return
        self.jobs = []
        if self.proc:
            self.proc.finished.disconnect()
            self.proc.kill()
            self.proc.waitForFinished(3000)
            self.proc = None
        try:
            os.remove(self.out_path)
        except OSError:
            pass
        self.cleanup_tmp()
        self.reset_export_ui("Export cancelled.")

    def reset_export_ui(self, msg):
        self.progress.hide()
        self.b_cancel.hide()
        self.b_export.setEnabled(True)
        self.b_open.setEnabled(True)
        self.status.setText(msg)

    def finish(self, ok):
        self.cleanup_tmp()
        if ok and os.path.isfile(self.out_path):
            self.progress.setValue(100)
            self.reset_export_ui(f"Saved: {self.out_path}")
            box = QMessageBox(self)
            box.setWindowTitle("ClipTrim")
            box.setText(f"Saved:\n{self.out_path}")
            show = box.addButton("Show in folder", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() == show:
                self.reveal(self.out_path)
        else:
            self.reset_export_ui("Export failed.")
            tail = self.err.decode(errors="ignore").strip().splitlines()[-8:]
            QMessageBox.critical(self, "Export failed", "\n".join(tail) or "ffmpeg returned an error.")

    @staticmethod
    def reveal(path):
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def closeEvent(self, e):
        if self.proc:
            self.cancel_export()
        if self.kf_proc:
            self.kf_proc.kill()
        super().closeEvent(e)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClipTrim")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("ClipTrim")
    app.setStyle("Fusion")
    pal = QPalette()
    for role, c in [(QPalette.Window, "#1e1e22"), (QPalette.WindowText, "#e6e6e6"), (QPalette.Base, "#16161a"),
                    (QPalette.AlternateBase, "#26262b"), (QPalette.Text, "#e6e6e6"), (QPalette.Button, "#2d2d33"),
                    (QPalette.ButtonText, "#e6e6e6"), (QPalette.Highlight, "#4da3ff"),
                    (QPalette.HighlightedText, "#000000"), (QPalette.ToolTipBase, "#2d2d33"),
                    (QPalette.ToolTipText, "#e6e6e6")]:
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    w = ClipTrim(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
