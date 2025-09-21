"""
VLABench LangGraph Workflow
This module defines the complete multi-agent workflow using LangGraph.
Phase 1: Sequential execution of all agents.
"""

import os
import sys
from typing import Optional, Dict, Any, List
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# Add VLABench to path
sys.path.insert(0, "/home/vla/Downloads/VLABench")
os.environ["VLABENCH_ROOT"] = "/home/vla/Downloads/VLABench/VLABench"

# Import agents
from VLABench.langgraph_agents import (
    ScenarioAgent,
    TaskAgent,
    TrajectoryAgent,
    EvalAgent,
    ReportAgent
)


# Define the workflow state structure
class VLABenchState(TypedDict, total=False):
    """State dictionary for the VLABench workflow."""
    # Scenario configuration
    scenario: Optional[Dict[str, Any]]
    components: Optional[List[Dict[str, Any]]]
    object_classes: Optional[List[str]]
    
    # Task generation
    task: Optional[Dict[str, Any]]
    
    # Trajectory generation
    trajectory: Optional[Dict[str, Any]]
    
    # Evaluation results
    evaluation: Optional[Dict[str, Any]]
    
    # Report generation
    report: Optional[Dict[str, Any]]
    
    # Error tracking
    error: Optional[str]


def create_workflow(config_dir: str = "VLABench/configs/langgraph/agent_configs"):
    """
    Create the VLABench LangGraph workflow.
    
    Args:
        config_dir: Directory containing agent configuration files
        
    Returns:
        Compiled LangGraph application
    """
    # Initialize agents with their configurations
    print("Initializing agents...")
    
    scenario_agent = ScenarioAgent(os.path.join(config_dir, "scenario_agent.yaml"))
    task_agent = TaskAgent(os.path.join(config_dir, "task_agent.yaml"))
    trajectory_agent = TrajectoryAgent(os.path.join(config_dir, "trajectory_agent.yaml"))
    eval_agent = EvalAgent(os.path.join(config_dir, "eval_agent.yaml"))
    report_agent = ReportAgent(os.path.join(config_dir, "report_agent.yaml"))
    
    # Create the state graph
    workflow = StateGraph(VLABenchState)
    
    # Add nodes for each agent
    workflow.add_node("scenario_agent", scenario_agent.run)
    workflow.add_node("task_agent", task_agent.run)
    workflow.add_node("trajectory_agent", trajectory_agent.run)
    workflow.add_node("eval_agent", eval_agent.run)
    workflow.add_node("report_agent", report_agent.run)
    
    # Define conditional logic for trajectory agent
    def should_continue_after_trajectory(state: VLABenchState):
        """Determine next step after trajectory generation."""
        if state.get("error"):
            return "end_with_error"
        
        trajectory = state.get("trajectory", {})
        if trajectory.get("status") == "human_approval_needed":
            return "human_in_loop"
        elif trajectory.get("status") == "completed":
            return "continue"
        else:
            return "end_with_error"
    
    # Define conditional logic for evaluation agent
    def should_continue_after_eval(state: VLABenchState):
        """Determine next step after evaluation."""
        if state.get("error"):
            return "end_with_error"
        
        evaluation = state.get("evaluation", {})
        if evaluation.get("status") == "completed":
            return "continue"
        else:
            return "end_with_error"
    
    # Define the workflow edges
    # Sequential flow: START -> scenario -> task -> trajectory
    workflow.add_edge(START, "scenario_agent")
    workflow.add_edge("scenario_agent", "task_agent")
    workflow.add_edge("task_agent", "trajectory_agent")
    
    # Conditional edge after trajectory generation
    workflow.add_conditional_edges(
        "trajectory_agent",
        should_continue_after_trajectory,
        {
            "continue": "eval_agent",
            "human_in_loop": END,  # End for human approval
            "end_with_error": END
        }
    )
    
    # Conditional edge after evaluation
    workflow.add_conditional_edges(
        "eval_agent",
        should_continue_after_eval,
        {
            "continue": "report_agent",
            "end_with_error": END
        }
    )
    
    # Final edge
    workflow.add_edge("report_agent", END)
    
    # Compile the workflow
    print("Compiling workflow...")
    app = workflow.compile()
    
    return app


