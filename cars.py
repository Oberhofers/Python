import pygame
import sys
import math

# Initialize pygame
pygame.init()

# Screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
GREEN = (0, 255, 0)
RED = (255, 0, 0)

# Initialize the screen
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Pseudo-3D Car Racing")

# Clock for controlling the frame rate
clock = pygame.time.Clock()

# Road properties
road_width = 200
road_segments = 50
segment_length = 50
perspective_scale = 4
camera_height = 150

# Player car
car_width = 40
car_height = 20
car_x = 0  # Position on the road (-1 to 1)
car_speed = 0.02
max_car_speed = 0.05

# World
player_position = 0  # Progress along the road
road = []


def create_road():
    """Create the road segments with simple height changes."""
    segments = []
    for i in range(road_segments):
        curve = math.sin(i * 0.1) * 0.5  # A sine wave for road curvature
        hill = math.sin(i * 0.05) * 30  # A sine wave for road elevation
        segments.append({"curve": curve, "y": hill})
    return segments


def project(x, y, z):
    """Project a 3D point onto the 2D screen."""
    scale = perspective_scale / (z / segment_length)
    screen_x = SCREEN_WIDTH // 2 + int(x * scale)
    screen_y = SCREEN_HEIGHT // 2 - int((y - camera_height) * scale)
    return screen_x, screen_y, scale


def draw_road():
    """Draw the road using perspective scaling."""
    base_segment = int(player_position // segment_length)
    z_offset = player_position % segment_length
    max_z = road_segments * segment_length

    for i in range(300):
        segment_index = (base_segment + i) % road_segments
        segment = road[segment_index]

        z_start = i * segment_length - z_offset
        z_end = z_start + segment_length

        if z_start <= 0 or z_start > max_z:
            continue

        x1, y1, s1 = project(road_width * segment["curve"], segment["y"], z_start)
        x2, y2, s2 = project(road_width * segment["curve"], segment["y"], z_end)

        pygame.draw.polygon(screen, GRAY, [(0, y2), (SCREEN_WIDTH, y2), (x2, y1), (x1, y1)])


def draw_car():
    """Draw the player's car."""
    car_screen_x = SCREEN_WIDTH // 2 + int(car_x * road_width)
    car_screen_y = SCREEN_HEIGHT - 100
    pygame.draw.rect(
        screen, GREEN, (car_screen_x - car_width // 2, car_screen_y - car_height, car_width, car_height)
    )


# Create the road
road = create_road()

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

    # Player input
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        car_x -= car_speed
    if keys[pygame.K_RIGHT]:
        car_x += car_speed

    car_x = max(-1, min(1, car_x))  # Clamp car position on the road

    # Update world
    player_position += max_car_speed
    if player_position >= road_segments * segment_length:
        player_position -= road_segments * segment_length

    # Draw everything
    screen.fill(BLACK)
    draw_road()
    draw_car()
    pygame.display.flip()

    # Control the frame rate
    clock.tick(60)
