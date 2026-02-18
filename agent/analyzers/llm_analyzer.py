"""LLM-powered analysis of test failures and code changes."""
import os
import json
from typing import Dict, Any, List
from openai import OpenAI, AzureOpenAI


class LLMAnalyzer:
    """Use LLM to provide human-friendly analysis."""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI or Azure OpenAI API key."""
        
        # Check for Azure OpenAI configuration first
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_key = os.getenv("AZURE_OPENAI_KEY")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        
        if azure_endpoint and azure_key and azure_deployment:
            # Use Azure OpenAI
            print(f"🔵 Using Azure OpenAI: {azure_endpoint}")
            print(f"📦 Deployment: {azure_deployment}")
            
            self.client = AzureOpenAI(
                api_key=azure_key,
                api_version=azure_api_version or "2024-12-01-preview",
                azure_endpoint=azure_endpoint
            )
            self.model = azure_deployment
            self.is_azure = True
            
        else:
            # Fallback to standard OpenAI
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if self.api_key:
                print("🟢 Using Standard OpenAI")
                self.client = OpenAI(api_key=self.api_key)
                self.model = "gpt-4-turbo-preview"
                self.is_azure = False
            else:
                print("⚪ No API keys found - using rule-based analysis")
                self.client = None
                self.model = None
                self.is_azure = False
    
    def analyze_failure_with_context(
        self,
        regression: Dict[str, Any],
        key_changes: Dict[str, Any],
        file_changes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze test failure with full context using LLM."""
        
        if not self.client:
            return self._fallback_analysis(regression, key_changes)
        
        # Build context for LLM
        prompt = self._build_analysis_prompt(regression, key_changes, file_changes)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert QA test automation engineer analyzing test failures. Provide clear, actionable insights about why tests failed based on code changes. Be specific about line numbers, what changed, and the likely impact. Explain in simple terms that both technical and non-technical team members can understand."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            analysis_text = response.choices[0].message.content
            
            return {
                "analysis_type": "llm_powered",
                "detailed_explanation": analysis_text,
                "confidence": "high",
                "model_used": self.model,
                "provider": "Azure OpenAI" if self.is_azure else "OpenAI"
            }
            
        except Exception as e:
            print(f"LLM analysis failed: {e}")
            return self._fallback_analysis(regression, key_changes)
    
    def _build_analysis_prompt(
        self,
        regression: Dict[str, Any],
        key_changes: Dict[str, Any],
        file_changes: List[Dict[str, Any]]
    ) -> str:
        """Build detailed prompt for LLM analysis."""
        
        error_msg = regression.get('error_message', 'No error message')
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        
        scenario_name = regression.get('scenario_name', 'Unknown')
        feature_name = regression.get('feature', 'Unknown')
        baseline_duration = regression.get('baseline_duration_ms', 0)
        current_duration = regression.get('current_duration_ms', 0)
        
        prompt_parts = []
        prompt_parts.append("## Test Failure Analysis Request")
        prompt_parts.append("")
        prompt_parts.append("### Failed Test")
        prompt_parts.append(f"- **Scenario**: {scenario_name}")
        prompt_parts.append(f"- **Feature**: {feature_name}")
        prompt_parts.append("- **Error Message**:")
        prompt_parts.append("```")
        prompt_parts.append(error_msg)
        prompt_parts.append("```")
        prompt_parts.append(f"- **Duration**: Baseline {baseline_duration:.0f}ms → Current {current_duration:.0f}ms")
        prompt_parts.append("")
        prompt_parts.append("### Code Changes Detected")
        prompt_parts.append("")
        
        # Add feature file changes
        if key_changes.get('feature_changes'):
            prompt_parts.append("#### Feature File Changes:")
            for change in key_changes['feature_changes'][:5]:
                line_num = change.get('line', 'unknown')
                change_type = change.get('type', 'unknown')
                old_content = change.get('old', '')
                new_content = change.get('new', '')
                
                if change_type == 'modified':
                    prompt_parts.append(f"- Line {line_num}: Changed from `{old_content}` to `{new_content}`")
                elif change_type == 'added':
                    prompt_parts.append(f"- Line {line_num}: Added `{new_content}`")
                elif change_type == 'removed':
                    prompt_parts.append(f"- Line {line_num}: Removed `{old_content}`")
            prompt_parts.append("")
        
        # Add step definition changes
        if key_changes.get('step_definition_changes'):
            prompt_parts.append("#### Step Definition Changes:")
            for change in key_changes['step_definition_changes'][:5]:
                file_path = change.get('file', 'unknown')
                line_num = change.get('line', 'unknown')
                change_type = change.get('type', 'unknown')
                old_content = change.get('old', '')
                new_content = change.get('new', '')
                
                prompt_parts.append(f"- {file_path} (Line {line_num}):")
                if change_type == 'modified':
                    if old_content and new_content:
                        prompt_parts.append(f"  - Before: `{old_content}`")
                        prompt_parts.append(f"  - After: `{new_content}`")
                elif change_type == 'added':
                    prompt_parts.append(f"  - Added: `{new_content}`")
            prompt_parts.append("")
        
        # Add locator changes
        if key_changes.get('locator_changes'):
            prompt_parts.append("#### Locator Changes:")
            for change in key_changes['locator_changes']:
                line_num = change.get('line', 'unknown')
                change_type = change.get('type', 'unknown')
                old_content = change.get('old', '')
                new_content = change.get('new', '')
                
                if change_type == 'modified':
                    prompt_parts.append(f"- Line {line_num}: `{old_content}` → `{new_content}`")
            prompt_parts.append("")
        
        prompt_parts.append("### Please provide:")
        prompt_parts.append("")
        prompt_parts.append("1. **Root Cause Analysis**: What exactly changed and why did it break the test?")
        prompt_parts.append("2. **Detailed Explanation**: Explain the connection between the code changes and the test failure in simple terms")
        prompt_parts.append("3. **Specific Lines**: Reference specific line numbers and explain what each change did")
        prompt_parts.append("4. **Impact**: How did these changes cause the observed behavior?")
        prompt_parts.append("5. **Fix Recommendations**: Concrete steps to fix the issue")
        prompt_parts.append("6. **Prevention**: How to prevent similar issues in the future")
        prompt_parts.append("")
        prompt_parts.append("Use clear, conversational language. Assume the reader understands testing concepts but may not know this specific codebase.")
        
        return "\n".join(prompt_parts)
    
    def _fallback_analysis(self, regression: Dict[str, Any], key_changes: Dict[str, Any]) -> Dict[str, Any]:
        """Provide rule-based analysis when LLM is not available."""
        
        explanation_parts = []
        
        # Analyze error message
        error_msg = regression.get('error_message', '').lower()
        
        if 'timeout' in error_msg:
            explanation_parts.append(
                "🕒 **Timeout Issue Detected**: The test waited for something that never happened. "
                "This usually means an expected element didn't appear or a page didn't load."
            )
        
        if 'assertion' in error_msg:
            explanation_parts.append(
                "❌ **Assertion Failure**: The test expected one thing but found another. "
                "This indicates the application behavior changed or the test expectations are wrong."
            )
        
        # Analyze changes
        if key_changes.get('feature_changes'):
            num_changes = len(key_changes['feature_changes'])
            explanation_parts.append(
                f"\n📝 **Feature File Changes**: {num_changes} changes in test scenarios. "
                "The test steps or test data may have been modified."
            )
            
            # Show specific changes
            for change in key_changes['feature_changes'][:3]:
                change_type = change.get('type', 'unknown')
                old_content = change.get('old', '')
                new_content = change.get('new', '')
                line_num = change.get('line', 'unknown')
                
                if change_type == 'modified' and old_content and new_content:
                    explanation_parts.append(
                        f"  - Line {line_num}: Changed test input from "
                        f"'{old_content.strip()}' to '{new_content.strip()}'"
                    )
        
        if key_changes.get('step_definition_changes'):
            num_changes = len(key_changes['step_definition_changes'])
            explanation_parts.append(
                f"\n🔧 **Step Definition Changes**: {num_changes} changes in test implementation. "
                "The way tests interact with the application has been modified."
            )
        
        # Provide recommendations
        recommendations = []
        
        # Check for password-related issues
        password_in_error = 'password' in error_msg.lower()
        password_in_changes = False
        for changes in key_changes.values():
            if isinstance(changes, list):
                for c in changes:
                    old_val = str(c.get('new', '') or c.get('old', '')).lower()
                    if 'password' in old_val:
                        password_in_changes = True
                        break
        
        if password_in_error or password_in_changes:
            recommendations.append(
                "🔐 Check if the password was changed in the test. "
                "Verify it matches the expected credentials."
            )
        
        if 'timeout' in error_msg:
            recommendations.append(
                "⏱️ Increase timeout values if the application legitimately needs more time, "
                "or investigate why the expected element/page isn't loading."
            )
            recommendations.append(
                "🔍 Check browser console and network logs for errors during test execution."
            )
        
        explanation = "\n\n".join(explanation_parts)
        if recommendations:
            explanation += "\n\n### 💡 Recommended Actions:\n" + "\n".join(recommendations)
        
        return {
            "analysis_type": "rule_based",
            "detailed_explanation": explanation,
            "confidence": "medium"
        }
    
    def generate_summary_report(
        self,
        regressions: List[Dict[str, Any]],
        analyses: List[Dict[str, Any]],
        overall_context: Dict[str, Any]
    ) -> str:
        """Generate a comprehensive summary report."""
        
        if not self.client or not regressions:
            return self._generate_simple_summary(regressions, overall_context)
        
        commits = overall_context.get('commits', [])
        commits_str = json.dumps(commits, indent=2)
        if len(commits_str) > 500:
            commits_str = commits_str[:500] + "..."
        
        failures_list_parts = []
        for r in regressions[:5]:
            scenario = r.get('scenario_name', 'Unknown')
            error = r.get('error_message', 'Unknown')
            if len(error) > 100:
                error = error[:100] + "..."
            failures_list_parts.append(f"- {scenario}: {error}")
        
        failures_list = "\n".join(failures_list_parts)
        
        total_tests = overall_context.get('total_tests', 0)
        num_failures = len(regressions)
        num_commits = len(commits)
        
        prompt_lines = [
            "Generate an executive summary of test failures:",
            "",
            "**Test Run Summary:**",
            f"- Total tests: {total_tests}",
            f"- Failed: {num_failures}",
            f"- Commits analyzed: {num_commits}",
            "",
            "**Failures:**",
            failures_list,
            "",
            "**Context:**",
            commits_str,
            "",
            "Provide a concise executive summary in 2-3 paragraphs covering:",
            "1. What changed in the code",
            "2. Which tests failed and why",
            "3. Overall impact and urgency"
        ]
        
        prompt = "\n".join(prompt_lines)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a QA lead providing executive summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Summary generation failed: {e}")
            return self._generate_simple_summary(regressions, overall_context)
    
    def _generate_simple_summary(self, regressions: List[Dict[str, Any]], context: Dict[str, Any]) -> str:
        """Simple summary without LLM."""
        num_failures = len(regressions)
        total_tests = context.get('total_tests', 'unknown')
        num_commits = len(context.get('commits', []))
        
        return f"""## Test Run Summary

**{num_failures} test(s) failed** out of {total_tests} total tests.

**Commits analyzed**: {num_commits}

The failures appear to be related to recent code changes. Review the detailed analysis below for specific root causes and recommendations.
"""