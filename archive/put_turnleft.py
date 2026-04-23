"""
put.py — 机器人携带方块移动到指定位置并放置

用法: python put.py <color>
  color: red / yellow / green

流程 (fetch 成功后执行):
  1. 后退 b 步
  2. 左转 90°
  3. 根据颜色前进不同步数，转向 90°（红左转，其余右转），再前进若干步
  4. 执行 place 动作放置方块
"""

import sys
import YanAPI

# ======================== 参数配置（按硬件实际调整）========================
# 第一步：后退步数
B = 3

# 各颜色对应的步数参数与转向
STEPS = {
    "yellow": {"forward1": 20, "forward2": 0, "turn_dir": "right"},   # h1, h2
    "green":  {"forward1": 15, "forward2": 2, "turn_dir": "right"},   # g1, g2
    "red":    {"forward1": 20, "forward2": 5, "turn_dir": "left"},    # r1, r2
}

SUPPORTED_COLORS = ["red", "yellow", "green"]


def main():
    # ---------- 参数校验 ----------
    if len(sys.argv) < 2:
        print("用法: python put.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    params = STEPS[target_color]

    print("=" * 55)
    print("  目标颜色: {}".format(target_color))
    print("  后退步数 B: {}".format(B))
    print("  前进1: {} 步, 转向: {}, 前进2: {} 步".format(
        params["forward1"], params["turn_dir"], params["forward2"]))
    print("=" * 55)

    # ---------- 初始化 ----------
    YanAPI.yan_api_init(YanAPI.ip)

    # ---------- 步骤1: 后退 b 步 ----------
    print("[INFO] 后退 {} 步...".format(B))
    for i in range(B):
        YanAPI.sync_play_motion(name="walk", direction="backward", speed="slow", repeat=1)
        print("[INFO] 后退第 {}/{} 步完成".format(i + 1, B))
    print("[INFO] 后退完成")

    # ---------- 步骤2: 左转 90° ----------
    print("[INFO] 左转...")
    YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
    print("[INFO] 左转完成")

    # ---------- 步骤3: 按颜色前进 ----------
    f1 = params["forward1"]
    print("[INFO] 向前走 {} 步...".format(f1))
    for i in range(f1):
        YanAPI.sync_play_motion(name="walk", direction="forward", speed="slow", repeat=1)
        print("[INFO] 前进第 {}/{} 步完成".format(i + 1, f1))
    print("[INFO] 前进 {} 步完成".format(f1))

    # ---------- 步骤4: 转向 90°（红色左转，其余右转）----------
    turn_dir = params["turn_dir"]
    print("[INFO] {}转...".format("左" if turn_dir == "left" else "右"))
    YanAPI.sync_play_motion(name="turn around", direction=turn_dir, repeat=1)
    print("[INFO] {}转完成".format("左" if turn_dir == "left" else "右"))

    # ---------- 步骤5: 再向前走 ----------
    f2 = params["forward2"]
    print("[INFO] 向前走 {} 步...".format(f2))
    for i in range(f2):
        YanAPI.sync_play_motion(name="walk", direction="forward", speed="slow", repeat=1)
        print("[INFO] 前进第 {}/{} 步完成".format(i + 1, f2))
    print("[INFO] 前进 {} 步完成".format(f2))

    # ---------- 步骤6: 放置方块 ----------
    print("[INFO] 执行 place 放置方块...")
    YanAPI.sync_play_motion(name="place2")
    print("[INFO] 放置完成！")


if __name__ == "__main__":
    main()
