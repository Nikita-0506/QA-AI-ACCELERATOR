"""Enhanced report builder with detailed analysis and parallel processing."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from .config import (
    IntelligenceReport, FileChange, ChangeType,
    LocatorChange, Regression, TestRunSummary
)
from .analyzers.diff_analyzer import DiffAnalyzer, FileChangeDetail
from .analyzers.llm_analyzer import LLMAnalyzer


class EnhancedReportBuilder:
    """Build intelligence reports with detailed LLM-powered analysis."""
    
    def __init__(
        self, 
        openai_api_key: str = None,
        max_workers: int = 10,
        cache_dir: str = ".llm_cache",
        max_detailed_analysis: int = 20
    ):
        """Initialize with optional OpenAI API key for LLM analysis.
        
        Args:
            openai_api_key: OpenAI API key for LLM analysis
            max_workers: Maximum number of parallel threads for LLM calls
            cache_dir: Directory to store cached LLM results
            max_detailed_analysis: Maximum number of regressions to analyze in detail
        """
        self.llm_analyzer = LLMAnalyzer(api_key=openai_api_key)
        self.max_workers = max_workers
        self.cache_dir = cache_dir
        self.max_detailed_analysis = max_detailed_analysis
        
        # Create cache directory if it doesn't exist
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
    
    def build_detailed_report(
        self,
        repo_url: str,
        baseline_commit: str,
        current_commit: str,
        baseline_summary: TestRunSummary,
        current_summary: TestRunSummary,
        commits: List[Dict[str, str]],
        raw_file_changes: List[tuple],  # (path, diff, additions, deletions)
        regressions: List[Regression],
        improvements: List[str],
        duration_regressions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build comprehensive report with detailed analysis."""
        
        # Analyze diffs in detail
        detailed_changes = []
        for path, diff, additions, deletions in raw_file_changes:
            detail = DiffAnalyzer.parse_unified_diff(diff, path)
            detailed_changes.append(detail)
        
        # Extract key changes for LLM
        key_changes = DiffAnalyzer.extract_key_changes(detailed_changes)
        
        # Prepare file change summaries for LLM context
        file_change_summaries = [
            {"path": fc.file_path, "type": fc.change_type, "summary": fc.summary} 
            for fc in detailed_changes
        ]
        
        # ============================================================
        # STEP 1: PRIORITIZE - Sort regressions by impact
        # ============================================================
        print(f"[STEP 1] Prioritizing {len(regressions)} regressions...")
        prioritized_regressions = self._prioritize_regressions(regressions)
        
        # Split into detailed and quick analysis
        regressions_for_detailed = prioritized_regressions[:self.max_detailed_analysis]
        regressions_for_quick = prioritized_regressions[self.max_detailed_analysis:]
        
        print(f"  → Top {len(regressions_for_detailed)} for detailed analysis")
        print(f"  → Remaining {len(regressions_for_quick)} get quick summary")
        
        # ============================================================
        # STEPS 2-4: Check cache, parallel execution, combine results
        # ============================================================
        detailed_regressions = self._analyze_regressions_optimized(
            regressions_for_detailed,
            key_changes,
            file_change_summaries
        )
        
        # Add quick summaries for remaining regressions
        for regression in regressions_for_quick:
            regression_dict = {
                "scenario_name": regression.scenario_name,
                "feature": regression.feature,
                "error_message": regression.error_message,
                "baseline_duration_ms": regression.baseline_duration_ms,
                "current_duration_ms": regression.current_duration_ms
            }
            detailed_regressions.append({
                **regression_dict,
                "analysis": {
                    "root_cause": "Not analyzed in detail (lower priority)",
                    "note": f"This regression ranked #{len(detailed_regressions) + 1}. See top {self.max_detailed_analysis} for detailed analysis.",
                    "confidence": "N/A"
                }
            })
        
        # Generate executive summary
        executive_summary = self.llm_analyzer.generate_summary_report(
            detailed_regressions,
            [r["analysis"] for r in detailed_regressions],
            {
                "total_tests": baseline_summary.total,
                "commits": commits,
                "files_changed": len(detailed_changes)
            }
        )
        
        # Build comprehensive report
        return {
            "repo_url": repo_url,
            "baseline_commit": baseline_commit,
            "current_commit": current_commit,
            "executive_summary": executive_summary,
            "test_summary": {
                "baseline": {
                    "total": baseline_summary.total,
                    "passed": baseline_summary.passed,
                    "failed": baseline_summary.failed,
                    "duration_ms": baseline_summary.duration_ms
                },
                "current": {
                    "total": current_summary.total,
                    "passed": current_summary.passed,
                    "failed": current_summary.failed,
                    "duration_ms": current_summary.duration_ms
                }
            },
            "commits": commits,
            "detailed_file_changes": [
                {
                    "file_path": fc.file_path,
                    "change_type": fc.change_type,
                    "summary": fc.summary,
                    "line_changes": [
                        {
                            "line_number": lc.line_number,
                            "change_type": lc.change_type,
                            "old_content": lc.old_content,
                            "new_content": lc.new_content,
                            "context": lc.context_before
                        }
                        for lc in fc.line_changes
                    ]
                }
                for fc in detailed_changes
                if fc.line_changes  # Only include files with actual changes
            ],
            "regressions": detailed_regressions,
            "improvements": improvements,
            "duration_regressions": duration_regressions,
            "key_findings": self._extract_key_findings(detailed_regressions, detailed_changes)
        }
    
    def _prioritize_regressions(self, regressions: List[Regression]) -> List[Regression]:
        """Step 1: Prioritize regressions by impact."""
        def calculate_priority(regression: Regression) -> float:
            score = 0.0
            
            # Errors are most important
            if regression.error_message:
                score += 1000
            
            # Then consider duration impact
            if regression.current_duration_ms and regression.baseline_duration_ms:
                duration_increase = regression.current_duration_ms - regression.baseline_duration_ms
                score += max(0, duration_increase)
            
            return score
        
        return sorted(regressions, key=calculate_priority, reverse=True)
    
    def _analyze_regressions_optimized(
        self,
        regressions: List[Regression],
        key_changes: Any,
        file_change_summaries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Steps 2-4: Check cache, parallel execution, and combine results."""
        if not regressions:
            return []
        
        print(f"\n[STEP 2] Checking cache for {len(regressions)} regressions...")
        
        # Prepare all regression dictionaries
        regression_dicts = [
            {
                "scenario_name": r.scenario_name,
                "feature": r.feature,
                "error_message": r.error_message,
                "baseline_duration_ms": r.baseline_duration_ms,
                "current_duration_ms": r.current_duration_ms
            }
            for r in regressions
        ]
        
        # Step 2: Check cache for each regression
        cached_results = []
        to_analyze = []
        
        for i, regression_dict in enumerate(regression_dicts):
            cache_result = self._get_from_cache(regression_dict, key_changes)
            
            if cache_result is not None:
                cached_results.append((i, {**regression_dict, "analysis": cache_result}))
            else:
                to_analyze.append((i, regression_dict))
        
        print(f"  ✓ Cache hit: {len(cached_results)}/{len(regressions)} ({len(cached_results)*100//len(regressions) if regressions else 0}%)")
        print(f"  → Need to analyze: {len(to_analyze)} regressions")
        
        # Step 3: Parallel execution for uncached regressions
        if to_analyze:
            print(f"\n[STEP 3] Launching {min(len(to_analyze), self.max_workers)} parallel LLM analyses...")
            new_results = self._analyze_parallel(to_analyze, key_changes, file_change_summaries)
        else:
            print(f"\n[STEP 3] All results from cache - no LLM calls needed!")
            new_results = []
        
        # Step 4: Combine results (cached + new)
        print(f"\n[STEP 4] Combining results...")
        
        # Merge cached and new results in original order
        all_results = cached_results + new_results
        all_results.sort(key=lambda x: x[0])  # Sort by original index
        
        return [result for _, result in all_results]
    
    def _get_cache_key(self, regression_dict: Dict[str, Any], key_changes: Any) -> str:
        """Generate a unique cache key for a regression analysis."""
        cache_input = {
            "scenario": regression_dict.get("scenario_name", ""),
            "feature": regression_dict.get("feature", ""),
            "error": regression_dict.get("error_message", ""),
            "changes": str(key_changes)[:500]
        }
        
        cache_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _get_from_cache(
        self, 
        regression_dict: Dict[str, Any], 
        key_changes: Any
    ) -> Dict[str, Any] | None:
        """Check if analysis exists in cache."""
        if not self.cache_dir:
            return None
        
        cache_key = self._get_cache_key(regression_dict, key_changes)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
        
        return None
    
    def _save_to_cache(
        self, 
        regression_dict: Dict[str, Any], 
        key_changes: Any,
        analysis: Dict[str, Any]
    ) -> None:
        """Save analysis result to cache."""
        if not self.cache_dir:
            return
        
        cache_key = self._get_cache_key(regression_dict, key_changes)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(analysis, f, indent=2)
        except IOError as e:
            print(f"  ⚠️  Warning: Could not save to cache: {e}")
    
    def _analyze_parallel(
        self,
        to_analyze: List[tuple],
        key_changes: Any,
        file_change_summaries: List[Dict[str, Any]]
    ) -> List[tuple]:
        """Execute LLM analyses in parallel using ThreadPoolExecutor."""
        
        def analyze_single(item):
            index, regression_dict = item
            
            scenario_name = regression_dict.get("scenario_name", "Unknown")
            print(f"  ⚡ Thread {index}: Analyzing '{scenario_name[:50]}...'")
            
            try:
                analysis = self.llm_analyzer.analyze_failure_with_context(
                    regression_dict,
                    key_changes,
                    file_change_summaries
                )
                
                self._save_to_cache(regression_dict, key_changes, analysis)
                
                print(f"  ✓ Thread {index}: Complete")
                
                return (index, {**regression_dict, "analysis": analysis})
                
            except Exception as e:
                print(f"  ✗ Thread {index}: Error - {e}")
                return (index, {
                    **regression_dict, 
                    "analysis": {
                        "root_cause": "Analysis failed",
                        "error": str(e),
                        "confidence": "N/A"
                    }
                })
        
        # Timeout (in seconds) for each individual LLM analysis task.
        # Prevents the executor from hanging indefinitely if an API call stalls.
        FUTURE_TIMEOUT_SECONDS = 320

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(analyze_single, item): item for item in to_analyze}
            
            for future in as_completed(futures):
                item = futures[future]
                index, regression_dict = item
                try:
                    # Wait at most FUTURE_TIMEOUT_SECONDS for each result
                    result = future.result(timeout=FUTURE_TIMEOUT_SECONDS)
                    results.append(result)
                except TimeoutError:
                    scenario_name = regression_dict.get("scenario_name", "Unknown")
                    print(f"  ⏱ Thread {index}: Timed out after {FUTURE_TIMEOUT_SECONDS}s for '{scenario_name[:50]}'")
                    # Return a graceful fallback so the rest of the report isn't blocked
                    results.append((index, {
                        **regression_dict,
                        "analysis": {
                            "root_cause": "Analysis timed out",
                            "error": f"LLM analysis did not complete within {FUTURE_TIMEOUT_SECONDS}s",
                            "confidence": "N/A"
                        }
                    }))
                except Exception as e:
                    print(f"  ✗ Unexpected error: {e}")
        
        return results
    
    def _extract_key_findings(
        self,
        regressions: List[Dict[str, Any]],
        file_changes: List[FileChangeDetail]
    ) -> List[str]:
        """Extract key findings from analysis."""
        findings = []
        
        for regression in regressions:
            analysis = regression.get("analysis", {})
            if "password" in regression.get("error_message", "").lower():
                findings.append(
                    f"⚠️ Authentication issue in '{regression['scenario_name']}': "
                    "Test may be using incorrect credentials"
                )
            
            if "timeout" in regression.get("error_message", "").lower():
                duration_increase = regression['current_duration_ms'] - regression['baseline_duration_ms']
                findings.append(
                    f"⏱️ Timeout in '{regression['scenario_name']}' after "
                    f"{duration_increase/1000:.1f}s longer than baseline"
                )
        
        step_def_changes = [fc for fc in file_changes if fc.change_type == "step_definition"]
        if step_def_changes and regressions:
            findings.append(
                f"🔧 {len(step_def_changes)} step definition file(s) changed - "
                "may have introduced bugs in test implementation"
            )
        
        feature_changes = [fc for fc in file_changes if fc.change_type == "feature"]
        if feature_changes:
            findings.append(
                f"📝 {len(feature_changes)} feature file(s) modified - "
                "test scenarios or test data have changed"
            )
        
        return findings