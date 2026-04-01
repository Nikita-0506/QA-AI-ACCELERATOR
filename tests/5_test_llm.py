"""Test 5: Test LLM analyzer with Azure OpenAI."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from agent.analyzers.llm_analyzer import LLMAnalyzer

load_dotenv()

def test_llm_analyzer():
    print("=" * 60)
    print("TEST 5: LLM Analyzer")
    print("=" * 60)
    
    try:
        print("\n🔄 Step 1: Initializing LLM Analyzer...")
        analyzer = LLMAnalyzer()
        
        if analyzer.client:
            provider = "Azure OpenAI" if analyzer.is_azure else "OpenAI"
            print(f"✓ LLM Analyzer initialized with {provider}")
            print(f"  Model: {analyzer.model}")
        else:
            print("⚠️  No API keys configured - will use rule-based analysis")
        
        print("\n🔄 Step 2: Preparing sample regression data...")
        sample_regression = {
            "scenario_name": "Login with valid credentials",
            "feature": "User Authentication",
            "error_message": "Element not found: Timeout waiting for selector '#loginButton'",
            "baseline_duration_ms": 2000,
            "current_duration_ms": 8000
        }
        
        sample_key_changes = {
            "step_definition_changes": [
                {
                    "file": "LoginSteps.java",
                    "line": 15,
                    "type": "modified",
                    "old": "String password = \"Test@123\";",
                    "new": "String password = \"WrongPassword@456\";"
                }
            ]
        }
        
        sample_file_changes = [
            {
                "path": "LoginSteps.java",
                "type": "step_definition",
                "summary": "Modified password in login step"
            }
        ]
        
        print("✓ Sample data prepared")
        
        print("\n🔄 Step 3: Analyzing failure...")
        print("  (This may take 5-15 seconds if using LLM)")
        
        analysis = analyzer.analyze_failure_with_context(
            sample_regression,
            sample_key_changes,
            sample_file_changes
        )
        
        print(f"✓ Analysis complete!")
        print(f"\n📊 Analysis Results:")
        print(f"  Type: {analysis.get('analysis_type', 'unknown')}")
        print(f"  Confidence: {analysis.get('confidence', 'N/A')}")
        if 'provider' in analysis:
            print(f"  Provider: {analysis['provider']}")
        if 'model_used' in analysis:
            print(f"  Model: {analysis['model_used']}")
        
        print(f"\n📝 Detailed Explanation:")
        print("-" * 60)
        explanation = analysis.get('detailed_explanation', 'No explanation')
        # Print first 500 characters
        if len(explanation) > 500:
            print(explanation[:500] + "...")
            print(f"\n  ... (truncated, full length: {len(explanation)} characters)")
        else:
            print(explanation)
        print("-" * 60)
        
        print("\n" + "=" * 60)
        if analysis.get('analysis_type') in ['llm_powered', 'rule_based']:
            print("✅ TEST PASSED: LLM Analyzer working")
            if analysis.get('analysis_type') == 'llm_powered':
                print("   🎉 Azure OpenAI is working correctly!")
            print("   You can proceed to Test 6")
        else:
            print("⚠️  TEST WARNING: Unexpected analysis type")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("\n🔧 Troubleshooting:")
        print("  1. Check Azure OpenAI credentials in .env")
        print("  2. Verify deployment name is correct")
        print("  3. Ensure API key has proper permissions")
        print("=" * 60)
        return False

if __name__ == "__main__":
    test_llm_analyzer()