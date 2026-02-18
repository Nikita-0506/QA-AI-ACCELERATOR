"""Compare test runs."""
from typing import List, Dict, Any
from ..config import TestRunSummary, Regression, TestStatus


class RunComparator:
    """Compare baseline and current test runs."""
    
    @staticmethod
    def find_regressions(
        baseline: TestRunSummary,
        current: TestRunSummary
    ) -> List[Regression]:
        """Find scenarios that regressed (passed → failed)."""
        regressions = []
        
        # Build lookup for baseline scenarios
        baseline_map = {
            (s.feature, s.name): s 
            for s in baseline.scenarios
        }
        
        for curr_scenario in current.scenarios:
            key = (curr_scenario.feature, curr_scenario.name)
            baseline_scenario = baseline_map.get(key)
            
            if baseline_scenario:
                # Check if passed → failed
                if (baseline_scenario.status == TestStatus.PASSED and 
                    curr_scenario.status == TestStatus.FAILED):
                    regressions.append(Regression(
                        scenario_name=curr_scenario.name,
                        feature=curr_scenario.feature,
                        baseline_duration_ms=baseline_scenario.duration_ms,
                        current_duration_ms=curr_scenario.duration_ms,
                        error_message=curr_scenario.error_message
                    ))
        
        return regressions
    
    @staticmethod
    def find_improvements(
        baseline: TestRunSummary,
        current: TestRunSummary
    ) -> List[str]:
        """Find scenarios that improved (failed → passed)."""
        improvements = []
        
        baseline_map = {
            (s.feature, s.name): s 
            for s in baseline.scenarios
        }
        
        for curr_scenario in current.scenarios:
            key = (curr_scenario.feature, curr_scenario.name)
            baseline_scenario = baseline_map.get(key)
            
            if baseline_scenario:
                if (baseline_scenario.status == TestStatus.FAILED and 
                    curr_scenario.status == TestStatus.PASSED):
                    improvements.append(f"{curr_scenario.feature} → {curr_scenario.name}")
        
        return improvements
    
    @staticmethod
    def find_duration_regressions(
        baseline: TestRunSummary,
        current: TestRunSummary,
        threshold_percent: float = 50.0
    ) -> List[Dict[str, Any]]:
        """Find scenarios with significant duration increase."""
        duration_regressions = []
        
        baseline_map = {
            (s.feature, s.name): s 
            for s in baseline.scenarios
        }
        
        for curr_scenario in current.scenarios:
            key = (curr_scenario.feature, curr_scenario.name)
            baseline_scenario = baseline_map.get(key)
            
            if baseline_scenario and baseline_scenario.duration_ms > 0:
                increase_percent = (
                    (curr_scenario.duration_ms - baseline_scenario.duration_ms) / 
                    baseline_scenario.duration_ms * 100
                )
                
                if increase_percent > threshold_percent:
                    duration_regressions.append({
                        "scenario": curr_scenario.name,
                        "feature": curr_scenario.feature,
                        "baseline_ms": baseline_scenario.duration_ms,
                        "current_ms": curr_scenario.duration_ms,
                        "increase_percent": round(increase_percent, 1)
                    })
        
        return duration_regressions