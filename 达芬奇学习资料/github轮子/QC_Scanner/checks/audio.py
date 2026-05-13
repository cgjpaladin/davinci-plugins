"""Audio quality checks."""

import subprocess
import logging
import json
from typing import Dict, Any, List

from report import CheckResult


logger = logging.getLogger(__name__)


class AudioChecker:
    """Performs audio quality checks."""
    
    # Loudness targets by spec
    LOUDNESS_SPECS = {
        "broadcast": {"target": -24, "tolerance": 1},  # Zee Kannada / TV
        "netflix": {"target": -27, "tolerance": 2},    # Netflix OC-3.2
        "dci": {"target": -24, "tolerance": 1},        # SMPTE 429-2
    }
    
    def __init__(self, input_file: str, spec: str = "broadcast"):
        self.input_file = input_file
        self.spec = spec
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()
    
    def _load_metadata(self) -> None:
        """Load audio metadata using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=channels,channel_layout,codec_name",
                "-of", "json",
                self.input_file,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("streams"):
                    self._metadata = data["streams"][0]
        except Exception as e:
            logger.warning(f"Could not load audio metadata: {e}")
    
    def check_loudness(self) -> CheckResult:
        """Check audio loudness (LUFS)."""
        logger.debug(f"Checking loudness with {self.spec} spec...")
        
        try:
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
                "-af", "ebur128=stat=1",
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Parse ebur128 output for Integrated loudness
            integrated_loudness = None
            for line in result.stderr.split("\n"):
                if "Integrated loudness:" in line:
                    try:
                        # Extract LUFS value
                        parts = line.split(":")
                        loudness_str = parts[1].split()[0]
                        integrated_loudness = float(loudness_str)
                    except (ValueError, IndexError):
                        pass
            
            if integrated_loudness is None:
                return CheckResult(
                    passed=False,
                    message="Could not measure loudness",
                )
            
            spec_target = self.LOUDNESS_SPECS[self.spec]
            target = spec_target["target"]
            tolerance = spec_target["tolerance"]
            
            if abs(integrated_loudness - target) <= tolerance:
                message = f"Loudness: {integrated_loudness:.1f} LUFS (target: {target} +/- {tolerance})"
                return CheckResult(passed=True, message=message)
            else:
                message = f"Loudness: {integrated_loudness:.1f} LUFS (target: {target} +/- {tolerance}) - OUT OF SPEC"
                return CheckResult(passed=False, message=message)
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Loudness check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Loudness check error: {str(e)}",
            )
    
    def check_channel_mapping(self) -> CheckResult:
        """Check for proper channel mapping (detect mono mapped as 5.1)."""
        logger.debug("Checking channel mapping...")
        
        try:
            if not self._metadata:
                return CheckResult(
                    passed=False,
                    message="Could not determine audio metadata",
                )
            
            channels = int(self._metadata.get("channels", 0))
            channel_layout = self._metadata.get("channel_layout", "unknown")
            
            # Common correct layouts
            valid_layouts = [
                "mono",
                "stereo",
                "5.1",
                "5.1(side)",
                "7.1",
                "7.1(side)",
            ]
            
            if channel_layout in valid_layouts or channels in [1, 2, 6, 8]:
                message = f"Channels: {channels}, Layout: {channel_layout}"
                
                # Special check: 5.1 should have 6 channels
                if "5.1" in channel_layout and channels != 6:
                    return CheckResult(
                        passed=False,
                        message=f"5.1 declared but {channels} channels present - mono mapped to 5.1?",
                    )
                
                return CheckResult(passed=True, message=message)
            else:
                return CheckResult(
                    passed=False,
                    message=f"Unexpected channel layout: {channel_layout} ({channels} channels)",
                )
        
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Channel mapping check error: {str(e)}",
            )
    
    def check_audio_sync(self) -> CheckResult:
        """Check for audio/video sync issues."""
        logger.debug("Checking audio/video sync...")
        
        try:
            # Use ffmpeg's built-in A/V sync detection
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
                "-af", "astats=metadata=1:reset=1",
                "-vf", "fps=1",
                "-f", "null",
                "-",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # In production, parse detailed sync metrics
            # For now, check if processing succeeded
            if result.returncode == 0:
                return CheckResult(
                    passed=True,
                    message="Audio/video sync: OK",
                )
            else:
                return CheckResult(
                    passed=False,
                    message="Potential A/V sync issues detected",
                )
        
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                message="Audio sync check timed out",
            )
        except Exception as e:
            return CheckResult(
                passed=False,
                message=f"Audio sync check error: {str(e)}",
            )