def run_workflow(initial_state: Optional[Dict[str, Any]] = None,
                 config_dir: str = "VLABench/configs/langgraph/agent_configs",
                 use_checkpointer: bool = False):
    """
    Run the complete VLABench workflow.
    
    Args:
        initial_state: Initial state for the workflow
        config_dir: Directory containing agent configurations
        use_checkpointer: Whether to use checkpointing for persistence
        
    Returns:
        Final state after workflow execution
    """
    # Create workflow
    app = create_workflow(config_dir)
    
    # Initialize checkpointer if requested
    checkpointer = MemorySaver() if use_checkpointer else None
    
    # Set up initial state
    if initial_state is None:
        initial_state = {}
    
    # Configuration for execution
    config = {
        "recursion_limit": 100
    }
    
    if checkpointer:
        config["checkpointer"] = checkpointer
        config["configurable"] = {"thread_id": "vlabench_workflow_1"}
    
    # Run the workflow
    print("\n" + "=" * 60)
    print("Starting VLABench Multi-Agent Workflow")
    print("=" * 60 + "\n")
    
    final_state = None
    for step_num, state_update in enumerate(app.stream(initial_state, config=config), 1):
        # Print progress
        node_name = list(state_update.keys())[0]
        print(f"\nStep {step_num}: {node_name}")
        print("-" * 40)
        
        # Update final state
        if node_name in state_update:
            final_state = state_update[node_name]
            
            # Check for errors
            if "error" in final_state:
                print(f"⚠️  Error detected: {final_state['error']}")
                
            # Check for human-in-loop
            if node_name == "trajectory_agent":
                trajectory = final_state.get("trajectory", {})
                if trajectory.get("status") == "human_approval_needed":
                    print("\n🔔 Human approval required!")
                    print(f"   Message: {trajectory.get('message', 'Please review and confirm.')}")
                    print("   Workflow paused. Resume after review.")
    
    print("\n" + "=" * 60)
    print("Workflow Execution Complete")
    print("=" * 60 + "\n")
    
    # Print summary
    if final_state:
        print_workflow_summary(final_state)
    
    return final_state


def print_workflow_summary(state: Dict[str, Any]):
    """
    Print a summary of the workflow execution.
    
    Args:
        state: Final workflow state
    """
    print("📊 Workflow Summary:")
    print("-" * 40)
    
    # Scenario
    scenario = state.get("scenario", {})
    if scenario:
        print(f"✅ Scenario: {scenario.get('name', 'N/A')}")
    
    # Task
    task = state.get("task", {})
    if task:
        print(f"✅ Task: {task.get('name', 'N/A')} ({task.get('type', 'N/A')})")
    
    # Trajectory
    trajectory = state.get("trajectory", {})
    if trajectory:
        status = trajectory.get("status", "N/A")
        if status == "completed":
            print(f"✅ Trajectory: Generated ({trajectory.get('path', 'N/A')})")
        elif status == "human_approval_needed":
            print(f"⏸️  Trajectory: Awaiting human approval")
        else:
            print(f"❌ Trajectory: {status}")
    
    # Evaluation
    evaluation = state.get("evaluation", {})
    if evaluation and evaluation.get("status") == "completed":
        metrics = evaluation.get("metrics", {})
        if metrics:
            print(f"✅ Evaluation: Completed")
            for metric, value in metrics.items():
                if isinstance(value, (int, float)):
                    print(f"   - {metric}: {value:.2%}")
    
    # Report
    report = state.get("report", {})
    if report and report.get("status") == "completed":
        print(f"✅ Report: Generated ({report.get('path', 'N/A')})")
    
    # Errors
    if state.get("error"):
        print(f"\n❌ Error: {state['error']}")
    
    print("-" * 40)


if __name__ == "__main__":
    # Example usage
    import argparse
    
    parser = argparse.ArgumentParser(description="Run VLABench LangGraph Workflow")
    parser.add_argument("--config-dir", type=str, 
                        default="VLABench/configs/langgraph/agent_configs",
                        help="Directory containing agent configuration files")
    parser.add_argument("--checkpoint", action="store_true",
                        help="Enable checkpointing for workflow persistence")
    args = parser.parse_args()
    
    # Run workflow with empty initial state
    final_state = run_workflow(
        initial_state={},
        config_dir=args.config_dir,
        use_checkpointer=args.checkpoint
    )
    
    # Save final state
    if final_state:
        import json
        output_file = "workflow_output.json"
        
        # Filter out non-serializable content
        serializable_state = {}
        for key, value in final_state.items():
            if key in ["scenario", "components", "object_classes", "trajectory", "evaluation", "report", "error"]:
                serializable_state[key] = value
            elif key == "task" and isinstance(value, dict):
                # Exclude the code field for JSON serialization
                serializable_state[key] = {k: v for k, v in value.items() if k != "code"}
        
        with open(output_file, 'w') as f:
            json.dump(serializable_state, f, indent=2)
        
        print(f"\n💾 Workflow output saved to: {output_file}")