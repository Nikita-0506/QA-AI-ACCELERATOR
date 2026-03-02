"""Parse Cucumber JSON reports."""
import json
from typing import List, Dict, Any
from ..config import ScenarioResult, TestRunSummary, TestStatus


class CucumberJsonParser:
    """Parse Cucumber JSON format."""
    
    @staticmethod
    def parse(json_content: str) -> TestRunSummary:
        """Parse Cucumber JSON and return summary."""
        data = json.loads(json_content) if isinstance(json_content, str) else json_content
        
        scenarios = []
        total_duration_ms = 0
        
        for feature in data:
            feature_name = feature.get("name", "Unknown Feature")
            
            for element in feature.get("elements", []):
                if element.get("type") != "scenario":
                    continue
                    
                scenario_name = element.get("name", "Unknown Scenario")
                tags = [tag["name"] for tag in element.get("tags", [])]
                
                # Calculate status and duration
                steps = element.get("steps", [])
                status = TestStatus.PASSED
                duration_ms = 0
                failing_step = None
                error_message = None
                
                for step in steps:
                    result = step.get("result", {})
                    step_status = result.get("status", "passed")
                    step_duration_ns = result.get("duration", 0)
                    duration_ms += step_duration_ns / 1_000_000  # ns to ms
                    
                    if step_status == "failed":
                        status = TestStatus.FAILED
                        failing_step = f"{step.get('keyword', '')}{step.get('name', '')}"
                        error_message = result.get("error_message", "No error message")
                    elif step_status == "skipped" and status != TestStatus.FAILED:
                        status = TestStatus.SKIPPED
                
                total_duration_ms += duration_ms
                
                scenarios.append(ScenarioResult(
                    name=scenario_name,
                    feature=feature_name,
                    status=status,
                    duration_ms=duration_ms,
                    tags=tags,
                    failing_step=failing_step,
                    error_message=error_message,
                    steps=[{
                        "keyword": s.get("keyword", ""),
                        "name": s.get("name", ""),
                        "status": s.get("result", {}).get("status", ""),
                        "duration_ms": s.get("result", {}).get("duration", 0) / 1_000_000
                    } for s in steps]
                ))
        
        # Count status
        passed = sum(1 for s in scenarios if s.status == TestStatus.PASSED)
        failed = sum(1 for s in scenarios if s.status == TestStatus.FAILED)
        skipped = sum(1 for s in scenarios if s.status == TestStatus.SKIPPED)
        
        return TestRunSummary(
            total=len(scenarios),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_ms=total_duration_ms,
            scenarios=scenarios
        )