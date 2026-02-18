"""Streamlit UI for QA Intelligence Agent."""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from dotenv import load_dotenv

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.git_repo import GitRepoAnalyzer
from agent.parsers import CucumberJsonParser, TestNGXmlParser
from agent.analyzers import ChangeClassifier, RunComparator
from agent.report_builder import ReportBuilder
from agent.config import ChangeType

# Load env
load_dotenv()

# Page config
st.set_page_config(
    page_title="QA Intelligence Agent",
    page_icon="🤖",
    layout="wide"
)

# Title
st.title("🤖 QA Intelligence Agent")
st.markdown("**Analyze test results + code changes = understand what broke and why**")

# Sidebar
with st.sidebar:
    st.header("Configuration")
    
    repo_url = st.text_input(
        "Git Repository URL",
        value="https://github.com/QA-Practice/QA_Playwright_Repo",
        help="Public or private GitHub repo URL"
    )
    
    github_token = st.text_input(
        "GitHub Token (optional)",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
        help="Required for private repos"
    )
    
    baseline_ref = st.text_input(
        "Baseline Ref",
        value="HEAD~5",
        help="Commit SHA, branch, or tag for baseline"
    )
    
    current_ref = st.text_input(
        "Current Ref",
        value="HEAD",
        help="Commit SHA, branch, or tag for current"
    )
    
    st.divider()
    
    st.subheader("Upload Reports")
    
    baseline_json = st.file_uploader(
        "Baseline Report (JSON/XML)",
        type=["json", "xml"],
        help="Cucumber JSON or TestNG XML"
    )
    
    current_json = st.file_uploader(
        "Current Report (JSON/XML)",
        type=["json", "xml"],
        help="Cucumber JSON or TestNG XML"
    )
    
    analyze_button = st.button("🔍 Analyze", type="primary", use_container_width=True)

# Main content
if analyze_button:
    if not baseline_json or not current_json:
        st.error("Please upload both baseline and current reports")
        st.stop()
    
    with st.spinner("Analyzing repository and reports..."):
        try:
            # Parse reports
            baseline_content = baseline_json.read().decode('utf-8')
            current_content = current_json.read().decode('utf-8')
            
            # Detect format and parse
            if baseline_json.name.endswith('.json'):
                baseline_summary = CucumberJsonParser.parse(baseline_content)
            else:
                baseline_summary = TestNGXmlParser.parse(baseline_content)
            
            if current_json.name.endswith('.json'):
                current_summary = CucumberJsonParser.parse(current_content)
            else:
                current_summary = TestNGXmlParser.parse(current_content)
            
            # Git analysis
            with GitRepoAnalyzer(repo_url, github_token or None) as git:
                baseline_sha = git.resolve_commit(baseline_ref)
                current_sha = git.resolve_commit(current_ref)
                
                commits = git.get_commits_between(baseline_ref, current_ref)
                raw_changes = git.get_diff(baseline_ref, current_ref)
                
                # Classify changes
                file_changes = ChangeClassifier.classify_changes(raw_changes)
                
                # Extract locator changes
                locator_changes = []
                for fc in file_changes:
                    if fc.change_type == ChangeType.LOCATOR:
                        locator_changes.extend(
                            ChangeClassifier.extract_locator_changes(fc.diff or "")
                        )
                
                # Compare runs
                regressions = RunComparator.find_regressions(baseline_summary, current_summary)
                improvements = RunComparator.find_improvements(baseline_summary, current_summary)
                duration_regressions = RunComparator.find_duration_regressions(
                    baseline_summary, current_summary
                )
                
                # Build report
                report = ReportBuilder.build_report(
                    repo_url=repo_url,
                    baseline_commit=baseline_sha,
                    current_commit=current_sha,
                    baseline_summary=baseline_summary,
                    current_summary=current_summary,
                    commits=commits,
                    file_changes=file_changes,
                    locator_changes=locator_changes,
                    regressions=regressions,
                    improvements=improvements,
                    duration_regressions=duration_regressions
                )
                
                # Store in session state
                st.session_state.report = report
                
        except Exception as e:
            st.error(f"Error during analysis: {str(e)}")
            st.exception(e)
            st.stop()

