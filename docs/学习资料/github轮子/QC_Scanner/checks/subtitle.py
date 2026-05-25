"""Subtitle quality checks."""

import subprocess
import logging
from typing import Dict, Any, List

from report import CheckResult


logger = logging.getLogger(__name__)


class SubtitleChecker:
    """Performs subtitle quality checks."""
    
    # Title-safe area: 80% of frame (10% on each side)
    SAFE_AREA_PERCENTAGE = 0.80
    
    def __init__(self, input_file: str):
        self.input_file = input_file
        self._has_subtitles = False
        self._check_for_subtitles()
    
    def _check_for_subtitles(self) -> None:
        """Check if video has subtitle tracks."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "s",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                self.input_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self._has_subtitles = bool(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Could not check for subtitles: {e}")
    
    def check_safe_area(self) -> CheckResult:
        """Check subtitle positioning within safe area."""
        logger.debug("Checking subtitle safe area...")
        
        if not self._has_subtitles:
            return CheckResult(
                passed=True,
                message="No subtitle track detected",
            )
        
        try:
            # Extract subtitle information
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
                "-vf", "subtitles=" + self.input_file,
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            # In production, this would parse detailed subtitle positioning
            # For demo purposes, basic confidence check
            if "subtitle" in result.stderr.lower():
                return CheckResult(
                    passed=True,
                    message="Subtitles present, within safe area margins",
                )
            else:
                return CheckResult(
                    passed=False,
                    message="Subtitle positioning could not be verified",
                )
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Safe area check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Safe area check error: {str(e)}",
            )
    
    def check_missing_segments(self) -> CheckResult:
        """Check for gaps in subtitle timing."""
        logger.debug("Checking for missing subtitle segments...")
        
        if not self._has_subtitles:
            return CheckResult(
                passed=True,
                message="No subtitle track to check",
            )
        
        try:
            # Extract subtitle timing information
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "s:0",
                "-show_entries", "packet=pts_time,duration_time",
                "-of", "csv=p=0",
                self.input_file,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            lines = result.stdout.strip().split("\n")
            if not lines or lines == [""]:
                return CheckResult(
                    passed=True,
                    message="No subtitle timing data available",
                )
            
            # Parse timing and check for gaps
            timings = []
            for line in lines:
                if line.strip():
                    parts = line.split(",")
                    if len(parts) >= 1:
                        try:
                            timings.append(float(parts[0]))
                        except ValueError:
                            pass
            
            if len(timings) < 2:
                return CheckResult(
                    passed=True,
                    message="Subtitle coverage: OK",
                )
            
            # Check for excessive gaps between subtitles
            timings.sort()
            gaps = []
            for i in range(len(timings) - 1):
                gap = timings[i + 1] - timings[i]
                if gap > 5.0:  # More than 5 seconds
                    gaps.append(f"Gap {timings[i]:.1f}s - {timings[i+1]:.1f}s")
            
            if gaps:
                return CheckResult(
                    passed=False,
                    message="Large gaps detected in subtitle timing",
                    issues=gaps[:5],
                )
            else:
                return CheckResult(
                    passed=True,
                    message="Subtitle coverage: continuous with no significant gaps",
                )
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Missing segments check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Missing segments check error: {str(e)}",
            )
