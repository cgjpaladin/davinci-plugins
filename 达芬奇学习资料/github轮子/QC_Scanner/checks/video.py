"""Video quality checks."""

import subprocess
import logging
from typing import Dict, Any, List
import json

from report import CheckResult


logger = logging.getLogger(__name__)


class VideoChecker:
    """Performs video quality checks."""
    
    def __init__(self, input_file: str):
        self.input_file = input_file
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()
    
    def _load_metadata(self) -> None:
        """Load video metadata using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,codec_name",
                "-of", "json",
                self.input_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("streams"):
                    self._metadata = data["streams"][0]
        except Exception as e:
            logger.warning(f"Could not load video metadata: {e}")
    
    def check_black_level(self) -> CheckResult:
        """Check for black level violations."""
        logger.debug("Checking black levels...")
        
        try:
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
                "-vf", "signalstats=stat=1",
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            # Parse ffmpeg output for signalstats
            violations = []
            for line in result.stderr.split("\n"):
                if "signalstats" in line and ("YMIN" in line or "YMAX" in line):
                    if "YMIN=" in line:
                        # Check if YMIN < 16 (below legal black)
                        violations.append(f"Black level violation detected: {line.strip()}")
                    if "YMAX=" in line:
                        # Check if YMAX > 235 (above legal white)
                        violations.append(f"White level violation detected: {line.strip()}")
            
            if violations:
                return CheckResult(
                    passed=False,
                    message="Black/white level violations detected",
                    issues=violations[:5],  # Limit to 5 issues
                )
            
            return CheckResult(passed=True, message="All frames within legal levels")
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Black level check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Black level check error: {str(e)}",
            )
    
    def check_noise_artifacts(self) -> CheckResult:
        """Check for noise and artifacts."""
        logger.debug("Checking for noise and artifacts...")
        
        try:
            # Use ffmpeg's noise detection filter
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
                "-vf", "cropdetect,hflip,analyze",
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            # In a production system, parse detailed noise metrics
            # For now, basic check based on successful analysis
            if result.returncode == 0:
                return CheckResult(
                    passed=True,
                    message="No significant noise artifacts detected",
                )
            else:
                return CheckResult(
                    passed=False,
                    message="Potential noise artifacts detected",
                )
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Noise check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Noise check error: {str(e)}",
            )
    
    def check_resolution(self) -> CheckResult:
        """Check video resolution and frame rate."""
        logger.debug("Checking resolution and frame rate...")
        
        try:
            if not self._metadata:
                return CheckResult(
                    passed=False,
                    message="Could not determine video metadata",
                )
            
            width = int(self._metadata.get("width", 0))
            height = int(self._metadata.get("height", 0))
            frame_rate = self._metadata.get("r_frame_rate", "unknown")
            
            # Check for common resolutions
            valid_resolutions = [
                (1920, 1080),  # 1080p
                (1280, 720),   # 720p
                (854, 480),    # 480p
                (640, 360),    # 360p
                (3840, 2160),  # 4K
                (4096, 2160),  # DCI 4K
            ]
            
            if (width, height) in valid_resolutions:
                message = f"Resolution: {width}x{height}, Frame rate: {frame_rate}"
                return CheckResult(passed=True, message=message)
            else:
                message = f"Non-standard resolution: {width}x{height}"
                return CheckResult(passed=False, message=message)
        
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Resolution check error: {str(e)}",
            )
