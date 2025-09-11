N_SAMPLE=5
OFFSET=0
 
task_names=("sd_card_disposal" ) # add more task here
save_dir="vlabench_dataset"
# /home/vla/Downloads/VLABench/vlabench_dataset

for task_name in "${task_names[@]}"; do # add more process here
    commands=(
        "python scripts/trajectory_generation.py --task-name $task_name --n-sample $N_SAMPLE --start-id $((0 * N_SAMPLE + OFFSET)) --save-dir $save_dir"
        "python scripts/trajectory_generation.py --task-name $task_name --n-sample $N_SAMPLE --start-id $((1 * N_SAMPLE + OFFSET)) --save-dir $save_dir"
    )

    echo "Running tasks for: $task_name"

    for cmd in "${commands[@]}"; do
        echo "Starting: $cmd"
        $cmd &
    done

    wait  # 等待当前任务名称的所有命令执行完成
    echo "Completed tasks for: $task_name"
done

echo "All processes for all tasks have completed."