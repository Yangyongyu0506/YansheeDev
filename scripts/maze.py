"""
maze.py - 迷宫路径自动行走
路径: 前10|左24|后10|左28|前7|左20

用法:
  python3 maze.py
"""

import YanAPI

# 迷宫路径: (方向, 步数)
MAZE_PATH = [
    ("forward",  10),
    ("left",     24),
    ("backward", 10),
    ("left",     28),
    ("forward",   7),
    ("left",     20),
]

DIR_LABEL = {"forward": "前", "backward": "后", "left": "左", "right": "右"}


def main():
    YanAPI.yan_api_init(YanAPI.ip)
    total_steps = sum(n for _, n in MAZE_PATH)
    print("[INFO] 迷宫路径开始，共 {} 段 {} 步".format(len(MAZE_PATH), total_steps))

    for seg_idx, (direction, steps) in enumerate(MAZE_PATH):
        label = DIR_LABEL[direction]
        print("[INFO] --- 第 {}/{} 段: 向{}走 {} 步 ---".format(
            seg_idx + 1, len(MAZE_PATH), label, steps))
        for i in range(steps):
            print("[INFO] 向{}走第 {}/{} 步...".format(label, i + 1, steps))
            YanAPI.sync_play_motion(name="walk", direction=direction, speed="slow", repeat=1)

    print("[INFO] 迷宫路径完成！")


if __name__ == "__main__":
    main()
