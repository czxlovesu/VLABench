#!/usr/bin/env python3
"""
通用任务可视化测试脚本
基于test_baby_visual.py改进，支持测试任意VLABench任务的加载和视觉效果
使用方法: python test_task_visual.py [task_name]
"""
import os
import sys
import numpy as np
import argparse

# Add VLABench to path
sys.path.append('/home/vla/Downloads/VLABench')

from VLABench.envs import load_env
from VLABench.robots import *  # 关键：导入robots注册信息
from VLABench.tasks import *   # 关键：导入tasks注册信息

# Set environment variables  
os.environ["VLABENCH_ROOT"] = "/home/vla/Downloads/VLABench/VLABench"
os.environ["MUJOCO_GL"] = "egl"  # 可视化模式，不是headless

def test_task_visual(task_name):
    """通用任务可视化测试"""
    
    print(f"🎨 Visual Test: {task_name}")
    print("=" * 50)
    
    try:
        # 加载环境
        print(f"📝 Loading {task_name} environment...")
        env = load_env(task_name)  # 使用默认robot="franka"
        
        print("🔄 Resetting environment...")
        env.reset()
        
        # 渲染初始场景
        print("🎨 Rendering initial scene...")
        initial_image = env.render(camera_id=2, height=640, width=640)
        print(f"✅ Rendered image shape: {initial_image.shape}")
        
        # 保存初始场景图片
        from PIL import Image
        initial_img = Image.fromarray(initial_image)
        initial_img.save(f"/home/vla/Downloads/VLABench/{task_name}_scene_initial.png")
        print(f"💾 Saved initial scene: {task_name}_scene_initial.png")
        
        print("🎯 Getting expert skill sequence...")
        skill_sequence = env.get_expert_skill_sequence()
        
        if not skill_sequence:
            print("❌ No skill sequence found!")
            return False
            
        print(f"✅ Found {len(skill_sequence)} skills in sequence:")
        for i, skill in enumerate(skill_sequence):
            print(f"   {i+1}. {skill}")
        
        # 收集关键帧进行可视化
        print("🎬 Collecting visual trajectory...")
        key_frames = []
        total_observations = 0
        total_waypoints = 0
        
        # 执行第一个技能并收集视觉数据
        for i, skill in enumerate(skill_sequence[:1]):  # 只测试第一个技能避免超时
            print(f"\n🔧 Executing skill {i+1}: {skill.func.__name__}")
            try:
                obs, waypoints, stage_success, task_success = skill(env)
                
                if obs:
                    total_observations += len(obs)
                    # 提取RGB图像数据用于可视化
                    frames = [o['rgb'][2] for o in obs if 'rgb' in o and len(o['rgb']) > 2]
                    key_frames.extend(frames)
                    print(f"   ✅ Collected {len(obs)} observations, {len(frames)} visual frames")
                    
                if waypoints:
                    total_waypoints += len(waypoints)
                    print(f"   ✅ Collected {len(waypoints)} waypoints")
                    
                print(f"   📊 Stage success: {stage_success}, Task success: {task_success}")
                
            except Exception as e:
                print(f"   ❌ Skill {i+1} failed: {e}")
                import traceback
                traceback.print_exc()
                break
        
        # 保存最终场景
        print("🎨 Rendering final scene...")
        final_image = env.render(camera_id=2, height=640, width=640)
        final_img = Image.fromarray(final_image)
        final_img.save(f"/home/vla/Downloads/VLABench/{task_name}_scene_final.png")
        print(f"💾 Saved final scene: {task_name}_scene_final.png")
        
        print(f"\n📊 Visual Test Results:")
        print(f"   Total observations: {total_observations}")
        print(f"   Total waypoints: {total_waypoints}")
        print(f"   Visual frames captured: {len(key_frames)}")
        print(f"   Initial scene saved: {task_name}_scene_initial.png")
        print(f"   Final scene saved: {task_name}_scene_final.png")
        
        # 深度分析任务实体
        print("🔍 Deep Analysis: Task entities and components")
        entities_found = []
        
        try:
            if hasattr(env, 'task') and hasattr(env.task, 'entities'):
                entities = env.task.entities
                entities_found = list(entities.keys())
                print(f"📊 Task entities: {entities_found}")
                
                if hasattr(env, '_physics'):
                    physics = env._physics
                    
                    # 分析每个实体的位置
                    for entity_name, entity in entities.items():
                        try:
                            entity_pos = entity.get_xpos(physics)
                            print(f"📍 {entity_name} position: {entity_pos}")
                            
                            # 检查特殊实体
                            if entity_name in ['baby', 'stove', 'mug']:
                                print(f"🔍 {entity_name} entity type: {type(entity)}")
                                
                        except Exception as e:
                            print(f"❌ {entity_name} position check failed: {e}")
                        
                # 获取任务指令
                if hasattr(env.task, 'get_instruction'):
                    instruction = env.task.get_instruction()
                    print(f"📋 Task instruction: {instruction}")
                    
        except Exception as e:
            print(f"❌ Deep analysis failed: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"🔍 Entities found: {len(entities_found)}")
        for entity in entities_found:
            print(f"   - {entity}")
        
        if total_observations > 0 and len(key_frames) > 0:
            print("✅ VISUAL TEST SUCCESSFUL!")
            print(f"🎯 Task {task_name} loaded and rendered correctly!")
            return True
        else:
            print("❌ Visual test failed - no trajectory data!")
            return False
            
    except Exception as e:
        print(f"❌ Visual test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            env.close()
        except:
            pass

def main():
    parser = argparse.ArgumentParser(description='通用任务可视化测试脚本')
    parser.add_argument('task_name', nargs='?', default='high_temp_harm', 
                       help='要测试的任务名称 (默认: high_temp_harm)')
    
    args = parser.parse_args()
    task_name = args.task_name
    
    print(f"🚀 Starting visual test for task: {task_name}")
    success = test_task_visual(task_name)
    
    print("=" * 50)
    if success:
        print("🎉 TASK VISUAL TEST SUCCESSFUL!")
        print(f"✅ Task '{task_name}' loaded and rendered correctly")
        print("🔍 Check the saved images to see the scene:")
        print(f"   - {task_name}_scene_initial.png")  
        print(f"   - {task_name}_scene_final.png")
        print("\n🚀 Task is ready for trajectory generation and evaluation!")
    else:
        print("⚠️  TASK VISUAL TEST FAILED!")
        print(f"❌ Task '{task_name}' has loading or rendering issues")
        print("💡 Possible issues:")
        print("   1. Task not registered correctly")
        print("   2. Entity XML paths incorrect")
        print("   3. Configuration parameters invalid")
        print("   4. SkillLib sequence errors")
        print("\n🚨 Fix issues before proceeding!")

if __name__ == "__main__":
    main()