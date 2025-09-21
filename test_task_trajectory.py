#!/usr/bin/env python3
"""
通用任务轨迹生成测试脚本
基于test_pour_trajectory.py改进，支持测试任意VLABench任务的轨迹采集效果
使用方法: python test_task_trajectory.py [task_name] [--max_skills N]
"""
import os
import sys
import numpy as np
import argparse

# Add VLABench to path
sys.path.append('/home/vla/Downloads/VLABench')

from VLABench.envs import load_env
from VLABench.robots import *  # Import robots
from VLABench.tasks import *   # Import tasks

# Set environment variables
os.environ["VLABENCH_ROOT"] = "/home/vla/Downloads/VLABench/VLABench"
os.environ["MUJOCO_GL"] = "egl"

def test_task_trajectory(task_name, max_skills=2):
    """测试任意任务的轨迹生成效果"""
    
    print(f"🧪 Testing {task_name} Trajectory Generation...")
    print("=" * 50)
    
    try:
        # 加载环境
        print(f"📝 Loading {task_name} environment...")
        env = load_env(task_name)
        
        print("🔄 Resetting environment...")
        env.reset()
        
        print("🎯 Getting expert skill sequence...")
        skill_sequence = env.get_expert_skill_sequence()
        
        if not skill_sequence:
            print("❌ No skill sequence found!")
            return False
            
        print(f"✅ Found {len(skill_sequence)} skills in sequence:")
        for i, skill in enumerate(skill_sequence):
            print(f"   {i+1}. {skill}")
        
        # 获取任务指令
        try:
            if hasattr(env.task, 'get_instruction'):
                instruction = env.task.get_instruction()
                print(f"📋 Task instruction: {instruction}")
        except Exception as e:
            print(f"⚠️ Could not get instruction: {e}")
        
        print(f"🚀 Executing skills (testing first {max_skills} skills)...")
        total_observations = []
        total_waypoints = []
        
        # 测试指定数量的技能避免超时
        skills_to_test = min(max_skills, len(skill_sequence))
        successful_skills = 0
        
        for i, skill in enumerate(skill_sequence[:skills_to_test]):
            print(f"\n🔧 Executing skill {i+1}/{skills_to_test}: {skill.func.__name__}")
            
            try:
                # 记录执行前状态
                pre_obs = env.get_observation()
                
                # 执行技能
                obs, waypoints, stage_success, task_success = skill(env)
                
                if obs:
                    total_observations.extend(obs)
                    print(f"   ✅ Generated {len(obs)} observations")
                else:
                    print("   ⚠️ No observations generated")
                
                if waypoints:
                    total_waypoints.extend(waypoints)
                    print(f"   ✅ Generated {len(waypoints)} waypoints")
                else:
                    print("   ⚠️ No waypoints generated")
                
                print(f"   📊 Stage success: {stage_success}")
                print(f"   📊 Task success: {task_success}")
                
                if stage_success:
                    successful_skills += 1
                    
                # 渲染当前状态用于调试
                try:
                    current_image = env.render(camera_id=2, height=320, width=320)
                    print(f"   🎨 Rendered frame: {current_image.shape}")
                except Exception as e:
                    print(f"   ⚠️ Rendering failed: {e}")
                
            except Exception as e:
                print(f"   ❌ Skill {i+1} execution failed: {e}")
                import traceback
                traceback.print_exc()
                break
        
        # 获取最终状态
        try:
            final_obs = env.get_observation()
            print(f"\n🎯 Final observation keys: {list(final_obs.keys())}")
        except Exception as e:
            print(f"⚠️ Could not get final observation: {e}")
        
        # 统计结果
        print(f"\n📊 Trajectory Generation Results:")
        print(f"   Task: {task_name}")
        print(f"   Skills tested: {skills_to_test}/{len(skill_sequence)}")
        print(f"   Successful skills: {successful_skills}")
        print(f"   Total observations: {len(total_observations)}")
        print(f"   Total waypoints: {len(total_waypoints)}")
        
        # 分析轨迹数据质量
        if total_observations:
            print(f"\n🔍 Trajectory Data Analysis:")
            sample_obs = total_observations[0]
            print(f"   Observation keys: {list(sample_obs.keys())}")
            
            # 检查关键数据
            if 'robot0_eef_pos' in sample_obs:
                eef_positions = [obs['robot0_eef_pos'] for obs in total_observations 
                               if 'robot0_eef_pos' in obs]
                if eef_positions:
                    start_pos = eef_positions[0]
                    end_pos = eef_positions[-1]
                    total_distance = np.linalg.norm(end_pos - start_pos)
                    print(f"   End-effector travel distance: {total_distance:.3f}m")
            
            if 'rgb' in sample_obs and len(sample_obs['rgb']) > 2:
                rgb_shape = sample_obs['rgb'][2].shape
                print(f"   RGB image shape: {rgb_shape}")
        
        # 成功判断
        success = (successful_skills > 0 and 
                  len(total_observations) > 0 and 
                  len(total_waypoints) > 0)
        
        return success
        
    except Exception as e:
        print(f"❌ Trajectory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            env.close()
        except:
            pass

def main():
    parser = argparse.ArgumentParser(description='通用任务轨迹生成测试脚本')
    parser.add_argument('task_name', nargs='?', default='high_temp_harm',
                       help='要测试的任务名称 (默认: high_temp_harm)')
    parser.add_argument('--max_skills', type=int, default=2,
                       help='最大测试技能数量 (默认: 2)')
    
    args = parser.parse_args()
    
    print(f"🚀 Starting trajectory test for task: {args.task_name}")
    print(f"🔧 Max skills to test: {args.max_skills}")
    
    success = test_task_trajectory(args.task_name, args.max_skills)
    
    print("=" * 50)
    if success:
        print("🎉 TRAJECTORY TEST SUCCESSFUL!")
        print(f"✅ Task '{args.task_name}' can generate valid trajectories")
        print("📊 Trajectory data includes:")
        print("   - Robot observations")
        print("   - Waypoint sequences") 
        print("   - Visual frames")
        print("\n🚀 Task is ready for dataset generation and VLA training!")
    else:
        print("⚠️  TRAJECTORY TEST FAILED!")
        print(f"❌ Task '{args.task_name}' has trajectory generation issues")
        print("💡 Possible issues:")
        print("   1. Skill sequence execution errors")
        print("   2. Physics simulation problems")
        print("   3. Robot control failures")
        print("   4. Observation collection issues")
        print("\n🚨 Debug and fix issues before using for dataset generation!")

if __name__ == "__main__":
    main()