import pyautogui
import math
import time
import keyboard  # Install using `pip install keyboard`

def move_mouse_in_circle(radius=100, speed=0.05, duration=0.01):
    """
    Move the mouse pointer in a circular pattern.

    :param radius: The radius of the circle.
    :param speed: The angular speed of the mouse (smaller for slower rotation).
    :param duration: The time in seconds for each incremental movement.
    """
    screen_width, screen_height = pyautogui.size()
    print(f"Screen resolution: {screen_width}x{screen_height}")
    print("Press 'Esc' to stop the mouse movement.")

    # Start the mouse at the middle of the screen
    center_x, center_y = screen_width // 2, screen_height // 2

    angle = 0  # Initial angle in radians
    while not keyboard.is_pressed('esc'):
        # Calculate the x and y positions based on the angle
        x = center_x + int(radius * math.cos(angle))
        y = center_y + int(radius * math.sin(angle))
        
        # Move the mouse to the calculated position
        pyautogui.moveTo(x, y, duration=duration)
        
        # Increment the angle for the next position
        angle += speed
        
        # Wrap the angle to stay within 0 to 2π for smooth transitions
        if angle > 2 * math.pi:
            angle -= 2 * math.pi

    print("Mouse movement stopped by user.")

if __name__ == "__main__":
    print("Starting circular mouse movement...")
    try:
        move_mouse_in_circle(radius=200, speed=0.1, duration=0.01)
    except KeyboardInterrupt:
        print("Mouse movement interrupted by user.")
