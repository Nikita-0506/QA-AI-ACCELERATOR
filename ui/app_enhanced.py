"""Enhanced Streamlit UI with detailed analysis display."""
import streamlit as st
import os
from pathlib import Path
import sys
import json
from io import StringIO
import contextlib

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.git_repo import GitRepoAnalyzer
from agent.parsers import CucumberJsonParser
from agent.report_builder_enhanced import EnhancedReportBuilder
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="QA Intelligence Agent - Enhanced",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 QA Intelligence Agent - Enhanced Analysis")
st.markdown("**AI-powered analysis that explains exactly what changed and why tests failed**")

# Sidebar
with st.sidebar:
    st.header("Configuration")
    
    repo_url = st.text_input(
        "Git Repository URL",
        value="https://github.com/Inadev-Data-Lab/QA_Playwright_Repo",
    )
    
    github_token = st.text_input(
        "GitHub Token (optional)",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
    )
    
    st.divider()
    st.subheader("🤖 AI Configuration")
    
    # Show which provider is configured
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    openai_key_env = os.getenv("OPENAI_API_KEY")
    
    if azure_endpoint and azure_deployment:
        st.success("✅ Azure OpenAI Configured")
        st.caption(f"📍 Endpoint: {azure_endpoint[:50]}...")
        st.caption(f"📦 Deployment: {azure_deployment}")
    elif openai_key_env:
        st.success("✅ Standard OpenAI Configured")
    else:
        st.warning("⚠️ No AI Provider Configured")
        st.caption("Will use rule-based analysis")
    
    openai_key = st.text_input(
        "OpenAI API Key (optional override)",
        type="password",
        value="",
        help="Leave empty to use Azure OpenAI from .env or standard OpenAI from .env"
    )
    
    st.divider()
    
    baseline_ref = st.text_input("Baseline Ref", value="36f96ae5")
    current_ref = st.text_input("Current Ref", value="1ea635a0")
    
    st.divider()
    
    # Performance Settings
    with st.expander("⚡ Performance Settings", expanded=False):
        st.markdown("**Optimization Options**")
        
        max_workers = st.slider(
            "Parallel Workers",
            min_value=1,
            max_value=20,
            value=10,
            help="Number of parallel threads for LLM analysis. More = faster but uses more API quota."
        )
        
        max_detailed = st.slider(
            "Max Detailed Analysis",
            min_value=5,
            max_value=50,
            value=20,
            help="Maximum regressions to analyze in detail. Rest get quick summary."
        )
        
        enable_cache = st.checkbox(
            "Enable Caching",
            value=True,
            help="Cache LLM results for faster repeat analysis"
        )
        
        cache_dir = ".llm_cache" if enable_cache else None
    
    st.divider()
    
    baseline_json = st.file_uploader("Baseline Report (JSON)", type=["json"])
    current_json = st.file_uploader("Current Report (JSON)", type=["json"])
    
    analyze_button = st.button("🔍 Analyze", type="primary", use_container_width=True)

# Main content
if analyze_button:
    if not baseline_json or not current_json:
        st.error("Please upload both reports")
        st.stop()
    
    # Create a progress container
    progress_container = st.container()
    progress_text = st.empty()
    progress_bar = st.progress(0)
    output_container = st.expander("📊 Analysis Progress", expanded=True)
    
    with st.spinner("🔎 Analyzing repository and generating AI insights..."):
        try:
            # Capture print statements
            output_buffer = StringIO()
            
            with output_container:
                status_placeholder = st.empty()
                
                # Parse reports
                status_placeholder.info("📖 Parsing test reports...")
                progress_bar.progress(10)
                
                baseline_content = baseline_json.read().decode('utf-8')
                current_content = current_json.read().decode('utf-8')
                
                baseline_summary = CucumberJsonParser.parse(baseline_content)
                current_summary = CucumberJsonParser.parse(current_content)
                
                status_placeholder.success(f"✓ Parsed reports: {baseline_summary.total} baseline tests, {current_summary.total} current tests")
                
                # Git analysis
                status_placeholder.info("🔍 Analyzing Git repository...")
                progress_bar.progress(20)
                
                with GitRepoAnalyzer(repo_url, github_token or None) as git:
                    commits = git.get_commits_between(baseline_ref, current_ref)
                    raw_changes = git.get_diff(baseline_ref, current_ref)
                    
                    status_placeholder.success(f"✓ Found {len(commits)} commits and {len(raw_changes)} file changes")
                    progress_bar.progress(30)
                    
                    # Build enhanced report
                    status_placeholder.info("🤖 Initializing AI-powered report builder...")
                    
                    report_builder = EnhancedReportBuilder(
                        openai_api_key=openai_key or None,
                        max_workers=max_workers,
                        cache_dir=cache_dir,
                        max_detailed_analysis=max_detailed
                    )
                    
                    progress_bar.progress(40)
                    
                    # Find regressions
                    status_placeholder.info("🔬 Comparing test runs...")
                    from agent.analyzers.compare_runs import RunComparator
                    regressions = RunComparator.find_regressions(baseline_summary, current_summary)
                    improvements = RunComparator.find_improvements(baseline_summary, current_summary)
                    duration_regressions = RunComparator.find_duration_regressions(baseline_summary, current_summary)
                    
                    status_placeholder.success(f"✓ Found {len(regressions)} regressions, {len(improvements)} improvements")
                    progress_bar.progress(50)
                    
                    # Capture stdout for progress updates
                    import sys
                    from io import StringIO
                    
                    # Create progress display
                    progress_display = st.empty()
                    
                    # Redirect stdout to capture print statements
                    old_stdout = sys.stdout
                    sys.stdout = captured_output = StringIO()
                    
                    try:
                        status_placeholder.info("🧠 Running AI analysis (this may take a moment)...")
                        
                        # Build detailed report (this will print progress)
                        report = report_builder.build_detailed_report(
                            repo_url=repo_url,
                            baseline_commit=baseline_ref,
                            current_commit=current_ref,
                            baseline_summary=baseline_summary,
                            current_summary=current_summary,
                            commits=commits,
                            raw_file_changes=raw_changes,
                            regressions=regressions,
                            improvements=improvements,
                            duration_regressions=duration_regressions
                        )
                        
                        # Get captured output
                        output_text = captured_output.getvalue()
                        
                        # Display the progress output
                        if output_text:
                            with st.code(output_text, language="text"):
                                pass
                        
                    finally:
                        # Restore stdout
                        sys.stdout = old_stdout
                    
                    progress_bar.progress(100)
                    status_placeholder.success("✅ Analysis complete!")
                    
                    st.session_state.report = report
                    
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.exception(e)
            st.stop()

