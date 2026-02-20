import cv2
import numpy as np
from ..base_layer import BaseLayer


class CircularParticle:
    def __init__(self, width, height, config, spawn_time=0):
        self.center_x = width // 2
        self.center_y = height // 2
        self.max_radius = min(width, height) // 3
        
        self.angle = np.random.uniform(0, 2 * np.pi)
        self.radius = np.random.uniform(self.max_radius * 0.2, self.max_radius * 0.8)
        
        self.base_speed = np.random.uniform(0.05, 0.1)
        self.direction = np.random.choice([-1, 1])
        
        self.size = np.random.uniform(2.0, 6.0)
        self.current_size = self.size
        self.color_ratio = np.random.uniform(0, 1)
        
        self.life = 1.0
        self.decay = np.random.uniform(0.97, 0.99)
        
        self.width = width
        self.height = height
        self.spawn_time = spawn_time

    def update(self, audio_level):
        speed_multiplier = 0.5 + audio_level * 2.5
        self.speed = self.base_speed * speed_multiplier
        
        self.angle += self.speed * self.direction
        
        radius_multiplier = 1.0 + audio_level * 0.3
        current_radius = self.radius * radius_multiplier
        
        self.x = int(self.center_x + current_radius * np.cos(self.angle))
        self.y = int(self.center_y + current_radius * np.sin(self.angle))
        
        self.current_size = self.size * (1.0 + audio_level * 0.5)
        
        self.life *= self.decay
        
        return self.life > 0.1

    def draw(self, frame, colors):
        if self.life <= 0:
            return
            
        primary = np.array(colors.get("primary", [0, 255, 255]))
        secondary = np.array(colors.get("secondary", [255, 0, 255]))
        color = primary * (1 - self.color_ratio) + secondary * self.color_ratio
        
        # Apply life alpha
        color = color * self.life
        
        cv2.circle(frame, (int(self.x), int(self.y)), int(self.current_size),
                  color.astype(int).tolist(), -1)


class CircularParticlesLayer(BaseLayer):
    layer_type = "circular_particles"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["circular_particles"]
        self.particles = []
        self.last_spawn_time = 0
        
    def _render_direct(self, time, frame):
        window = 0.1
        audio_segment = self.audio.get_audio_segment(time, window)
        
        if audio_segment is not None and len(audio_segment) > 0:
            audio_level = np.mean(np.abs(audio_segment))
        else:
            audio_level = 0
        
        spawn_rate = self.layer_config.get("spawn_rate", 5)
        if time - self.last_spawn_time > 1.0 / spawn_rate:
            for _ in range(np.random.randint(1, 4)):
                self.particles.append(CircularParticle(self.width, self.height, 
                                                     self.config, time))
            self.last_spawn_time = time
        
        colors = self.config["visualization"]["colors"]
        
        alive_particles = []
        for particle in self.particles:
            if particle.update(audio_level):
                particle.draw(frame, colors)
                alive_particles.append(particle)
        
        self.particles = alive_particles
        
        return frame