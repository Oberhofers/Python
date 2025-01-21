import pyautogui
import time

def move_mouse(x, y, duration=1):
    """
    Move the mouse pointer to a specific position.
    
    :param x: The x-coordinate of the target position.
    :param y: The y-coordinate of the target position.
    :param duration: Time in seconds for the mouse to move to the target position.
    """
    pyautogui.moveTo(x, y, duration=duration)

def move_mouse_in_pattern():
    """
    Move the mouse pointer in a simple pattern (e.g., square).
    """
    screen_width, screen_height = pyautogui.size()
    print(f"Screen resolution: {screen_width}x{screen_height}")

    # Define the corners of the pattern
    positions = [
        (100, 100),  # Top-left
        (500, 100),  # Top-right
        (500, 500),  # Bottom-right
        (100, 500)   # Bottom-left
    ]

    # Loop through the positions
    for pos in positions:
        print(f"Moving to position: {pos}")
        move_mouse(pos[0], pos[1], duration=1)
        time.sleep(0.5)

if __name__ == "__main__":
    print("Starting mouse movement...")
    try:
        move_mouse_in_pattern()
        print("Mouse movement completed.")
    except KeyboardInterrupt:
        print("Mouse movement interrupted by user.")