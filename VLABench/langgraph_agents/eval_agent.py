"""
Evaluation Agent for VLABench
This agent handles model evaluation by calling VLABench's evaluation scripts.
Phase 1: Basic implementation focusing on success rate metrics.
"""

import os
import json
import yaml
import subprocess
from typing import Dict, Any, Optional, List
from pathlib import Path


class EvalAgent:
    """
    Evaluation Agent responsible for running model evaluation on generated trajectories.
    This agent calls VLABench's evaluation scripts to compute metrics.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the EvalAgent with configuration.
        
        Args:
            config_path: Path to the agent configuration YAML file
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set default values
        self.eval_track = self.config.get("eval_track", "vla")  # vla or vlm
        self.model_name = self.config.get("model_name", "random")
        self.output_dir = self.config.get("output_dir", "VLABench/eval_results")
        self.n_episodes = self.config.get("n_episodes", 1)
        self.metrics = self.config.get("metrics", ["success_rate"])
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def run(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Evaluation Agent to evaluate model performance.
        
        Args:
            input_state: Current state from the workflow containing trajectory info
            
        Returns:
            Updated state with evaluation results or error information
        """
        print("Running EvalAgent...")
        
        # Extract trajectory information from previous agent
        trajectory_info = input_state.get("trajectory", {})
        
        if not trajectory_info or trajectory_info.get("status") != "completed":
            return self._handle_error(input_state, "No completed trajectory found in state")
        
        trajectory_path = trajectory_info.get("path")
        task_name = trajectory_info.get("task_name", input_state.get("task", {}).get("name"))
        
        if not trajectory_path:
            return self._handle_error(input_state, "Trajectory path not found")
        
        # Phase 1: Check if trajectory file exists (handle dummy files)
        if trajectory_path.endswith("_dummy.yaml"):
            print("  Phase 1: Using dummy evaluation for test trajectory")
            return self._create_dummy_evaluation(input_state, task_name)
        
        try:
            # Prepare evaluation output path
            eval_filename = f"{task_name}_{self.model_name}_eval.json"
            eval_path = os.path.join(self.output_dir, eval_filename)
            
            # Run evaluation based on track
            print(f"Evaluating {self.model_name} on task: {task_name}")
            
            if self.eval_track == "vla":
                success = self._evaluate_vla(
                    task_name=task_name,
                    trajectory_path=trajectory_path,
                    output_path=eval_path
                )
            elif self.eval_track == "vlm":
                success = self._evaluate_vlm(
                    task_name=task_name,
                    trajectory_path=trajectory_path,
                    output_path=eval_path
                )
            else:
                return self._handle_error(input_state, f"Unknown eval track: {self.eval_track}")
            
            if not success:
                return self._handle_error(input_state, "Evaluation failed")
            
            # Load and parse evaluation results
            if os.path.exists(eval_path):
                with open(eval_path, 'r') as f:
                    eval_results = json.load(f)
            else:
                # Create simple results if file doesn't exist
                eval_results = self._create_basic_results(task_name)
                with open(eval_path, 'w') as f:
                    json.dump(eval_results, f, indent=2)
            
            # Extract key metrics
            metrics_summary = self._extract_metrics(eval_results)
            
            # Update state with evaluation results
            updated_state = input_state.copy()
            updated_state["evaluation"] = {
                "status": "completed",
                "report_path": eval_path,
                "task_name": task_name,
                "model_name": self.model_name,
                "eval_track": self.eval_track,
                "metrics": metrics_summary,
                "raw_results": eval_results
            }
            
            print(f"✓ Evaluation completed: {eval_path}")
            print(f"  Metrics: {metrics_summary}")
            
            return updated_state
            
        except Exception as e:
            return self._handle_error(input_state, f"Unexpected error: {str(e)}")
    
    def _evaluate_vla(self, task_name: str, trajectory_path: str, output_path: str) -> bool:
        """
        Run VLA (Vision-Language-Action) model evaluation.
        
        Args:
            task_name: Name of the task
            trajectory_path: Path to trajectory data
            output_path: Path where evaluation results should be saved
            
        Returns:
            True if successful, False otherwise
        """
        vlabench_root = os.getenv("VLABENCH_ROOT", "/home/vla/Downloads/VLABench/VLABench")
        script_path = os.path.join(os.path.dirname(vlabench_root), "scripts", "evaluate_policy.py")
        
        # Check if script exists
        if not os.path.exists(script_path):
            print(f"  Warning: Evaluation script not found at {script_path}")
            return False
        
        # Build command
        cmd = [
            "python", script_path,
            "--tasks", task_name,
            "--n-episode", str(self.n_episodes),
            "--policy", self.model_name,
            "--save-dir", os.path.dirname(output_path),
            "--metrics"
        ] + self.metrics
        
        # Add model checkpoint if specified
        if "model_ckpt" in self.config:
            cmd.extend(["--model_ckpt", self.config["model_ckpt"]])
        if "lora_ckpt" in self.config:
            cmd.extend(["--lora_ckpt", self.config["lora_ckpt"]])
        
        print(f"  Executing VLA evaluation: {' '.join(cmd[:6])}...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.get("timeout", 600),  # 10 minutes default
                cwd=os.path.dirname(vlabench_root),
                env={**os.environ, "MUJOCO_GL": "egl"}
            )
            
            if result.returncode != 0:
                print(f"  Evaluation failed with return code: {result.returncode}")
                print(f"  Error: {result.stderr[-500:]}")
                return False
            
            print("  VLA evaluation completed")
            return True
            
        except subprocess.TimeoutExpired:
            print("  Evaluation timed out")
            return False
        except Exception as e:
            print(f"  Error during evaluation: {e}")
            return False
    
    def _evaluate_vlm(self, task_name: str, trajectory_path: str, output_path: str) -> bool:
        """
        Run VLM (Vision-Language Model) evaluation.
        
        Args:
            task_name: Name of the task
            trajectory_path: Path to trajectory data
            output_path: Path where evaluation results should be saved
            
        Returns:
            True if successful, False otherwise
        """
        vlabench_root = os.getenv("VLABENCH_ROOT", "/home/vla/Downloads/VLABench/VLABench")
        script_path = os.path.join(os.path.dirname(vlabench_root), "scripts", "evaluate_vlm.py")
        
        # Check if script exists
        if not os.path.exists(script_path):
            print(f"  Warning: VLM evaluation script not found at {script_path}")
            return False
        
        # Build command
        cmd = [
            "python", script_path,
            "--task", task_name,
            "--model", self.model_name,
            "--save-dir", os.path.dirname(output_path)
        ]
        
        print(f"  Executing VLM evaluation: {' '.join(cmd[:4])}...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.get("timeout", 600),
                cwd=os.path.dirname(vlabench_root)
            )
            
            if result.returncode != 0:
                print(f"  VLM evaluation failed: {result.stderr[-500:]}")
                return False
            
            print("  VLM evaluation completed")
            return True
            
        except Exception as e:
            print(f"  Error during VLM evaluation: {e}")
            return False
    
    def _create_dummy_evaluation(self, input_state: Dict[str, Any], task_name: str) -> Dict[str, Any]:
        """
        Create dummy evaluation results for Phase 1 testing.
        
        Args:
            input_state: Current state
            task_name: Name of the task
            
        Returns:
            Updated state with dummy evaluation
        """
        print("  Creating dummy evaluation results for testing...")
        
        # Create dummy evaluation results
        dummy_results = {
            "task": task_name,
            "model": self.model_name,
            "phase": "1_testing",
            "metrics": {
                "success_rate": 0.75,
                "progress_score": 0.82,
                "intention_score": 0.68,
                "dag_match": 0.70
            },
            "episodes": self.n_episodes,
            "message": "This is a dummy evaluation for Phase 1 testing"
        }
        
        # Save dummy results
        eval_filename = f"{task_name}_{self.model_name}_dummy_eval.json"
        eval_path = os.path.join(self.output_dir, eval_filename)
        
        with open(eval_path, 'w') as f:
            json.dump(dummy_results, f, indent=2)
        
        # Update state
        updated_state = input_state.copy()
        updated_state["evaluation"] = {
            "status": "completed",
            "report_path": eval_path,
            "task_name": task_name,
            "model_name": self.model_name,
            "eval_track": self.eval_track,
            "metrics": dummy_results["metrics"],
            "raw_results": dummy_results
        }
        
        print(f"  Dummy evaluation created: {eval_path}")
        return updated_state
    
    def _create_basic_results(self, task_name: str) -> Dict[str, Any]:
        """
        Create basic evaluation results structure.
        
        Args:
            task_name: Name of the task
            
        Returns:
            Basic results dictionary
        """
        return {
            "task": task_name,
            "model": self.model_name,
            "metrics": {
                "success_rate": 0.0,
                "progress_score": 0.0,
                "intention_score": 0.0
            },
            "episodes": self.n_episodes
        }
    
    def _extract_metrics(self, eval_results: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract key metrics from evaluation results.
        
        Args:
            eval_results: Raw evaluation results
            
        Returns:
            Dictionary of extracted metrics
        """
        metrics = {}
        
        # Try different possible keys for metrics
        if "metrics" in eval_results:
            metrics = eval_results["metrics"]
        elif "results" in eval_results:
            metrics = eval_results["results"]
        else:
            # Try to extract from top level
            for key in ["success_rate", "progress_score", "intention_score", "dag_match"]:
                if key in eval_results:
                    metrics[key] = eval_results[key]
        
        return metrics
    
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
        updated_state["evaluation"] = {
            "status": "failed",
            "error": error_msg
        }
        return updated_state


if __name__ == "__main__":
    # Standalone testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluation Agent for VLABench")
    parser.add_argument("--config", type=str, required=True,
                        help="Path to the agent configuration file")
    args = parser.parse_args()
    
    # Create agent
    agent = EvalAgent(args.config)
    
    # Mock input state
    mock_state = {
        "trajectory": {
            "status": "completed",
            "path": "VLABench/trajectories/test_task_dummy.yaml",
            "task_name": "test_task"
        },
        "task": {
            "name": "test_task"
        }
    }
    
    # Run agent
    result = agent.run(mock_state)
    
    # Print results
    print("\n--- Evaluation Agent Results ---")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        eval_info = result.get("evaluation", {})
        print(f"Status: {eval_info.get('status')}")
        print(f"Report: {eval_info.get('report_path')}")
        print(f"Metrics: {eval_info.get('metrics')}")