"""Test 3: Test Cucumber JSON parser with sample data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.parsers import CucumberJsonParser

def test_parser():
    print("=" * 60)
    print("TEST 3: Test Report Parser")
    print("=" * 60)
    
    # Sample Cucumber JSON (minimal valid structure)
    sample_json = """
    [
      {
        "name": "Sample Feature",
        "elements": [
          {
            "type": "scenario",
            "name": "Test Scenario 1",
            "tags": [{"name": "@smoke"}],
            "steps": [
              {
                "keyword": "Given ",
                "name": "I am on the login page",
                "result": {
                  "status": "passed",
                  "duration": 1500000000
                }
              },
              {
                "keyword": "When ",
                "name": "I enter credentials",
                "result": {
                  "status": "passed",
                  "duration": 2000000000
                }
              }
            ]
          },
          {
            "type": "scenario",
            "name": "Test Scenario 2",
            "tags": [],
            "steps": [
              {
                "keyword": "Given ",
                "name": "I am logged in",
                "result": {
                  "status": "failed",
                  "duration": 500000000,
                  "error_message": "Element not found: #loginButton"
                }
              }
            ]
          }
        ]
      }
    ]
    """
    
    try:
        print("\n🔄 Step 1: Parsing sample JSON...")
        summary = CucumberJsonParser.parse(sample_json)
        print("✓ JSON parsed successfully")
        
        print("\n📊 Step 2: Analyzing results...")
        print(f"  Total scenarios: {summary.total}")
        print(f"  Passed: {summary.passed}")
        print(f"  Failed: {summary.failed}")
        print(f"  Skipped: {summary.skipped}")
        print(f"  Duration: {summary.duration_ms:.0f}ms")
        
        print("\n📝 Step 3: Checking scenario details...")
        for i, scenario in enumerate(summary.scenarios, 1):
            status_icon = "✅" if scenario.status.value == "passed" else "❌"
            print(f"  {status_icon} Scenario {i}: {scenario.name}")
            print(f"     Feature: {scenario.feature}")
            print(f"     Status: {scenario.status.value}")
            print(f"     Duration: {scenario.duration_ms:.0f}ms")
            if scenario.error_message:
                print(f"     Error: {scenario.error_message}")
        
        print("\n" + "=" * 60)
        if summary.total == 2 and summary.passed == 1 and summary.failed == 1:
            print("✅ TEST PASSED: Parser working correctly")
            print("   You can proceed to Test 4")
        else:
            print("⚠️  TEST WARNING: Unexpected results")
            print(f"   Expected: 2 total, 1 passed, 1 failed")
            print(f"   Got: {summary.total} total, {summary.passed} passed, {summary.failed} failed")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return False

if __name__ == "__main__":
    test_parser()