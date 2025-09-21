"""
Report Generation Agent for VLABench
This agent generates comprehensive reports from evaluation results.
Phase 1: Basic Markdown report generation.
"""

import os
import json
import yaml
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path


class ReportAgent:
    """
    Report Agent responsible for generating readable reports from evaluation results.
    This agent creates Markdown reports with metrics visualization.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the ReportAgent with configuration.
        
        Args:
            config_path: Path to the agent configuration YAML file
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set default values
        self.report_output_dir = self.config.get("report_output_dir", "VLABench/reports")
        self.include_charts = self.config.get("include_charts", False)
        self.report_format = self.config.get("report_format", "markdown")
        
        # Ensure output directory exists
        os.makedirs(self.report_output_dir, exist_ok=True)
    
    def run(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Report Agent to generate a comprehensive report.
        
        Args:
            input_state: Current state from the workflow containing evaluation results
            
        Returns:
            Updated state with report file path
        """
        print("Running ReportAgent...")
        
        # Extract evaluation information from previous agent
        eval_info = input_state.get("evaluation", {})
        
        if not eval_info or eval_info.get("status") != "completed":
            return self._handle_error(input_state, "No completed evaluation found in state")
        
        # Extract relevant information
        report_path = eval_info.get("report_path")
        task_name = eval_info.get("task_name", "unknown_task")
        model_name = eval_info.get("model_name", "unknown_model")
        metrics = eval_info.get("metrics", {})
        raw_results = eval_info.get("raw_results", {})
        
        try:
            # Generate report filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"{task_name}_{model_name}_{timestamp}.md"
            report_file_path = os.path.join(self.report_output_dir, report_filename)
            
            # Generate the report content
            print(f"Generating report for task: {task_name}")
            report_content = self._generate_report(
                task_name=task_name,
                model_name=model_name,
                metrics=metrics,
                full_state=input_state,
                raw_results=raw_results
            )
            
            # Write report to file
            with open(report_file_path, 'w') as f:
                f.write(report_content)
            
            print(f"✓ Report generated: {report_file_path}")
            
            # Optionally generate charts (Phase 2+)
            chart_paths = []
            if self.include_charts and metrics:
                chart_paths = self._generate_charts(metrics, task_name, model_name)
            
            # Update state with report information
            updated_state = input_state.copy()
            updated_state["report"] = {
                "status": "completed",
                "path": report_file_path,
                "format": self.report_format,
                "task_name": task_name,
                "model_name": model_name,
                "timestamp": timestamp,
                "charts": chart_paths
            }
            
            return updated_state
            
        except Exception as e:
            return self._handle_error(input_state, f"Unexpected error: {str(e)}")
    
    def _generate_report(self, task_name: str, model_name: str, 
                        metrics: Dict[str, float], full_state: Dict[str, Any],
                        raw_results: Dict[str, Any]) -> str:
        """
        Generate a comprehensive Markdown report.
        
        Args:
            task_name: Name of the evaluated task
            model_name: Name of the evaluated model
            metrics: Dictionary of computed metrics
            full_state: Complete workflow state
            raw_results: Raw evaluation results
            
        Returns:
            Markdown formatted report content
        """
        # Extract additional information from state
        scenario_info = full_state.get("scenario", {})
        task_info = full_state.get("task", {})
        trajectory_info = full_state.get("trajectory", {})
        
        # Build report header
        report = f"""# VLABench Evaluation Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## Task Information

| Field | Value |
|-------|-------|
| **Task Name** | `{task_name}` |
| **Task Type** | `{task_info.get('type', 'primitive')}` |
| **Model** | `{model_name}` |
| **Evaluation Track** | `{full_state.get('evaluation', {}).get('eval_track', 'vla')}` |

## Scenario Configuration

| Field | Value |
|-------|-------|
| **Scene** | `{scenario_info.get('name', 'N/A')}` |
| **Objects** | {', '.join(scenario_info.get('object_classes', [])) or 'N/A'} |
| **Components** | {len(full_state.get('components', []))} items |

## Trajectory Generation

| Field | Value |
|-------|-------|
| **Status** | `{trajectory_info.get('status', 'N/A')}` |
| **Episodes** | {trajectory_info.get('num_episodes', 'N/A')} |
| **Robot** | `{trajectory_info.get('robot', 'franka')}` |
| **Output Path** | `{trajectory_info.get('path', 'N/A')}` |

---

## Evaluation Metrics

"""
        
        # Add metrics table
        if metrics:
            report += "| Metric | Value | Status |\n"
            report += "|--------|-------|--------|\n"
            
            for metric_name, value in metrics.items():
                # Determine status emoji based on value
                if isinstance(value, (int, float)):
                    if value >= 0.8:
                        status = "🟢 Excellent"
                    elif value >= 0.6:
                        status = "🟡 Good"
                    elif value >= 0.4:
                        status = "🟠 Fair"
                    else:
                        status = "🔴 Poor"
                    
                    # Format value as percentage
                    formatted_value = f"{value:.2%}" if value <= 1.0 else f"{value:.2f}"
                else:
                    formatted_value = str(value)
                    status = "ℹ️ Info"
                
                # Clean up metric name
                display_name = metric_name.replace("_", " ").title()
                report += f"| **{display_name}** | {formatted_value} | {status} |\n"
        else:
            report += "*No metrics available*\n"
        
        # Add performance analysis
        report += "\n### Performance Analysis\n\n"
        
        if metrics:
            success_rate = metrics.get("success_rate", 0)
            progress_score = metrics.get("progress_score", 0)
            
            if success_rate >= 0.8:
                report += "✅ **Excellent Performance**: The model successfully completed the task with high accuracy.\n\n"
            elif success_rate >= 0.5:
                report += "⚠️ **Moderate Performance**: The model showed reasonable capability but has room for improvement.\n\n"
            else:
                report += "❌ **Needs Improvement**: The model struggled with this task and requires further training.\n\n"
            
            # Add specific insights
            if progress_score > success_rate:
                report += "📊 The model made good progress even when not fully succeeding, indicating partial understanding.\n\n"
            
            if "intention_score" in metrics:
                intention = metrics["intention_score"]
                if intention > 0.7:
                    report += "🎯 Strong intention recognition suggests good task understanding.\n\n"
        
        # Add raw results section (Phase 1)
        report += "\n---\n\n## Raw Results\n\n"
        report += "```json\n"
        report += json.dumps(raw_results, indent=2)[:1000]  # Limit to 1000 chars
        if len(json.dumps(raw_results)) > 1000:
            report += "\n... (truncated)"
        report += "\n```\n"
        
        # Add workflow summary
        report += "\n---\n\n## Workflow Summary\n\n"
        report += "### Pipeline Stages\n\n"
        report += "1. ✅ **ScenarioAgent**: Scene and asset configuration\n"
        report += "2. ✅ **TaskAgent**: Task Python file generation\n"
        report += "3. ✅ **TrajectoryAgent**: Trajectory data generation\n"
        report += "4. ✅ **EvalAgent**: Model evaluation\n"
        report += "5. ✅ **ReportAgent**: Report generation\n"
        
        # Add notes section
        report += "\n---\n\n## Notes\n\n"
        report += f"- **Phase**: 1 (Basic Implementation)\n"
        report += f"- **LangGraph Integration**: Enabled\n"
        report += f"- **Automatic Pipeline**: End-to-end execution\n"
        
        # Add footer
        report += "\n---\n\n"
        report += "*Generated by VLABench LangGraph Multi-Agent System*\n"
        
        return report
    
    def _generate_charts(self, metrics: Dict[str, float], 
                        task_name: str, model_name: str) -> List[str]:
        """
        Generate visualization charts for metrics (Phase 2+).
        
        Args:
            metrics: Dictionary of metrics to visualize
            task_name: Name of the task
            model_name: Name of the model
            
        Returns:
            List of paths to generated chart files
        """
        # Phase 1: Placeholder for chart generation
        print("  Chart generation not implemented in Phase 1")
        return []
    
    def _handle_error(self, input_state: Dict[str, Any], error_msg: str) -> Dict[str, Any]:
        """
        Handle errors by updating the state with error information.
        
        Args:
            input_state: Current state
            error_msg: Error message to include
            
        Returns:
            Updated state with error field
        """
        print(f"❌ Error: {error_msg}")
        updated_state = input_state.copy()
        updated_state["error"] = error_msg
        updated_state["report"] = {
            "status": "failed",
            "error": error_msg
        }
        return updated_state


