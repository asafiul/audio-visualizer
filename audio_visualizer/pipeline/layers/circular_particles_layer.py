import cv2
import numpy as np
from ..base_layer import BaseLayer


class CircularParticle:
    def __init__(self, width, height, config, spawn_time=0):
        self.center_x = width // 2
        self.center_y = height // 2
        self.max_radius = min(width, height) // 3

        particles_config = config['pipeline']['circular_particles']

        self.angle = np.random.uniform(0, 2 * np.pi)
        orbit_min = particles_config.get('orbit_radius_min', 100)
        orbit_max = particles_config.get('orbit_radius_max', 400)
        self.radius = np.random.uniform(orbit_min * 0.5, orbit_max * 0.8)

        self.base_speed = np.random.uniform(0.01, 0.04)
        self.direction = np.random.choice([-1, 1])

        self.size = np.random.uniform(2.0, 5.0)
        self.current_size = self.size
        self.color_ratio = np.random.uniform(0, 1)

        self.life = 1.0
        decay_min = particles_config.get('decay_min', 0.998)
        decay_max = particles_config.get('decay_max', 0.9995)
        self.decay = np.random.uniform(decay_min, decay_max)

        self.width = width
        self.height = height
        self.spawn_time = spawn_time

        # Unique phase for organic variation
        self.phase = np.random.uniform(0, 2 * np.pi)
        self.radius_wobble = np.random.uniform(0.02, 0.08)
        # Smoothed size for gradual transitions
        self.smoothed_size = self.size
        # Smoothed radius for gradual transitions
        self.smoothed_radius_factor = 1.0

    def update(self, audio_level, beat):
        # Audio-reactive orbital speed (gentle)
        speed_multiplier = 0.7 + audio_level * 1.5
        self.speed = self.base_speed * speed_multiplier

        # Orbit
        self.angle += self.speed * self.direction

        # Radius responds to audio with very gentle expansion
        target_radius_factor = 1.0 + audio_level * 0.15
        wobble = np.sin(self.angle * 3 + self.phase) * self.radius_wobble

        # On beat, expand radius only slightly
        if beat:
            target_radius_factor *= 1.05
            self.life = min(1.0, self.life + 0.05)

        # Very smooth radius changes (slow attack, slow release)
        if target_radius_factor > self.smoothed_radius_factor:
            self.smoothed_radius_factor = self.smoothed_radius_factor * 0.85 + target_radius_factor * 0.15
        else:
            self.smoothed_radius_factor = self.smoothed_radius_factor * 0.95 + target_radius_factor * 0.05

        current_radius = self.radius * (self.smoothed_radius_factor + wobble)

        self.x = self.center_x + current_radius * np.cos(self.angle)
        self.y = self.center_y + current_radius * np.sin(self.angle)

        # Smooth size changes — very gradual, barely noticeable
        target_size = self.size * (0.9 + audio_level * 0.2)
        self.smoothed_size = self.smoothed_size * 0.92 + target_size * 0.08
        self.current_size = self.smoothed_size

        self.life *= self.decay

        return self.life > 0.05

    def draw(self, frame, colors):
        if self.life <= 0.05:
            return

        primary = np.array(colors.get("primary", [0, 255, 255]), dtype=np.float64)
        secondary = np.array(colors.get("secondary", [255, 0, 255]), dtype=np.float64)
        color = primary * (1 - self.color_ratio) + secondary * self.color_ratio

        # Apply life alpha
        alpha = self.life * 0.9
        color = (color * alpha).astype(np.uint8)
        color_tuple = tuple(int(c) for c in color)

        ix, iy = int(self.x), int(self.y)
        size = max(1, int(self.current_size))

        cv2.circle(frame, (ix, iy), size, color_tuple, -1)

        # Glow for larger particles
        if size > 2 and self.life > 0.3:
            glow_alpha = self.life * 0.3
            glow_color = (primary * (1 - self.color_ratio) + secondary * self.color_ratio)
            glow_color = (glow_color * glow_alpha).astype(np.uint8)
            glow_tuple = tuple(int(c) for c in glow_color)
            cv2.circle(frame, (ix, iy), size + 2, glow_tuple, 1)


class CircularParticlesLayer(BaseLayer):
    layer_type = "circular_particles"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["circular_particles"]
        self.particles = []
        self.last_spawn_time = 0
        self.prev_audio_level = 0.0

        # Pre-spawn initial particles
        count = self.layer_config.get("count", 100)
        for _ in range(count):
            self.particles.append(
                CircularParticle(self.width, self.height, self.config, 0)
            )

    def _render_direct(self, time, frame):
        window = 0.05
        audio_segment = self.audio.get_audio_segment(time, window)

        if audio_segment is not None and len(audio_segment) > 0:
            audio_level = np.sqrt(np.mean(audio_segment ** 2))
        else:
            audio_level = 0

        # Smooth audio level
        audio_level = self.prev_audio_level * 0.7 + audio_level * 0.3
        self.prev_audio_level = audio_level

        beat = self.audio.is_beat_at_time(time, threshold=0.05)

        # Spawn new particles to maintain count
        target_count = self.layer_config.get("count", 100)
        spawn_rate = self.layer_config.get("spawn_rate", 5.0)
        spawn_interval = 1.0 / max(spawn_rate, 0.1)

        if len(self.particles) < target_count and time - self.last_spawn_time > spawn_interval:
            spawn_count = min(3, target_count - len(self.particles))
            for _ in range(spawn_count):
                self.particles.append(
                    CircularParticle(self.width, self.height, self.config, time)
                )
            self.last_spawn_time = time

        # Use per-layer color overrides if available
        global_colors = self.config["visualization"]["colors"]
        colors = {
            "primary": self.layer_config.get("color_primary", global_colors.get("primary", [0, 255, 255])),
            "secondary": self.layer_config.get("color_secondary", global_colors.get("secondary", [255, 0, 255])),
        }

        alive_particles = []
        for particle in self.particles:
            if particle.update(audio_level, beat):
                particle.draw(frame, colors)
                alive_particles.append(particle)

        self.particles = alive_particles

        return frame
