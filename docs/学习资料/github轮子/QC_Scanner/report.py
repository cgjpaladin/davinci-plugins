"""QC Report generation and formatting."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single QC check."""
    
    passed: bool
    message: str
    issues: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QCResult:
    """Complete QC scan result."""
    
    file: str
    spec: str
    checks: Dict[str, Dict[str, CheckResult]]
    timestamp: str
    
    def __post_init__(self):
        """Set timestamp after initialization."""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def __init__(self, file: str, spec: str, checks: Dict[str, Dict[str, CheckResult]]):
        self.file = file
        self.spec = spec
        self.checks = checks
        self.timestamp = datetime.now().isoformat()
    
    def has_passed(self) -> bool:
        """Check if all QC checks passed."""
        for category in self.checks.values():
            for check in category.values():
                if isinstance(check, CheckResult) and not check.passed:
                    return False
        return True


class ReportGenerator:
    """Generate QC reports in JSON and terminal formats."""
    
    def __init__(self, result: QCResult):
        self.result = result
    
    def write_json(self, output_path: str) -> None:
        """Write QC result to JSON file."""
        data = {
            "file": self.result.file,
            "spec": self.result.spec,
            "timestamp": self.result.timestamp,
            "passed": self.result.has_passed(),
            "checks": {},
        }
        
        for category, checks in self.result.checks.items():
            data["checks"][category] = {}
            for check_name, check_result in checks.items():
                if isinstance(check_result, CheckResult):
                    data["checks"][category][check_name] = check_result.to_dict()
                else:
                    data["checks"][category][check_name] = check_result
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def print_terminal_report(self) -> None:
        """Print human-readable QC report to terminal."""
        
        print(f"File: {self.result.file}")
        print(f"Spec: {self.result.spec}")
        print(f"Time: {self.result.timestamp}")
        print(f"Status: {'PASS' if self.result.has_passed() else 'FAIL'}")
        print()
        
        for category, checks in self.result.checks.items():
            print(f"{category.upper()} CHECKS")
            print("-" * 70)
            
            for check_name, check_result in checks.items():
                if isinstance(check_result, CheckResult):
                    status = "[PASS]" if check_result.passed else "[FAIL]"
                    print(f"  {check_name.replace('_', ' ').title():30} {status}")
                    if check_result.message:
                        print(f"    {check_result.message}")
                    if check_result.issues:
                        for issue in check_result.issues:
                            print(f"    - {issue}")
                else:
                    print(f"  {check_name}: {check_result}")
            
            print()
