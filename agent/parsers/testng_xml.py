"""Parse TestNG XML reports."""
import xml.etree.ElementTree as ET
from typing import List
from ..config import ScenarioResult, TestRunSummary, TestStatus


class TestNGXmlParser:
    """Parse TestNG XML format."""
    
    @staticmethod
    def parse(xml_content: str) -> TestRunSummary:
        """Parse TestNG XML and return summary."""
        root = ET.fromstring(xml_content)
        
        scenarios = []
        total_duration_ms = 0
        
        for suite in root.findall(".//suite"):
            suite_name = suite.get("name", "Unknown Suite")
            
            for test in suite.findall(".//test"):
                test_name = test.get("name", "Unknown Test")
                
                for class_elem in test.findall(".//class"):
                    for method in class_elem.findall(".//test-method"):
                        if method.get("is-config") == "true":
                            continue
                            
                        method_name = method.get("name", "Unknown Method")
                        status_str = method.get("status", "PASS")
                        duration_str = method.get("duration-ms", "0")
                        
                        try:
                            duration_ms = float(duration_str)
                        except:
                            duration_ms = 0
                            
                        total_duration_ms += duration_ms
                        
                        # Map TestNG status to our enum
                        if status_str == "PASS":
                            status = TestStatus.PASSED
                        elif status_str == "FAIL":
                            status = TestStatus.FAILED
                        else:
                            status = TestStatus.SKIPPED
                        
                        # Get failure info if present
                        error_message = None
                        exception = method.find(".//exception")
                        if exception is not None:
                            message = exception.find(".//message")
                            if message is not None and message.text:
                                error_message = message.text
                        
                        scenarios.append(ScenarioResult(
                            name=method_name,
                            feature=f"{suite_name} / {test_name}",
                            status=status,
                            duration_ms=duration_ms,
                            tags=[],
                            failing_step=None,
                            error_message=error_message,
                            steps=[]
                        ))
        
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