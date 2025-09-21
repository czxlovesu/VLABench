"""
Task Generation Agent for VLABench
This agent generates complete Python task files based on scenario configuration.
Phase 1: Hardcoded template-based generation without LLM reasoning.
"""

import os
import yaml
import textwrap
from typing import Dict, Any, List
from datetime import datetime

from VLABench.robots import *
from VLABench.tasks import *


class TaskAgent:
    """
    Task Agent responsible for generating Python task class files.
    This is a Phase 1 implementation using hardcoded templates without LLM integration.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the TaskAgent with configuration.
        
        Args:
            config_path: Path to the agent configuration YAML file
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # In Phase 2+, we would initialize LLM here
        # self.llm = self._get_llm_model()
    
    def run(self, input_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Task Agent to generate a Python task file.
        
        Args:
            input_state: Current state from the LangGraph workflow containing scenario info
            
        Returns:
            Updated state with task file path and code content
        """
        print("Running TaskAgent...")
        
        # Extract scenario information from previous agent
        scenario_info = input_state.get("scenario", {})
        components = input_state.get("components", [])
        has_container = input_state.get("has_container", False)
        
        # Read task configuration
        task_type = self.config.get("task_type", "primitive")
        task_name = self.config.get("task_name", "pick_and_place_task")
        
        # Generate the Python task code
        task_code = self._generate_task_code(
            task_name=task_name,
            task_type=task_type,
            scenario_info=scenario_info,
            components=components,
            has_container=has_container
        )
        
        # Define file path for the generated task
        file_name = f"langgraph_generated_{task_name}.py"
        file_path = os.path.join("VLABench", "tasks", "hierarchical_tasks", 
                                  "primitive" if task_type == "primitive" else "composite",
                                  file_name)
        
        # Create updated state preserving all previous state data
        updated_state = input_state.copy()
        updated_state["task"] = {
            "name": task_name,
            "type": task_type,
            "file_path": file_path,
            "code": task_code,
            "class_name": self._generate_class_name(task_name)
        }
        
        return updated_state
    
    def _generate_class_name(self, task_name: str) -> str:
        """
        Convert task_name to CamelCase class name.
        
        Args:
            task_name: Snake case task name
            
        Returns:
            CamelCase class name
        """
        # Convert snake_case to CamelCase
        parts = task_name.split('_')
        class_name = ''.join(word.capitalize() for word in parts) + "Task"
        return class_name
    
    def _generate_task_code(self, task_name: str, task_type: str, 
                           scenario_info: Dict, components: List[Dict], has_container: bool = False) -> str:
        """
        Generate the complete Python task file code.
        Phase 1: Using hardcoded templates with basic logic.
        
        Args:
            task_name: Name of the task
            task_type: Type of task (primitive/composite)
            scenario_info: Scenario configuration from ScenarioAgent
            components: Component list from ScenarioAgent
            
        Returns:
            Complete Python code for the task file
        """
        class_name = self._generate_class_name(task_name)
        config_manager_name = class_name.replace("Task", "ConfigManager")
        
        # Container classes to check against
        container_classes = ["CommonContainer", "FlatContainer", "ContainerWithDrawer", 
                             "Microwave", "Vase", "CoffeeMachine", "Fridge"]
        
        # Separate objects and containers from components
        target_objects = []
        containers = []
        
        for comp in components:
            if comp.get("name") == "table":
                continue
            if comp.get("class") in container_classes:
                containers.append(comp)
            else:
                target_objects.append(comp)
        
        # If has_container but no containers found, check if any object is actually a container
        if has_container and not containers:
            # Some objects might be containers based on name pattern
            for obj in target_objects:
                obj_name = obj.get("name", "")
                if any(cont in obj_name for cont in ["tray", "basket", "dish", "plate", "bowl"]):
                    containers.append(obj)
                    target_objects.remove(obj)
                    break
        
        # Select target entity and container
        # Use first non-container object or derive from first component
        if target_objects:
            target_entity = target_objects[0]["name"]
        elif components:
            # Fallback: use first non-table component
            non_table = [c for c in components if c.get("name") != "table"]
            target_entity = non_table[0]["name"] if non_table else "object_1"
        else:
            target_entity = "object_1"
        
        # Select container if available, otherwise use tray as safe default
        target_container = containers[0]["name"] if containers else "tray_1"
        
        # Extract base class names (remove _number suffix)
        target_entity_class = target_entity.rsplit('_', 1)[0] if '_' in target_entity else target_entity
        target_container_class = target_container.rsplit('_', 1)[0] if '_' in target_container else target_container
        
        # Generate the task file code
        code = textwrap.dedent(f'''
        """
        Auto-generated task file by LangGraph TaskAgent
        Task: {task_name}
        Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        import random
        import numpy as np
        from functools import partial
        from VLABench.tasks.dm_task import LM4ManipBaseTask
        from VLABench.tasks.hierarchical_tasks.primitive.base import PrimitiveTask
        from VLABench.tasks.config_manager import BenchTaskConfigManager
        from VLABench.utils.register import register
        from VLABench.utils.skill_lib import SkillLib
        from VLABench.utils.utils import flatten_list, grid_sample
        
        
        @register.add_config_manager("{task_name}")
        class {config_manager_name}(BenchTaskConfigManager):
            """Configuration manager for {task_name} task."""
            
            def __init__(self, 
                         task_name,
                         num_objects=[3, 4],
                         **kwargs):
                super().__init__(task_name, num_objects, **kwargs)
                # Task-specific initialization
                self.scenario_name = "{scenario_info.get('name', 'default')}"
                self.components = {components}
                
            def load_init_containers(self, init_container):
                """Load initial containers for the task."""
                pass
            
            def get_instruction(self, target_entity, target_container, **kwargs):
                """Generate task instruction."""
                # Keep placeholders for instruction template
                instruction = [f"Pick up the {{target_entity}} and place it in the {{target_container}}"]
                self.config["task"]["instructions"] = instruction
            
            def get_condition_config(self, target_entity, target_container, **kwargs):
                """Define success conditions for the task."""
                # Use actual instance names for conditions
                conditions_config = dict(
                    contain=dict(
                        container="{target_container}",  # Use actual instance name like plate_1
                        entities=["{target_entity}"]      # Use actual instance name like apple_1
                    )
                )
                self.config["task"]["conditions"] = conditions_config
        
        
        @register.add_task("{task_name}")
        class {class_name}(PrimitiveTask):
            """Main task class for {task_name}."""
            
            def __init__(self, task_name, robot, **kwargs):
                """Initialize the task."""
                super().__init__(task_name, robot=robot, **kwargs)
                # Task is initialized through parent class which handles config_manager
                # The parent class will set self.target_entity and self.target_container from config_manager
            
            def get_expert_skill_sequence(self, physics):
                """Get the expert skill sequence for this task."""
                # Simple pick and place sequence
                skill_sequence = [
                    partial(SkillLib.pick, target_entity_name=self.target_entity),
                    partial(SkillLib.place, target_container_name=self.target_container),
                ]
                return skill_sequence
        ''').strip()
        
        return code


if __name__ == "__main__":
    # Standalone testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Task Generation Agent for VLABench")
    parser.add_argument("--config", type=str, required=True,
                        help="Path to the agent configuration file")
    args = parser.parse_args()
    
    # Create agent
    agent = TaskAgent(args.config)
    
    # Mock input state from ScenarioAgent
    mock_state = {
        "scenario": {
            "name": "kitchen_2",
            "xml_path": "kitchen_2/kitchen.xml",
            "candidate_pos": [[0, 0, 0], [-2, -1, 0]]
        },
        "components": [
            {"name": "table", "xml_path": "obj/meshes/table/table.xml", "class": "Table"},
            {"name": "apple_1", "xml_path": "obj/meshes/fruit/apple/apple.xml", "class": "Fruit"},
            {"name": "plate_1", "xml_path": "obj/meshes/containers/plate.xml", "class": "FlatContainer"}
        ]
    }
    
    # Run agent
    result = agent.run(mock_state)
    
    # Print results
    print(f"\nGenerated task file: {result['task']['file_path']}")
    print(f"Task class name: {result['task']['class_name']}")
    print("\n--- Generated Code ---")
    print(result['task']['code'])