if __name__ == "__main__":
    # Standalone testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Report Generation Agent for VLABench")
    parser.add_argument("--config", type=str, required=True,
                        help="Path to the agent configuration file")
    args = parser.parse_args()
    
    # Create agent
    agent = ReportAgent(args.config)
    
    # Mock input state with evaluation results
    mock_state = {
        "scenario": {
            "name": "kitchen_2",
            "object_classes": ["cabinet", "microwave", "fruit"]
        },
        "task": {
            "name": "pick_and_place_task",
            "type": "primitive"
        },
        "trajectory": {
            "status": "completed",
            "path": "VLABench/trajectories/test.hdf5",
            "num_episodes": 5,
            "robot": "franka"
        },
        "evaluation": {
            "status": "completed",
            "report_path": "VLABench/eval_results/test_eval.json",
            "task_name": "pick_and_place_task",
            "model_name": "random",
            "eval_track": "vla",
            "metrics": {
                "success_rate": 0.75,
                "progress_score": 0.82,
                "intention_score": 0.68
            },
            "raw_results": {
                "task": "pick_and_place_task",
                "episodes": 5,
                "detailed_scores": [0.7, 0.8, 0.75, 0.8, 0.7]
            }
        }
    }
    
    # Run agent
    result = agent.run(mock_state)
    
    # Print results
    print("\n--- Report Agent Results ---")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        report_info = result.get("report", {})
        print(f"Status: {report_info.get('status')}")
        print(f"Report: {report_info.get('path')}")