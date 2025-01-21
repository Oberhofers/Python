import random
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.animation import FuncAnimation


def generate_maze(width, height):
    # Initialize the grid
    maze = [["#" for _ in range(width)] for _ in range(height)]

    # Directions: (dx, dy)
    directions = [(0, 2), (2, 0), (0, -2), (-2, 0)]

    # Starting point
    start_x, start_y = 1, 1
    maze[start_y][start_x] = " "

    def carve(x, y):
        random.shuffle(directions)  # Randomize the direction order
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 < nx < width - 1 and 0 < ny < height - 1 and maze[ny][nx] == "#":
                # Carve the wall
                maze[ny][nx] = " "
                maze[y + dy // 2][x + dx // 2] = " "
                carve(nx, ny)

    carve(start_x, start_y)

    # Add entrance and exit
    maze[0][1] = " "
    maze[height - 1][width - 2] = " "

    return maze


def draw_maze(ax, maze):
    for y, row in enumerate(maze):
        for x, cell in enumerate(row):
            if cell == "#":
                ax.fill([x, x + 1, x + 1, x], [y, y, y + 1, y + 1], color="black")


def move_ball(event):
    global ball_x, ball_y

    # Movement step
    dx, dy = 0, 0
    if event.key == "up":
        dy = -1
    elif event.key == "down":
        dy = 1
    elif event.key == "left":
        dx = -1
    elif event.key == "right":
        dx = 1

    new_x, new_y = ball_x + dx, ball_y + dy

    # Check for collisions
    if 0 <= new_x < len(maze[0]) and 0 <= new_y < len(maze) and maze[new_y][new_x] == " ":
        ball_x, ball_y = new_x, new_y
        ball.center = (ball_x + 0.5, ball_y + 0.5)
        fig.canvas.draw()


if __name__ == "__main__":
    width, height = 21, 21  # Maze dimensions (must be odd numbers)
    maze = generate_maze(width, height)

    # Set up the figure
    fig, ax = plt.subplots()
    ax.set_aspect("equal")
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    plt.gca().invert_yaxis()
    plt.axis("off")

    # Draw the maze
    draw_maze(ax, maze)

    # Initialize the ball
    ball_x, ball_y = 1, 1
    ball = Circle((ball_x + 0.5, ball_y + 0.5), 0.3, color="red")
    ax.add_patch(ball)

    # Connect the keyboard event
    fig.canvas.mpl_connect("key_press_event", move_ball)

    plt.show()
