import pyautogui
import math
import time
import keyboard  # Install using `pip install keyboard`

def move_mouse_sinus_wave(amplitude=100, frequency=0.01, step=2, duration=0.01):
    """
    Move the mouse pointer in a smooth sinusoidal wave pattern.

    :param amplitude: The height of the sine wave.
    :param frequency: The frequency of the sine wave.
    :param step: The increment of the x-coordinate per iteration (smaller for smoother motion).
    :param duration: The time in seconds for each incremental movement (smaller for smoother motion).
    """
    screen_width, screen_height = pyautogui.size()
    print(f"Screen resolution: {screen_width}x{screen_height}")
    print("Press 'Esc' to stop the mouse movement.")

    # Start the mouse at the middle of the screen
    center_y = screen_height // 2

    x = 0  # Start position on the x-axis
    while not keyboard.is_pressed('esc'):
        # Calculate the y position using the sine function
        y = center_y + int(amplitude * math.sin(frequency * x))
        # Move the mouse to the calculated position
        pyautogui.moveTo(x % screen_width, y, duration=duration)
        x += step
        time.sleep(duration)

    print("Mouse movement stopped by user.")

if __name__ == "__main__":
    print("Starting smooth sinusoidal mouse movement...")
    try:
        move_mouse_sinus_wave(amplitude=300, frequency=0.02, step=1, duration=0.005)
    except KeyboardInterrupt:
        print("Mouse movement interrupted by user.")
