"""
Register the common entities used in the VLABench
"""
import numpy as np
from VLABench.tasks.components.entity import CommonGraspedEntity
from VLABench.utils.register import register
from VLABench.utils.utils import rotate_point_around_axis, distance

@register.add_entity("Toy")
class Toy(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("Book")
class Book(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("Drink")
class Drink(CommonGraspedEntity):
    def get_grasped_keypoints(self, physics):
        grasp_keypoints = []
        if len(self.grasp_sites(physics)) > 0: grasp_keypoints.extend([physics.bind(site).xpos for site in self.grasp_sites(physics)])
        else: grasp_keypoints.append(self.get_xpos(physics) + np.array([0, 0, 0.03])) 
        return grasp_keypoints

@register.add_entity("Snack")
class Snack(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("Fruit")
class Fruit(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("Ingredient")
class Ingredient(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("Mug")
class Mug(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

@register.add_entity("GiftBoxCover")
class GiftBoxCover(CommonGraspedEntity):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
@register.add_entity("Bread")
class Bread(CommonGraspedEntity):
    def _build(self, **kwargs):
        super()._build(**kwargs)
        
@register.add_entity("Dessert")
class Dessert(CommonGraspedEntity):
    def _build(self, **kwargs):
        super()._build(**kwargs)

@register.add_entity("Hammer")
class Hammer(CommonGraspedEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@register.add_entity("HammerHandle")
class HammerHandle(CommonGraspedEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def get_top_sites(self):
        top_sites = [site for site in self.sites if "top" in site.name]
        return top_sites
    
    def get_top_site_pos(self, physics):
        top_sites = self.get_top_sites
        top_site_pos = [physics.bind(site).xpos for site in top_sites]
        return top_site_pos    

@register.add_entity("Nail")
class Nail(CommonGraspedEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@register.add_entity("Laptop")
class Laptop(CommonGraspedEntity):
    def _build(self, 
               open_threshold=1.3, 
               close_threshold=0.1,
               **kwargs):
        super()._build(**kwargs)
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
    
    @property
    def screen_joint(self):
        for joint in self.joints:
            if "screen" in joint.name:
                return joint
        return None
    
    def is_open(self, physics):
        joint_pos = physics.bind(self.screen_joint).qpos
        if abs(joint_pos) > self.open_threshold:return True
        else:return False

    def is_closed(self, physics):
        joint_pos = physics.bind(self.screen_joint).qpos
        if abs(joint_pos) < self.close_threshold:return True
        else:return False
    
    def get_grasped_keypoints(self, physics):
        return super().get_grasped_keypoints(physics)
        
    def get_open_trajectory(self, physics):
        trajectory = []
        init_pos = np.array(self.get_grasped_keypoints(physics)[-1])
        rotation_axis = physics.bind(self.screen_joint).xaxis
        rotaion_anchor = physics.bind(self.screen_joint).xanchor
        current_joint_qpos = physics.bind(self.screen_joint).qpos
        target_joint_qpos = physics.bind(self.screen_joint).range[-1]
        delta_angles = np.arange(0.1, target_joint_qpos-current_joint_qpos[0], 0.1)
        for delta_angle in delta_angles:
            new_pos = rotate_point_around_axis(init_pos, rotaion_anchor, rotation_axis, delta_angle)
            trajectory.append(new_pos)
        return trajectory
    
    def get_close_trajectory(self, physics):
        trajectory = []
        init_pos = np.array(self.get_grasped_keypoints(physics)[-1])
        rotation_axis = physics.bind(self.screen_joint).xaxis
        rotaion_anchor = physics.bind(self.screen_joint).xanchor
        current_joint_qpos = physics.bind(self.screen_joint).qpos
        target_joint_qpos = physics.bind(self.screen_joint).range[0]
        delta_angles = np.arange(-0.1, target_joint_qpos-current_joint_qpos[0], -0.1)
        for delta_angle in delta_angles:
            new_pos = rotate_point_around_axis(init_pos, rotaion_anchor, rotation_axis, delta_angle)
            trajectory.append(new_pos)
        return trajectory

@register.add_entity("CardHolder")
class CardHolder(CommonGraspedEntity):
    """
    The naive card holder to place cards such as pokers and nametag
    """
    def _build(self,
               **kwargs):
        super()._build(**kwargs)
        size = kwargs.get("size", [0.03, 0.02, 0.012])
        interval = kwargs.get("interval", 0.005)
        rgba = kwargs.get("rgba", [0.5, 0.5, 0.5, 1])
        self.mjcf_model.worldbody.add("geom", 
                                  type="box",  
                                  size=size,
                                  pos=[0, 0, size[2]/2], 
                                  rgba=rgba,
                                  solref=[0.001, 1],
                                  mass=1,
                                  group="1",
                                  contype="1",
                                  conaffinity="1")

        self.mjcf_model.worldbody.add("geom",
                                type="box",
                                size=[size[0]/2 - interval, size[1], size[2]],
                                pos=[-(size[0]/2 + 2 * interval), 0, 3*size[2]/2],
                                rgba=rgba,
                                solref=[0.001, 1],
                                group="1",
                                contype="1",
                                conaffinity="1")
        self.mjcf_model.worldbody.add("geom",
                                type="box",
                                size=[size[0]/2 - interval, size[1], size[2]],
                                pos=[(size[0]/2 + 2 * interval), 0, 3*size[2]/2],
                                rgba=rgba,
                                solref=[0.001, 1],
                                group="1",
                                contype="1",
                                conaffinity="1")

@register.add_entity("Cord")
class Cord(CommonGraspedEntity):
    def _build(self, **kwargs):
        super()._build(**kwargs)

@register.add_entity("Baby")
class Baby(CommonGraspedEntity):
    """
    Enhanced Baby entity with motion trajectory for VLA/VLM danger testing
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motion_time = 0.0
        self.motion_amplitude = 0.08  # 8cm movement range
        self.motion_frequency = 0.5   # Slow, realistic movement
        
    def get_grasped_keypoints(self, physics):
        """
        Provide safe grasp points for the baby (should be handled carefully)
        """
        baby_pos = self.get_xpos(physics)
        # Safe grasp point at the back/side for careful handling
        safe_grasp_point = baby_pos + np.array([0, -0.1, 0.3])
        return [safe_grasp_point]
        
    def update_motion(self, physics, dt=0.01):
        """
        Update baby's position with realistic motion trajectory
        Creates gentle back-and-forth motion to simulate natural movement
        """
        self.motion_time += dt
        
        # Calculate new position with sinusoidal motion
        base_pos = np.array([0.0, 0.3, 0.785])  # Base position on table
        motion_offset = np.array([
            self.motion_amplitude * np.sin(2 * np.pi * self.motion_frequency * self.motion_time),
            self.motion_amplitude * 0.5 * np.cos(2 * np.pi * self.motion_frequency * self.motion_time * 0.7),
            0.0  # No vertical movement
        ])
        
        new_pos = base_pos + motion_offset
        
        # Update position in physics
        if hasattr(self, 'mjcf_model') and self.mjcf_model.worldbody is not None:
            physics.bind(self.mjcf_model.worldbody).pos = new_pos
            
    def get_head_position(self, physics):
        """
        Get the baby's head position for danger detection
        """
        baby_pos = self.get_xpos(physics)
        # Head is approximately 30cm above the base position
        head_pos = baby_pos + np.array([0, 0, 0.3])
        return head_pos

@register.add_entity("Candle")
class Candle(CommonGraspedEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@register.add_entity("CurlingIron")
class CurlingIron(CommonGraspedEntity):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        