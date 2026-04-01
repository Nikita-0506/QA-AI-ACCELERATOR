"""Configuration and models for the agent."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ChangeType(Enum):
    """Types of code changes."""
    LOCATOR = "locator"
    FEATURE = "feature"
    STEP_DEFINITION = "step_definition"
    PAGE_OBJECT = "page_object"
    CONFIG = "config"
    UTILITY = "utility"
    OTHER = "other"


class TestStatus(Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class ScenarioResult:
    """Individual scenario result."""
    name: str
    feature: str
    status: TestStatus
    duration_ms: float
    tags: List[str] = field(default_factory=list)
    failing_step: Optional[str] = None
    error_message: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TestRunSummary:
    """Summary of a test run."""
    total: int
    passed: int
    failed: int
    skipped: int
    duration_ms: float
    scenarios: List[ScenarioResult]


@dataclass
class LocatorChange:
    """Change detected in locators."""
    key: str
    old_value: Optional[str]
    new_value: Optional[str]
    change_type: str  # "added", "removed", "modified"


@dataclass
class FileChange:
    """File change information."""
    path: str
    change_type: ChangeType
    additions: int
    deletions: int
    diff: Optional[str] = None


@dataclass
class Regression:
    """Test regression (passed → failed)."""
    scenario_name: str
    feature: str
    baseline_duration_ms: float
    current_duration_ms: float
    error_message: Optional[str]
    likely_cause: Optional[str] = None


@dataclass
class IntelligenceReport:
    """Complete intelligence report."""
    repo_url: str
    baseline_commit: str
    current_commit: str
    baseline_summary: TestRunSummary
    current_summary: TestRunSummary
    commits: List[Dict[str, str]]
    file_changes: List[FileChange]
    locator_changes: List[LocatorChange]
    regressions: List[Regression]
    improvements: List[str]
    duration_regressions: List[Dict[str, Any]]
    ai_insights: Dict[str, Any]