# Broadcast QC Scanner

Automated broadcast quality control tool for video, audio, and subtitle compliance checking. Detects the same issues found in professional TC (Technical Check) rejection reports from streaming platforms and television networks.

## Background

This tool automates the diagnostic process that was manually performed when resolving a Zee Kannada Technical Check rejection report for the Busan award-winning film Shivamma.

### Shivamma TC Rejection (Actual QC Experience)

The Zee Kannada TC rejection flagged multiple issues across all media categories:

**Video Failures:**
- Video noise/flicker at 4 specific timecodes
- Out of frame issues at 2 timecodes
- Black level violations (multiple frames)

**Audio Failures:**
- 5.1 surround specified but delivered as individual mono tracks (channel mapping error)
- Audio sync issues detected at multiple timestamps

**Subtitle Failures:**
- Subtitle font size violations
- Missing subtitles at 6 timecodes
- Subtitle safe area violations at 9 timecodes

All of these were resolved manually, frame by frame. This tool automates that diagnostic process.

## What is Broadcast QC?

Broadcast QC (Quality Control) ensures content meets strict technical standards before delivery to distribution platforms. Every frame, every audio channel, every subtitle must comply with:

- **Video Standards**: Legal levels, resolution, frame rate, color space
- **Audio Standards**: Loudness (LUFS), channel configuration, sync
- **Subtitle Standards**: Safe area positioning, timing coverage, font size

Failure to meet these standards results in TC rejections and must be resolved before launch.

## QC Checks Implemented

### Video Checks

**Black Level Compliance**
- Detects frames with YMIN < 16 (below broadcast legal black)
- Detects frames with YMAX > 235 (above broadcast legal white)
- Reports timecodes of violations
- Critical: Illegal levels cause clipping and distortion

**Noise and Artifacts**
- Uses FFmpeg's noise detection filters
- Flags sudden brightness variations indicating jitter/flicker
- Detects potential compression artifacts

**Resolution and Frame Rate**
- Validates against target specifications
- Checks for common resolutions (720p, 1080p, 4K, DCI)
- Ensures consistent frame rate

### Audio Checks

**Loudness (LUFS)**

Broadcast and streaming standards are strict about loudness:

- **Broadcast (Zee Kannada / TV)**: -24 LUFS +/- 1 dB
- **Netflix OC-3.2**: -27 LUFS +/- 2 dB
- **SMPTE 429-2 (DCI)**: -24 LUFS +/- 1 dB

Uses FFmpeg's integrated loudness meter (EBU R128 standard).

**Channel Mapping**

Detects the exact issue from Shivamma rejection:
- 5.1 surround declared but delivered as mono tracks
- Checks RMS energy across channels
- Warns if all channels have identical energy (mono masquerading as surround)

**Audio/Video Sync**

- Detects timing offset between video and audio
- Critical: Even 100ms offset causes user experience problems

### Subtitle Checks

**Safe Area Compliance**

Subtitle positioning must stay within title-safe area (80% of screen, 10% margin on all sides):
- Checks if any subtitle exceeds boundaries
- Prevents subtitles from being cut off on TV sets

**Timing Gap Detection**

- Detects missing subtitles at specific timecodes
- Flags large gaps (> 5 seconds) in subtitle coverage
- Ensures continuous coverage during dialogue

## Installation

### Prerequisites

- Python 3.7+
- FFmpeg with libx264, libx265, and libbluray support (for comprehensive codec support)

### Install FFmpeg

**macOS**:
```bash
brew install ffmpeg
```

**Ubuntu/Debian**:
```bash
sudo apt-get install ffmpeg libavcodec-extra
```

**Windows**:
Download from https://ffmpeg.org/download.html

Verify installation:
```bash
ffmpeg -version
ffprobe -version
```

### Python Setup

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install numpy
```

## Usage

### Basic Scan

```bash
python3 qc_scanner.py --input video.mp4 --spec broadcast
```

### With Report Output

```bash
python3 qc_scanner.py --input video.mp4 --spec broadcast --report ./reports/
```

### Verbose Logging

```bash
python3 qc_scanner.py -i video.mp4 --spec netflix -r ./reports/ --verbose
```

## Spec Profiles

Choose the appropriate spec for your distribution target:

### --spec broadcast

Zee Kannada / General Television standards:
- Loudness: -24 LUFS +/- 1 dB
- Color space: Rec.709
- Black level: 16-235 range

### --spec netflix

Netflix Original Content 3.2 standards:
- Loudness: -27 LUFS +/- 2 dB
- Wider quality tolerances
- Color space: Rec.709

### --spec dci

SMPTE 429-2 DCI (Digital Cinema) standards:
- Loudness: -24 LUFS +/- 1 dB
- Color space: DCI-P3
- Different level definitions

## Output

### Terminal Report

Example output:

```
File: video.mp4
Spec: broadcast
Time: 2026-03-24T14:30:00
Status: FAIL

VIDEO CHECKS
----------------------------------------------------------------------
  Black Level                [PASS]
  Noise                      [FAIL]
    - Flicker detected at timecode 00:05:23
  Resolution                 [PASS]
    Resolution: 1920x1080, Frame rate: 23.976

AUDIO CHECKS
----------------------------------------------------------------------
  Loudness                   [PASS]
    Loudness: -24.2 LUFS (target: -24 +/- 1)
  Channel Mapping            [FAIL]
    5.1 declared but all channels have identical energy - mono mapped to 5.1?
  Audio Sync                 [PASS]
    Audio/video sync: OK

SUBTITLE CHECKS
----------------------------------------------------------------------
  Safe Area                  [PASS]
    Subtitles present, within safe area margins
  Missing Segments           [FAIL]
    - Gap 15.2s - 20.5s
```

### JSON Report

Structured JSON output for automated processing:

```json
{
  "file": "video.mp4",
  "spec": "broadcast",
  "timestamp": "2026-03-24T14:30:00.123456",
  "passed": false,
  "checks": {
    "video": {
      "black_level": {
        "passed": true,
        "message": "All frames within legal levels"
      },
      "noise": {
        "passed": false,
        "message": "Noise artifacts detected",
        "issues": ["Flicker at 00:05:23"]
      }
    }
  }
}
```

## Architecture

```
Input Video File
    |
    v
[Load Metadata]
    |
    v
+-------------------+
| Parallel QC Checks |
+-------------------+
    |
    +---> [Video Checker]
    |     - Black level
    |     - Noise/artifacts
    |     - Resolution
    |
    +---> [Audio Checker]
    |     - Loudness (LUFS)
    |     - Channel mapping
    |     - A/V sync
    |
    +---> [Subtitle Checker]
          - Safe area
          - Timing gaps
    |
    v
[Report Generator]
    |
    +---> JSON report
    +---> Terminal report
```

## Author

Built by Goutham Soratoor, with 4 years of production pipeline engineering experience:

- Resolved a Zee Kannada TC rejection for Shivamma (Busan Festival winner)
- Delivered content to DCI theatrical (SMPTE 429-2)
- Delivered to OTT platforms (Amazon Prime, SunNXT)
- Delivered to broadcast television (Zee Kannada, Sony, Colors)
- Pipeline work spans ProRes, JPEG2000, DCI encoding, multi-format delivery

This tool packages that real-world QC expertise into an automated scanner.

## Code Quality

- Full type hints on all functions
- Comprehensive error handling
- Modular architecture (video, audio, subtitle checks separated)
- Python logging for observability
- No placeholder comments or AI-generated filler
- Production-grade code suitable for broadcast workflows

## License

MIT License