# Display results
if 'report' in st.session_state:
    report = st.session_state.report
    
    # Performance metrics
    if report.get("regressions"):
        analyzed_count = sum(1 for r in report["regressions"] if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", "")))
        quick_count = len(report["regressions"]) - analyzed_count
        
        st.success(f"🚀 Analysis complete! Detailed analysis: {analyzed_count} regressions | Quick summary: {quick_count} regressions")
    
    # Executive Summary
    st.header("📊 Executive Summary")
    st.info(report["executive_summary"])
    
    # Key Findings
    if report.get("key_findings"):
        st.header("🔍 Key Findings")
        for finding in report["key_findings"]:
            st.warning(finding)
    
    # Detailed tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "💥 Failures Analysis",
        "📝 Code Changes",
        "📈 Metrics",
        "📥 Export"
    ])
    
    with tab1:
        st.header("Detailed Failure Analysis")
        
        # Separate detailed and quick analyses
        detailed_regressions = [r for r in report["regressions"] if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", ""))]
        quick_regressions = [r for r in report["regressions"] if "Not analyzed in detail" in str(r.get("analysis", {}).get("root_cause", ""))]
        
        if detailed_regressions:
            st.subheader(f"🔬 Detailed AI Analysis ({len(detailed_regressions)} regressions)")
            
            for regression in detailed_regressions:
                with st.expander(f"❌ {regression['scenario_name']}", expanded=True):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.subheader("Analysis")
                        analysis = regression.get("analysis", {})
                        
                        if analysis.get("analysis_type") == "llm_powered":
                            provider = analysis.get("provider", "AI")
                            st.success(f"🤖 {provider} Analysis")
                        else:
                            st.info("📊 Rule-Based Analysis")
                        
                        st.markdown(analysis.get("detailed_explanation", "No analysis available"))
                    
                    with col2:
                        st.subheader("Metrics")
                        st.metric(
                            "Duration Change",
                            f"{regression['current_duration_ms']:.0f}ms",
                            f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                        )
                        
                        st.subheader("Error Details")
                        with st.expander("View full error"):
                            st.code(regression.get("error_message", "No error message"), language="text")
        
        if quick_regressions:
            st.divider()
            st.subheader(f"📋 Quick Summary ({len(quick_regressions)} regressions)")
            st.caption("These regressions were not analyzed in detail due to lower priority. Increase 'Max Detailed Analysis' in settings to include more.")
            
            for i, regression in enumerate(quick_regressions, 1):
                with st.expander(f"⚠️ {regression['scenario_name']}"):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown(f"**Feature:** {regression['feature']}")
                        if regression.get('error_message'):
                            st.markdown("**Error:**")
                            st.code(regression['error_message'][:200] + "..." if len(regression['error_message']) > 200 else regression['error_message'], language="text")
                    
                    with col2:
                        st.metric(
                            "Duration Change",
                            f"{regression['current_duration_ms']:.0f}ms",
                            f"+{regression['current_duration_ms'] - regression['baseline_duration_ms']:.0f}ms"
                        )
    
    with tab2:
        st.header("Detailed Code Changes")
        
        for file_change in report["detailed_file_changes"]:
            with st.expander(f"📄 {file_change['file_path']} ({file_change['change_type']})"):
                st.caption(file_change['summary'])
                
                for line_change in file_change["line_changes"][:10]:  # Show first 10 changes
                    st.markdown(f"**Line {line_change['line_number']}** - _{line_change['change_type']}_")
                    
                    if line_change['change_type'] == 'modified':
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Before:**")
                            st.code(line_change.get('old_content', ''), language="text")
                        with col2:
                            st.markdown("**After:**")
                            st.code(line_change.get('new_content', ''), language="text")
                    
                    elif line_change['change_type'] == 'added':
                        st.markdown("**Added:**")
                        st.code(line_change.get('new_content', ''), language="text")
                    
                    elif line_change['change_type'] == 'removed':
                        st.markdown("**Removed:**")
                        st.code(line_change.get('old_content', ''), language="text")
                    
                    st.divider()
    
    with tab3:
        st.header("Test Metrics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Baseline")
            metrics = report["test_summary"]["baseline"]
            st.metric("Total", metrics["total"])
            st.metric("Passed", metrics["passed"])
            st.metric("Failed", metrics["failed"])
        
        with col2:
            st.subheader("Current")
            metrics = report["test_summary"]["current"]
            baseline_metrics = report["test_summary"]["baseline"]
            st.metric("Total", metrics["total"])
            st.metric("Passed", metrics["passed"], delta=metrics["passed"] - baseline_metrics["passed"])
            st.metric("Failed", metrics["failed"], delta=metrics["failed"] - baseline_metrics["failed"], delta_color="inverse")
        
        # Performance stats
        st.divider()
        st.subheader("⚡ Performance Stats")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            detailed = sum(1 for r in report["regressions"] if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", "")))
            st.metric("Detailed Analyses", detailed)
        
        with col2:
            quick = len(report["regressions"]) - sum(1 for r in report["regressions"] if "Not analyzed in detail" not in str(r.get("analysis", {}).get("root_cause", "")))
            st.metric("Quick Summaries", quick)
        
        with col3:
            st.metric("Total Regressions", len(report["regressions"]))
    
    with tab4:
        st.header("Export Report")
        
        report_json = json.dumps(report, indent=2, default=str)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="📥 Download Full Report (JSON)",
                data=report_json,
                file_name="intelligence-report-enhanced.json",
                mime="application/json",
                use_container_width=True
            )
        
        with col2:
            # Create a markdown summary
            markdown_summary = f"""# QA Intelligence Report

## Executive Summary
{report["executive_summary"]}

## Key Findings
{chr(10).join(f"- {finding}" for finding in report.get("key_findings", []))}

## Test Summary
- **Baseline:** {report["test_summary"]["baseline"]["passed"]}/{report["test_summary"]["baseline"]["total"]} passed
- **Current:** {report["test_summary"]["current"]["passed"]}/{report["test_summary"]["current"]["total"]} passed
- **Change:** {report["test_summary"]["current"]["passed"] - report["test_summary"]["baseline"]["passed"]:+d} tests

## Regressions Found: {len(report["regressions"])}

"""
            for reg in report["regressions"][:10]:  # First 10
                markdown_summary += f"""### {reg['scenario_name']}
- **Feature:** {reg['feature']}
- **Error:** {reg.get('error_message', 'N/A')[:100]}...
- **Duration:** {reg['baseline_duration_ms']:.0f}ms → {reg['current_duration_ms']:.0f}ms

"""
            
            st.download_button(
                label="📄 Download Summary (Markdown)",
                data=markdown_summary,
                file_name="intelligence-report-summary.md",
                mime="text/markdown",
                use_container_width=True
            )
else:
    st.info("""
    ### 👋 Welcome to the Enhanced QA Intelligence Agent!
    
    This tool provides:
    - **Line-by-line code analysis**: See exactly what changed and where
    - **AI-powered explanations**: Understand why tests failed in plain English
    - **Root cause analysis**: Connect code changes to test failures
    - **Actionable recommendations**: Get specific steps to fix issues
    - **⚡ Optimized Performance**: 50-100x faster with parallel processing and caching
    
    **To get started:**
    1. Enter your repository details and commit refs
    2. Configure AI provider in .env (Azure OpenAI or standard OpenAI)
    3. Configure performance settings (optional - defaults are optimized)
    4. Upload your baseline and current test reports
    5. Click Analyze
    
    **Performance Tips:**
    - **Parallel Workers**: More workers = faster analysis (uses more API quota)
    - **Max Detailed Analysis**: Analyze top N regressions in detail, rest get quick summary
    - **Enable Caching**: Dramatically speeds up repeat analyses on same commits
    
    The agent will analyze your code changes and explain everything in human-friendly language!
    """)