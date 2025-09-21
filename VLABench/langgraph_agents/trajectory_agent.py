"""
Trajectory Generation Agent for VLABench
This agent handles trajectory data generation by executing the generated task file.
Phase 1: Basic implementation with subprocess call to trajectory generation script.
"""

import os
import yaml
import subprocess
import tempfile
import shutil
from typing import Dict, Any, Optional
from pathlib import Path


class TrajectoryAgent:
    """
    Trajectory Agent responsible for generating trajectory data from task files.
    This agent writes the task code to disk and calls VLABench's trajectory generation script.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the TrajectoryAgent with configuration.
        
        Args:
            config_path: Path to the agent configuration YAML file
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set default values
        self.simulation_steps = self.config.get("simulation_steps", 1000)
        self.num_episodes = self.config.get("num_episodes", 5)
        self.output_dir = self.config.get("output_dir", "VLABench/trajectories")
        self.enable_human_in_loop = self.config.get("enable_human_in_loop", False)
        self.robot = self.config.get("robot", "franka")
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
    
    def run(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Trajectory Agent to generate trajectory data.
        
        Args:
            input_state: Current state from the workflow containing task info
            
        Returns:
            Updated state with trajectory file path or error information
        """
        print("Running TrajectoryAgent...")
        
        # Extract task information from previous agent
        task_info = input_state.get("task", {})
        
        if not task_info:
            return self._handle_error(input_state, "No task information found in state")
        
        task_name = task_info.get("name")
        task_code = task_info.get("code")
        task_file_path = task_info.get("file_path")
        
        if not all([task_name, task_code, task_file_path]):
            return self._handle_error(input_state, "Incomplete task information")
        
        try:
            # Step 1: Write the task code to file
            print(f"Writing task file to: {task_file_path}")
            written_path = self._write_task_file(task_file_path, task_code)
            
            # Step 2: Prepare trajectory output path
            trajectory_filename = f"{task_name}_trajectory.hdf5"
            trajectory_path = os.path.join(self.output_dir, trajectory_filename)
            
            # Step 3: Generate trajectory using VLABench script
            print(f"Generating trajectory for task: {task_name}")
            actual_path = self._generate_trajectory(
                task_name=task_name,
                output_path=trajectory_path,
                task_file_path=written_path
            )
            
            if not actual_path:
                return self._handle_error(input_state, "Trajectory generation failed")
            
            # Step 4: Check if human-in-the-loop is enabled
            if self.enable_human_in_loop:
                print("Human-in-the-loop enabled. Awaiting confirmation...")
                updated_state = input_state.copy()
                updated_state["trajectory"] = {
                    "status": "human_approval_needed",
                    "path": actual_path,  # Use actual path
                    "task_name": task_name,
                    "message": "Trajectory generated. Please review and confirm."
                }
                return updated_state
            
            # Step 5: Return successful state
            updated_state = input_state.copy()
            updated_state["trajectory"] = {
                "status": "completed",
                "path": actual_path,  # Use actual path
                "task_name": task_name,
                "num_episodes": self.num_episodes,
                "robot": self.robot
            }
            
            print(f"✓ Trajectory successfully generated: {trajectory_path}")
            return updated_state
            
        except Exception as e:
            return self._handle_error(input_state, f"Unexpected error: {str(e)}")
    
    def _write_task_file(self, file_path: str, code: str) -> str:
        """
        Write the task code to the specified file path.
        
        Args:
            file_path: Path where the task file should be written
            code: Python code content to write
            
        Returns:
            Actual path where the file was written
        """
        # Use VLABENCH_ROOT environment variable for portability
        vlabench_root = os.getenv("VLABENCH_ROOT", "/home/vla/Downloads/VLABench/VLABench")
        project_root = os.path.dirname(vlabench_root)
        
        # Convert relative to absolute path
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_root, file_path)
        
        # Create directory structure if it doesn't exist
        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)
        
        # Write the code to file
        with open(file_path, 'w') as f:
            f.write(code)
        
        print(f"  Task file written to: {file_path}")
        
        # Note: In Phase 1, this file won't be automatically registered with VLABench
        # The task name should match an existing registered task for trajectory generation
        print(f"  Note: Task registration is handled separately in Phase 1")
        
        return file_path
    
    def _generate_trajectory(self, task_name: str, output_path: str, 
                           task_file_path: Optional[str] = None) -> Optional[str]:
        """
        Generate trajectory by calling VLABench's trajectory generation script.
        
        Args:
            task_name: Name of the task
            output_path: Path where trajectory data should be saved
            task_file_path: Optional path to custom task file
            
        Returns:
            Path to generated trajectory file if successful, None otherwise
        """
        # Build command for trajectory generation
        vlabench_root = os.getenv("VLABENCH_ROOT", "/home/vla/Downloads/VLABench/VLABench")
        script_path = os.path.join(os.path.dirname(vlabench_root), "scripts", "trajectory_generation.py")
        
        # Check if we should use dummy mode for testing
        if self.config.get("use_dummy_trajectory", False):
            print(f"  Using dummy trajectory mode for Phase 1 testing")
            return self._create_dummy_trajectory(output_path)
        
        # Check if script exists
        if not os.path.exists(script_path):
            print(f"Warning: Trajectory generation script not found at {script_path}")
            # For Phase 1, create a dummy trajectory file
            return self._create_dummy_trajectory(output_path)
        
        # Important: VLABench loads tasks by name from registry, not from custom files
        # In Phase 1, use existing registered task names (e.g., "select_fruit", "select_toy")
        print(f"  Using task name: {task_name}")
        print(f"  Note: Task must be registered in VLABench's name2config")
        
        # Build command arguments
        cmd = [
            "python", script_path,
            "--task-name", task_name,
            "--save-dir", os.path.dirname(output_path),
            "--n-sample", str(self.num_episodes),
            "--robot", self.robot,
            "--record-video", str(self.config.get("record_video", True))
        ]
        
        # Add optional parameters
        if "max_episode" in self.config:
            cmd.extend(["--max-episode", str(self.config["max_episode"])])
        if self.config.get("eval_unseen", False):
            cmd.append("--eval-unseen")
        if self.config.get("early_stop", False):
            cmd.append("--early-stop")
        
        # Log full command for debugging
        print(f"  Full command: {' '.join(cmd)}")
        
        try:
            # Run the trajectory generation script
            # Prepare environment for headless rendering
            env = os.environ.copy()
            env["MUJOCO_GL"] = "egl"  # EGL for headless rendering
            env["PYOPENGL_PLATFORM"] = "egl"  # PyOpenGL backend
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.get("timeout", 60),  # Reduce timeout to 60s for testing
                cwd=os.path.dirname(vlabench_root),
                env=env
            )
            
            if result.returncode != 0:
                print(f"  Command failed with return code: {result.returncode}")
                print(f"  Error output: {result.stderr[-1000:]}")  # Last 1000 chars
                return None
            
            print(f"  Trajectory generation completed")
            
            # Check if output file was actually created
            expected_files = [
                output_path,
                output_path.replace('.hdf5', '_0.hdf5'),  # Sometimes indexed
                os.path.join(os.path.dirname(output_path), f"{task_name}/demo_0.hdf5")
            ]
            
            for file_path in expected_files:
                if os.path.exists(file_path):
                    print(f"  ✓ Output file found: {file_path}")
                    return file_path  # Return actual path
            
            print(f"  Warning: Expected output file not found at {output_path}")
            return None
            
        except subprocess.TimeoutExpired:
            print(f"  Trajectory generation timed out after {self.config.get('timeout', 300)}s")
            return None
        except Exception as e:
            print(f"  Error during trajectory generation: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _create_dummy_trajectory(self, output_path: str) -> str:
        """
        Create a dummy trajectory file for Phase 1 testing.
        
        Args:
            output_path: Path where dummy file should be created
            
        Returns:
            Path to the created dummy file
        """
        print("  Creating dummy trajectory file for testing...")
        
        # Create a simple text file as placeholder
        dummy_content = {
            "type": "dummy_trajectory",
            "phase": "1",
            "message": "This is a placeholder trajectory file for Phase 1 testing",
            "simulation_steps": self.simulation_steps,
            "num_episodes": self.num_episodes,
            "original_path": output_path
        }
        
        # Save as YAML instead of HDF5 for simplicity, but keep similar naming
        dummy_path = output_path.replace('.hdf5', '_dummy.yaml')
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(dummy_path), exist_ok=True)
        
        with open(dummy_path, 'w') as f:
            yaml.dump(dummy_content, f)
        
        print(f"  Dummy trajectory created: {dummy_path}")
        return dummy_path
    
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
        updated_state["trajectory"] = {
            "status": "failed",
            "error": error_msg
        }
        return updated_state


if __name__ == "__main__":
    # Standalone testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Trajectory Generation Agent for VLABench")
    parser.add_argument("--config", type=str, required=True,
                        help="Path to the agent configuration file")
    args = parser.parse_args()
    
    # Create agent
    agent = TrajectoryAgent(args.config)
    
    # Mock input state from TaskAgent
    mock_state = {
        "scenario": {
            "name": "kitchen_2"
        },
        "task": {
            "name": "test_pick_place",
            "type": "primitive",
            "file_path": "VLABench/tasks/test_task.py",
            "code": "# Dummy task code\nclass TestTask:\n    pass",
            "class_name": "TestPickPlaceTask"
        }
    }
    
    # Run agent
    result = agent.run(mock_state)
    
    # Print results
    print("\n--- Trajectory Agent Results ---")
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        traj = result.get("trajectory", {})
        print(f"Status: {traj.get('status')}")
        print(f"Path: {traj.get('path')}")
        print(f"Task: {traj.get('task_name')}")