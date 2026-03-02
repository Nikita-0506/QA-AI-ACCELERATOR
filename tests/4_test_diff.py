"""Test 4: Test diff analyzer with sample diff."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.analyzers.diff_analyzer import DiffAnalyzer

def test_diff_analyzer():
    print("=" * 60)
    print("TEST 4: Diff Analyzer")
    print("=" * 60)
    
    # Sample unified diff
    sample_diff = """
--- a/test/LoginSteps.java
+++ b/test/LoginSteps.java
@@ -10,7 +10,7 @@ public class LoginSteps {
     
     @When("I enter valid credentials")
     public void enterCredentials() {
-        String password = "Test@123";
+        String password = "NewPassword@456";
         loginPage.enterUsername("testuser");
         loginPage.enterPassword(password);
     }
"""
    
    try:
        print("\n🔄 Step 1: Parsing unified diff...")
        file_path = "test/LoginSteps.java"
        detail = DiffAnalyzer.parse_unified_diff(sample_diff, file_path)
        print(f"✓ Diff parsed: {file_path}")
        
        print("\n📊 Step 2: Analyzing changes...")
        print(f"  File: {detail.file_path}")
        print(f"  Type: {detail.change_type}")
        print(f"  Summary: {detail.summary}")
        print(f"  Total line changes: {len(detail.line_changes)}")
        
        print("\n📝 Step 3: Detailed line changes...")
        for i, change in enumerate(detail.line_changes, 1):
            print(f"\n  Change {i}:")
            print(f"    Line: {change.line_number}")
            print(f"    Type: {change.change_type}")
            if change.old_content:
                print(f"    Old:  {change.old_content.strip()}")
            if change.new_content:
                print(f"    New:  {change.new_content.strip()}")
        
        print("\n🔄 Step 4: Extracting key changes...")
        key_changes = DiffAnalyzer.extract_key_changes([detail])
        print(f"  Step definition changes: {len(key_changes.get('step_definition_changes', []))}")
        
        for change in key_changes.get('step_definition_changes', []):
            print(f"    → {change['file']} (Line {change['line']})")
            if 'old' in change and 'new' in change:
                print(f"      Before: {change['old']}")
                print(f"      After:  {change['new']}")
        
        print("\n" + "=" * 60)
        if len(detail.line_changes) > 0:
            print("✅ TEST PASSED: Diff analyzer working")
            print("   You can proceed to Test 5")
        else:
            print("⚠️  TEST WARNING: No changes detected")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return False

if __name__ == "__main__":
    test_diff_analyzer()