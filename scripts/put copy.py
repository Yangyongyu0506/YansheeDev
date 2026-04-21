"""
put-copy.py — 机器人携带方块向左移动并放置

用法: python "put copy.py" <color>
  color: red / yellow / green

流程 (fetch 成功后执行):
  1. 根据颜色向左走若干步
  2. 执行 place 动作放置方块
"""

import sys
import YanAPI

# ======================== 参数配置（按硬件实际调整）========================
# 各颜色对应的向左步数
WALK_LEFT_STEPS = {
    "green":  7,
    "yellow": 12,
    "red":    15,
}

SUPPORTED_COLORS = ["red", "yellow", "green"]


def main():
    # ---------- 参数校验 ----------
    if len(sys.argv) < 2:
        print("用法: python \"put copy.py\" <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    steps = WALK_LEFT_STEPS[target_color]

    print("=" * 55)
    print("  目标颜色: {}".format(target_color))
    print("  向左走: {} 步".format(steps))
    print("=" * 55)

    # ---------- 初始化 ----------
    YanAPI.yan_api_init(YanAPI.ip)

    # ---------- 步骤1: 向左走 ----------
    print("[INFO] 向左走 {} 步...".format(steps))
    for i in range(steps):
        YanAPI.sync_play_motion(name="walk", direction="left", speed="slow", repeat=1)
        print("[INFO] 向左第 {}/{} 步完成".format(i + 1, steps))
    print("[INFO] 向左走完成")

    # ---------- 步骤2: 放置方块 ----------
    print("[INFO] 执行 place 放置方块...")
    YanAPI.sync_play_motion(name="place2")
    print("[INFO] 放置完成！")


if __name__ == "__main__":
    main()
