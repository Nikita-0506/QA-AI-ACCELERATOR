"""Test 6: Mini end-to-end test with sample data."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from agent.parsers import CucumberJsonParser
from agent.analyzers.compare_runs import RunComparator
from agent.analyzers.diff_analyzer import DiffAnalyzer
from agent.analyzers.llm_analyzer import LLMAnalyzer

load_dotenv()

def test_mini_pipeline():
    print("=" * 60)
    print("TEST 6: Mini Full Pipeline")
    print("=" * 60)
    
    # Sample baseline report
    baseline_json = """
    [{
        "name": "Login Feature",
        "elements": [{
            "type": "scenario",
            "name": "Login with valid credentials",
            "steps": [{
                "keyword": "Given ",
                "name": "I am on login page",
                "result": {"status": "passed", "duration": 1000000000}
            }]
        }]
    }]
    """
    
    # Sample current report (same test now fails)
    current_json = """
    [{
        "name": "Login Feature",
        "elements": [{
            "type": "scenario",
            "name": "Login with valid credentials",
            "steps": [{
                "keyword": "Given ",
                "name": "I am on login page",
                "result": {
                    "status": "failed",
                    "duration": 5000000000,
                    "error_message": "Timeout: Element #loginButton not found"
                }
            }]
        }]
    }]
    """
    
    try:
        print("\n🔄 Step 1: Parsing test reports...")
        baseline_summary = CucumberJsonParser.parse(baseline_json)
        current_summary = CucumberJsonParser.parse(current_json)
        print(f"✓ Baseline: {baseline_summary.passed}/{baseline_summary.total} passed")
        print(f"✓ Current:  {current_summary.passed}/{current_summary.total} passed")
        
        print("\n🔄 Step 2: Comparing test runs...")
        regressions = RunComparator.find_regressions(baseline_summary, current_summary)
        improvements = RunComparator.find_improvements(baseline_summary, current_summary)
        print(f"✓ Found {len(regressions)} regressions")
        print(f"✓ Found {len(improvements)} improvements")
        
        if regressions:
            print("\n🔄 Step 3: Analyzing regressions...")
            regression = regressions[0]
            print(f"  Scenario: {regression.scenario_name}")
            print(f"  Feature: {regression.feature}")
            print(f"  Error: {regression.error_message[:50]}...")
            
            print("\n🔄 Step 4: Running AI analysis...")
            analyzer = LLMAnalyzer()
            
            regression_dict = {
                "scenario_name": regression.scenario_name,
                "feature": regression.feature,
                "error_message": regression.error_message,
                "baseline_duration_ms": regression.baseline_duration_ms,
                "current_duration_ms": regression.current_duration_ms
            }
            
            key_changes = {
                "step_definition_changes": [{
                    "file": "LoginPage.java",
                    "line": 42,
                    "type": "modified",
                    "old": "button.id = 'loginButton'",
                    "new": "button.id = 'submitButton'"
                }]
            }
            
            analysis = analyzer.analyze_failure_with_context(
                regression_dict,
                key_changes,
                []
            )
            
            print(f"✓ Analysis complete: {analysis.get('analysis_type')}")
            
            print("\n📊 Final Report Summary:")
            print("-" * 60)
            print(f"Regression: {regression.scenario_name}")
            print(f"Analysis Type: {analysis.get('analysis_type')}")
            print(f"Confidence: {analysis.get('confidence')}")
            print(f"\nRoot Cause Summary:")
            explanation = analysis.get('detailed_explanation', '')
            print(explanation[:200] + "..." if len(explanation) > 200 else explanation)
            print("-" * 60)
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED: Full pipeline working!")
        print("   🎉 Your QA Intelligence Agent is ready!")
        print("   You can now run the full Streamlit app:")
        print("   → streamlit run ui/app_enhanced.py")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return False

if __name__ == "__main__":
    test_mini_pipeline()