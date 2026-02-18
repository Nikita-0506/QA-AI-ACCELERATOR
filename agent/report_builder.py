"""Build intelligence report."""
import json
from typing import List, Dict, Any
from .config import (
    IntelligenceReport, 
    FileChange, 
    ChangeType,
    LocatorChange,
    Regression
)


class ReportBuilder:
    """Build and export intelligence reports."""
    
    @staticmethod
    def generate_ai_insights(
        regressions: List[Regression],
        file_changes: List[FileChange],
        locator_changes: List[LocatorChange]
    ) -> Dict[str, Any]:
        """Generate simple rule-based insights (enhance with LLM later)."""
        insights = {
            "classification": "Unknown",
            "confidence": 0.0,
            "explanation": "",
            "recommended_actions": []
        }
        
        if not regressions:
            insights["classification"] = "No regressions detected"
            insights["confidence"] = 1.0
            insights["explanation"] = "All tests passed or maintained previous state."
            return insights
        
        # Count change types
        has_locator_changes = any(fc.change_type == ChangeType.LOCATOR for fc in file_changes)
        has_feature_changes = any(fc.change_type == ChangeType.FEATURE for fc in file_changes)
        has_stepdef_changes = any(fc.change_type == ChangeType.STEP_DEFINITION for fc in file_changes)
        has_page_changes = any(fc.change_type == ChangeType.PAGE_OBJECT for fc in file_changes)
        
        # Rule-based classification
        if has_locator_changes and locator_changes:
            insights["classification"] = "Likely locator issue"
            insights["confidence"] = 0.75
            insights["explanation"] = (
                f"Found {len(locator_changes)} locator changes and {len(regressions)} regressions. "
                "Changed locators may have broken element identification."
            )
            insights["recommended_actions"] = [
                "Review changed locator values",
                "Verify elements are still locatable in the UI",
                "Consider updating to stable locators (ID, data-testid)"
            ]
        elif has_feature_changes and not has_stepdef_changes:
            insights["classification"] = "Test specification change"
            insights["confidence"] = 0.7
            insights["explanation"] = (
                f"Feature files changed but step definitions did not. "
                f"New/changed scenarios may need implementation."
            )
            insights["recommended_actions"] = [
                "Check if new steps are implemented",
                "Review changed scenario expectations"
            ]
        elif has_stepdef_changes or has_page_changes:
            insights["classification"] = "Test code change"
            insights["confidence"] = 0.65
            insights["explanation"] = (
                "Step definitions or page objects changed. "
                "Logic changes may have introduced bugs."
            )
            insights["recommended_actions"] = [
                "Review test code changes",
                "Check for typos or logic errors"
            ]
        else:
            insights["classification"] = "Possible application or environment issue"
            insights["confidence"] = 0.5
            insights["explanation"] = (
                f"Found {len(regressions)} regressions but no obvious test code changes. "
                "Could be application changes, environment issues, or test flakiness."
            )
            insights["recommended_actions"] = [
                "Check if application was deployed",
                "Verify test environment stability",
                "Re-run tests to check for flakiness"
            ]
        
        return insights
    
    @staticmethod
    def build_report(
        repo_url: str,
        baseline_commit: str,
        current_commit: str,
        baseline_summary,
        current_summary,
        commits: List[Dict[str, str]],
        file_changes: List[FileChange],
        locator_changes: List[LocatorChange],
        regressions: List[Regression],
        improvements: List[str],
        duration_regressions: List[Dict[str, Any]]
    ) -> IntelligenceReport:
        """Build complete intelligence report."""
        ai_insights = ReportBuilder.generate_ai_insights(
            regressions, file_changes, locator_changes
        )
        
        return IntelligenceReport(
            repo_url=repo_url,
            baseline_commit=baseline_commit,
            current_commit=current_commit,
            baseline_summary=baseline_summary,
            current_summary=current_summary,
            commits=commits,
            file_changes=file_changes,
            locator_changes=locator_changes,
            regressions=regressions,
            improvements=improvements,
            duration_regressions=duration_regressions,
            ai_insights=ai_insights
        )
    
    @staticmethod
    def to_json(report: IntelligenceReport) -> str:
        """Convert report to JSON."""
        def default_serializer(obj):
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            elif hasattr(obj, 'value'):  # For enums
                return obj.value
            return str(obj)
        
        return json.dumps(report, default=default_serializer, indent=2)