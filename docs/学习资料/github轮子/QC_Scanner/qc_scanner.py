#!/usr/bin/env python3
"""
Broadcast QC Scanner - Automated video, audio, and subtitle quality control.

This tool automates the diagnostic process for broadcast quality control,
detecting the same issues found in professional broadcast TC (Technical Check)
rejection reports from streaming platforms and television networks.

Author: Goutham Soratoor
GitHub: https://github.com/GouthamUKS
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from checks.video import VideoChecker
from checks.audio import AudioChecker
from checks.subtitle import SubtitleChecker
from report import ReportGenerator, QCResult


logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the QC scanner."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def verify_ffmpeg_available() -> bool:
    """Verify FFmpeg and ffprobe are available."""
    import subprocess
    
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run(
                [tool, "-version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return True


def validate_input_file(input_path: str) -> Path:
    """Validate that input file exists and is readable."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    return path


def run_qc_scan(
    input_file: str,
    spec: str,
    output_dir: Optional[str] = None,
    verbose: bool = False,
) -> bool:
    """Execute full QC scan on video file."""
    
    input_path = validate_input_file(input_file)
    
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path(".")
    
    logger.info(f"Starting QC scan: {input_path}")
    logger.info(f"Spec profile: {spec}")
    
    result = QCResult(
        file=str(input_path),
        spec=spec,
        checks={},
    )
    
    # Video checks
    logger.info("Running video checks...")
    video_checker = VideoChecker(str(input_path))
    result.checks["video"] = {
        "black_level": video_checker.check_black_level(),
        "noise": video_checker.check_noise_artifacts(),
        "resolution": video_checker.check_resolution(),
    }
    
    # Audio checks
    logger.info("Running audio checks...")
    audio_checker = AudioChecker(str(input_path), spec)
    result.checks["audio"] = {
        "loudness": audio_checker.check_loudness(),
        "channel_mapping": audio_checker.check_channel_mapping(),
        "sync": audio_checker.check_audio_sync(),
    }
    
    # Subtitle checks
    logger.info("Running subtitle checks...")
    subtitle_checker = SubtitleChecker(str(input_path))
    result.checks["subtitle"] = {
        "safe_area": subtitle_checker.check_safe_area(),
        "missing_segments": subtitle_checker.check_missing_segments(),
    }
    
    # Generate reports
    report_gen = ReportGenerator(result)
    
    # JSON report
    json_file = output_path / f"{input_path.stem}_qc_report.json"
    report_gen.write_json(str(json_file))
    logger.info(f"JSON report: {json_file}")
    
    # Terminal report
    print("\n" + "="*70)
    print("QC SCAN REPORT")
    print("="*70)
    report_gen.print_terminal_report()
    
    return result.has_passed()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Broadcast QC scanner - automated video, audio, subtitle compliance checking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Spec profiles:
  broadcast    Zee Kannada / general TV: -24 LUFS, Rec.709
  netflix      Netflix OC-3.2: -27 LUFS, wider tolerances
  dci          SMPTE 429-2: DCI-P3, different levels

Examples:
  %(prog)s --input video.mp4 --spec broadcast --report ./reports/
  %(prog)s -i content.mov --spec netflix
        """,
    )
    
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input video file path",
    )
    parser.add_argument(
        "--spec",
        default="broadcast",
        choices=["broadcast", "netflix", "dci"],
        help="Spec profile for QC thresholds (default: broadcast)",
    )
    parser.add_argument(
        "--report",
        "-r",
        help="Output directory for JSON report",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    
    if not verify_ffmpeg_available():
        logger.error("FFmpeg/ffprobe not found. Please install FFmpeg.")
        return 1
    
    try:
        success = run_qc_scan(
            args.input,
            args.spec,
            args.report,
            args.verbose,
        )
        return 0 if success else 1
    except Exception as e:
        logger.error(f"QC scan failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
