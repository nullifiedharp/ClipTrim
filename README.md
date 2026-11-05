<p align="center">
  <img src="docs/icon.png" width="96" alt="ClipTrim icon">
</p>

<h1 align="center">ClipTrim</h1>

<p align="center">
  A simple Windows desktop video trimmer and cutter.<br>
  Split a video into parts, delete the parts you don't want, and export the rest joined together.
</p>

<p align="center">
  <a href="https://github.com/nullifiedharp/ClipTrim/releases/latest"><img src="https://img.shields.io/github/v/release/nullifiedharp/ClipTrim?label=download" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="License: GPL v3"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-informational" alt="Platform: Windows 10/11">
  <img src="https://img.shields.io/badge/python-3.10%2B-yellow" alt="Python 3.10+">
</p>

---

## Features

- **Trim:** cut off the start and end with one key each.
- **Cut out sections:** split anywhere, mark parts as removed, and export one clean video without them.
- **Two export modes:**
  - **Precise:** frame-accurate, re-encodes to H.264/AAC MP4.
  - **Fast:** lossless and near-instant, with no re-encode.
- **Preview the result** before exporting. Playback skips the removed parts.
- **Drag and drop** videos onto the window, or right-click a video in Explorer and choose **Edit with ClipTrim**.
- **Keyboard-driven,** with undo.
- **Never touches your original file.**
- **Works with** MP4, MKV, MOV, AVI, WebM, M4V, WMV, FLV, TS, MTS and M2TS.
- **ffmpeg is bundled,** so there's nothing else to install.

## Install

Download **`ClipTrim-Setup-x.y.z.exe`** from the [latest release](https://github.com/nullifiedharp/ClipTrim/releases/latest) and run it.

- It installs for your user account and needs no admin rights. The setup also offers an all-users install.
- It adds a Start menu entry and an optional desktop shortcut.
- It optionally adds **Edit with ClipTrim** to the right-click menu for video files. On Windows 11 this is under **Show more options**.
- You can uninstall it from **Settings → Apps**.
- To upgrade, run a newer setup. It upgrades in place.

> Windows SmartScreen may warn about the installer because it isn't code-signed. Click **More info → Run anyway**.

## How to use

1. Open a video. You can drag it in, press **Ctrl+O**, or right-click it in Explorer and choose **Edit with ClipTrim**.
2. Move the playhead to where a section to delete starts and press **S** to split. Do the same where the section ends.
3. With the playhead inside that section, press **Del** (or right-click it on the timeline). It turns red-hatched, which means it will be removed.
4. Repeat for any other sections. Press **P** to preview the result.
5. Choose an export mode and press **Ctrl+E**.

To trim only the start or end, put the playhead where you want the video to begin and press **I**. Put it where you want it to end and press **O**.

### Keyboard shortcuts

| Key | Action |
|---|---|
| <kbd>S</kbd> | Split at playhead |
| <kbd>Del</kbd> | Remove / restore the part under the playhead |
| <kbd>I</kbd> / <kbd>O</kbd> | Remove everything before / after the playhead |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> | Undo |
| <kbd>P</kbd> | Preview the result from the start |
| <kbd>Space</kbd> | Play / pause |
| <kbd>←</kbd> / <kbd>→</kbd> | Move 1 second |
| <kbd>Shift</kbd>+<kbd>←</kbd> / <kbd>→</kbd> | Move 1 frame |
| <kbd>Ctrl</kbd>+<kbd>O</kbd> | Open |
| <kbd>Ctrl</kbd>+<kbd>E</kbd> | Export |

On the timeline:
- Drag the white split lines to adjust them.
- Removed parts are red-hatched.
- The small ticks along the bottom are keyframes.

### Export modes

| | Precise | Fast |
|---|---|---|
| Accuracy | Exact to the frame | Each kept piece starts at the next keyframe |
| Quality | Re-encoded (H.264, CRF 18, visually lossless) | Untouched original streams |
| Speed | Takes time to encode | Near-instant |
| Output | `.mp4` | Same container as the source |

Fast mode never lets removed footage back in. To make that guarantee, it drops up to one keyframe gap at the start of each kept piece. The summary line under the timeline shows how much will be dropped. For exact cuts, use Precise mode.

## Build from source

You need Windows and Python 3.10 or newer.

```bat
git clone https://github.com/nullifiedharp/ClipTrim.git
cd ClipTrim
```

| Script | What it does |
|---|---|
| `run.bat` | Installs the requirements and runs ClipTrim straight from source. |
| `build.bat` | Builds `dist\ClipTrim\ClipTrim.exe` with ffmpeg bundled, then the installer `installer\ClipTrim-Setup-x.y.z.exe`. If [Inno Setup 6](https://jrsoftware.org/isinfo.php) is missing, it installs it through winget. |

The version number comes from `APP_VERSION` in `cliptrim.py`.

### Project layout

```
cliptrim.py        the app (PySide6 UI + ffmpeg export)
installer.iss      Inno Setup script (Start menu, right-click menu, uninstaller)
build.bat          builds the exe and the installer
run.bat            run from source
requirements.txt   PySide6, imageio-ffmpeg
icon.ico           app icon
```

## Contributing

Bug reports and pull requests are welcome. Please [open an issue](https://github.com/nullifiedharp/ClipTrim/issues) with:
- the video format
- the export mode you used
- the error text, if there was one

## License

ClipTrim is free software, licensed under the **GNU General Public License v3.0 or later**. See [LICENSE](LICENSE).

You can use, study, modify and share it. If you distribute it or anything built from it, you must:
- release the full source code under the same license
- keep the original copyright notice

Copyright © 2026 NullHarp

### Third-party components

| Component | License | Notes |
|---|---|---|
| [FFmpeg](https://ffmpeg.org) | GPL v3 | Bundled `ffmpeg.exe`, taken from [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg). Source is available at [ffmpeg.org](https://ffmpeg.org/download.html). |
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) | LGPL v3 | UI and video playback |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD 2-Clause | Supplies the ffmpeg binary |

FFmpeg is a trademark of Fabrice Bellard. ClipTrim is not affiliated with the FFmpeg project.
