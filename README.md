# ClipTrim 1.1

Simple desktop video trimmer and cutter. Split a video into parts, remove the ones you don't want, and export the rest joined together.

## Install
1. Double-click **build.bat** (needs Python 3.10+). It:
   - installs the Python packages
   - builds `ClipTrim.exe` with ffmpeg bundled
   - installs Inno Setup through winget if it's missing
   - produces **installer\ClipTrim-Setup-1.1.0.exe**
2. Run the setup. It installs for your user (no admin needed) and adds:
   - a Start menu entry
   - an optional desktop shortcut
   - **Edit with ClipTrim** on the right-click menu for video files (on Windows 11, under *Show more options*)
   - an uninstaller in Settings → Apps

Re-running a newer setup upgrades in place.

To run without installing, double-click `run.bat`.

## Editing
| Key | Action |
|---|---|
| **S** | Split at playhead |
| **Del** | Remove / restore the part under the playhead (or right-click it on the timeline) |
| **I** / **O** | Remove everything before / after the playhead (quick trim) |
| **Ctrl+Z** | Undo |
| **P** | Preview the result from the start, skipping removed parts |
| **Space** | Play / pause |
| **← →** | Move 1 s (hold **Shift** to move 1 frame) |
| **Ctrl+O** / **Ctrl+E** | Open / Export |

On the timeline, removed parts are red-hatched. You can drag the white split lines to adjust them. The small ticks along the bottom are keyframes.

## Export modes
- **Precise:** re-encodes to H.264/AAC MP4 and is frame-accurate. Use this for exact cuts.
- **Fast:** no re-encode, so it's lossless and near-instant. Each kept piece starts at the next keyframe, so removed footage never sneaks back in, but up to one keyframe gap at the start of each piece is dropped. The summary line shows how much. Each piece's end can also run a few frames long.

The original file is never modified.
