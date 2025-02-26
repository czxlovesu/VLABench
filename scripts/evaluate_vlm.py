import argparse
import json
import os
from VLABench.evaluation.evaluator import VLMEvaluator
from VLABench.evaluation.model.vlm import *

def initialize_model(model_name, *args, **kwargs):
    cls = globals().get(model_name)
    if cls is None:
        raise ValueError(f"Model '{model_name}' not found in the current namespace.")
    
    return cls(*args, **kwargs)

def parse_args():
    parser = argparse.ArgumentParser(description="Run VLM benchmark with specified model and parameters.")
    parser.add_argument("--vlm_name", type=str, default="GPT_4v", choices=["GPT_4v", "Qwen2_VL", "InternVL2", "MiniCPM_V2_6", "GLM4v", "Llava_NeXT"], help="Name of the model class to instantiate")
    parser.add_argument("--save_interval", type=int, default=1, help="Interval for saving benchmark results")
    parser.add_argument("--few-shot-num", type=int, default=0, help="Number of few-shot examples")
    parser.add_argument("--eval-dimension", type=str, default=None, help="Path to the task list JSON file (optional)")
    parser.add_argument('--tasks', nargs='+', default=["select_fruit"], help="Specific tasks to run, work when eval-track is None")
    return parser.parse_args()

def main():
    args = parse_args()
    
    task_list = ["select_fruit"]
    
    evaluator = VLMEvaluator(
        tasks=task_list, 
        n_episodes=2,
        data_path=os.path.join(os.getenv("VLABENCH_ROOT"), "../dataset", "eval_vlm_v0/mesh_and_texture"),
        save_path=os.path.join(os.getenv("VLABENCH_ROOT"), "../logs/vlm"),
    )
    
    vlm = initialize_model(args.vlm_name) 
    
    if args.task_list_json is not None:
        try:
            pwd = os.getcwd()
            task_list_path = os.path.join(pwd, "../../configs/benchmark/taskList", args.task_list_json)
            with open(task_list_path, 'r') as f:
                task_list = json.load(f)
        except:
            task_list = None
    else:
        task_list = []

    evaluator.evaluate(
        vlm,
        save_interval=args.save_interval,
        few_shot_num=args.few_shot_num
    )
    result=evaluator.get_final_score_dict(args.vlm_name)
    with open(os.path.join(args.save_dir, args.vlm_name, "evaluation_result.json"), "w") as f:
        json.dump(result, f, indent=4)

if __name__ == "__main__":
    main()