# Display results
if 'report' in st.session_state:
    report = st.session_state.report
    
    # Summary tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Summary", 
        "🔧 Changes", 
        "❌ Regressions", 
        "🔍 Locators",
        "📥 Export"
    ])
    
    with tab1:
        st.header("Test Run Summary")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Baseline")
            st.metric("Commit", report.baseline_commit)
            
            b_metrics = st.columns(4)
            b_metrics[0].metric("Total", report.baseline_summary.total)
            b_metrics[1].metric("✅ Passed", report.baseline_summary.passed)
            b_metrics[2].metric("❌ Failed", report.baseline_summary.failed)
            b_metrics[3].metric("⏭️ Skipped", report.baseline_summary.skipped)
            
            st.metric("Duration", f"{report.baseline_summary.duration_ms / 1000:.1f}s")
        
        with col2:
            st.subheader("Current")
            st.metric("Commit", report.current_commit)
            
            c_metrics = st.columns(4)
            c_metrics[0].metric("Total", report.current_summary.total)
            c_metrics[1].metric(
                "✅ Passed", 
                report.current_summary.passed,
                delta=report.current_summary.passed - report.baseline_summary.passed
            )
            c_metrics[2].metric(
                "❌ Failed", 
                report.current_summary.failed,
                delta=report.current_summary.failed - report.baseline_summary.failed,
                delta_color="inverse"
            )
            c_metrics[3].metric("⏭️ Skipped", report.current_summary.skipped)
            
            st.metric(
                "Duration", 
                f"{report.current_summary.duration_ms / 1000:.1f}s",
                delta=f"{(report.current_summary.duration_ms - report.baseline_summary.duration_ms) / 1000:.1f}s"
            )
        
        # AI Insights
        st.divider()
        st.header("🤖 AI Insights")
        
        insights = report.ai_insights
        
        col1, col2 = st.columns([2, 1])
        with col1:
            classification = insights.get("classification", "Unknown")
            if "No regressions" in classification:
                st.success(f"**{classification}**")
            elif "locator" in classification.lower():
                st.error(f"**{classification}**")
            elif "environment" in classification.lower():
                st.warning(f"**{classification}**")
            else:
                st.info(f"**{classification}**")
        
        with col2:
            confidence = insights.get("confidence", 0)
            st.metric("Confidence", f"{confidence * 100:.0f}%")
        
        st.markdown(insights.get("explanation", ""))
        
        if insights.get("recommended_actions"):
            st.subheader("Recommended Actions")
            for action in insights["recommended_actions"]:
                st.markdown(f"- {action}")
        
        # Commits
        if report.commits:
            st.divider()
            st.subheader(f"📝 {len(report.commits)} Commits")
            commits_df = pd.DataFrame(report.commits)
            st.dataframe(commits_df, use_container_width=True, hide_index=True)
    
    with tab2:
        st.header("Code Changes")
        
        # Group by change type
        change_counts = {}
        for fc in report.file_changes:
            change_type = fc.change_type.value
            change_counts[change_type] = change_counts.get(change_type, 0) + 1
        
        # Display counts
        cols = st.columns(len(change_counts))
        for i, (change_type, count) in enumerate(change_counts.items()):
            cols[i].metric(change_type.replace("_", " ").title(), count)
        
        # Files table
        st.subheader("Changed Files")
        files_data = [{
            "Path": fc.path,
            "Type": fc.change_type.value,
            "Additions": fc.additions,
            "Deletions": fc.deletions
        } for fc in report.file_changes]
        
        files_df = pd.DataFrame(files_data)
        st.dataframe(files_df, use_container_width=True, hide_index=True)
    
    with tab3:
        st.header("Regressions")
        
        if report.regressions:
            st.error(f"Found {len(report.regressions)} regression(s)")
            
            for reg in report.regressions:
                with st.expander(f"❌ {reg.feature} → {reg.scenario_name}"):
                    st.markdown(f"**Feature:** {reg.feature}")
                    st.markdown(f"**Scenario:** {reg.scenario_name}")
                    
                    col1, col2 = st.columns(2)
                    col1.metric("Baseline Duration", f"{reg.baseline_duration_ms:.0f}ms")
                    col2.metric("Current Duration", f"{reg.current_duration_ms:.0f}ms")
                    
                    if reg.error_message:
                        st.markdown("**Error:**")
                        st.code(reg.error_message, language="text")
        else:
            st.success("No regressions detected! 🎉")
        
        # Improvements
        if report.improvements:
            st.divider()
            st.subheader("✅ Improvements")
            st.success(f"{len(report.improvements)} test(s) fixed")
            for imp in report.improvements:
                st.markdown(f"- {imp}")
        
        # Duration regressions
        if report.duration_regressions:
            st.divider()
            st.subheader("⏱️ Duration Regressions")
            dur_df = pd.DataFrame(report.duration_regressions)
            st.dataframe(dur_df, use_container_width=True, hide_index=True)
    
    with tab4:
        st.header("Locator Changes")
        
        if report.locator_changes:
            st.warning(f"Found {len(report.locator_changes)} locator change(s)")
            
            locator_data = [{
                "Key": lc.key,
                "Change": lc.change_type,
                "Old Value": lc.old_value or "N/A",
                "New Value": lc.new_value or "N/A"
            } for lc in report.locator_changes]
            
            locator_df = pd.DataFrame(locator_data)
            st.dataframe(locator_df, use_container_width=True, hide_index=True)
            
            # Highlight suspicious changes
            if report.regressions:
                st.info(
                    "💡 **Tip:** These locator changes may have caused regressions. "
                    "Review them against failing scenarios."
                )
        else:
            st.success("No locator changes detected")
    
    with tab5:
        st.header("Export Report")
        
        json_report = ReportBuilder.to_json(report)
        
        st.download_button(
            label="📥 Download JSON Report",
            data=json_report,
            file_name="intelligence-report.json",
            mime="application/json",
            use_container_width=True
        )
        
        st.divider()
        st.subheader("Preview")
        st.json(json_report)

else:
    # Landing instructions
    st.info("""
    ### How to use:
    
    1. **Enter repository URL** (public or private with token)
    2. **Specify baseline and current refs** (commits, branches, or tags)
    3. **Upload test reports**:
       - Cucumber JSON (`target/cucumber/Cucumber.json`)
       - Or TestNG XML (`test-output/testng-results.xml`)
    4. Click **Analyze** to generate intelligence report
    
    The agent will:
    - Clone the repository
    - Extract commits and code changes
    - Parse test results
    - Detect regressions and improvements
    - Classify likely root causes
    - Suggest next actions
    """)