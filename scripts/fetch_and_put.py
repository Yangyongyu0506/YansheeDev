"""
fetch-and-put.py — 识别拾取指定颜色方块，移动并放置

用法: python "fetch and put.py" <color>
  color: red / yellow / green

流程:
  Phase 1 (fetch): 向左搜索目标颜色方块，对准后拾取
  Phase 2 (put):   根据物块编号计算步数，向左走并放置
"""

import sys
import os
import time
import cv2
import YanAPI
import take_pic
from color_detect import (
    get_latest_photo,
    detect_color_blocks,
    SUPPORTED_COLORS,
    DRAW_COLORS,
    DOT_RADIUS,
    CONTOUR_THICKNESS,
)

# ======================== 路径配置 ========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")
TEST_PHOTOS_DIR = os.path.join(PROJECT_DIR, "test_photos")

# ======================== 参数配置 ========================
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CENTER_X = IMAGE_WIDTH // 2
CENTER_TOLERANCE = 40
SEARCH_WALK_REPEAT = 2
MAX_ITERATIONS = 40

# 放置公式: walk_left_steps = BASE[color] + (4 - block_index) * 3
PUT_STEP_MULTIPLIER = 7
PUT_BASE_STEPS = {
    "green":  16,
    "yellow": 30,
    "red":    30,
}


# ======================== 拍照 ========================
def do_take_photo():
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


# ======================== 保存调试可视化 ========================
def save_debug_image(image_path, result, target_color):
    if not os.path.exists(TEST_PHOTOS_DIR):
        os.makedirs(TEST_PHOTOS_DIR)

    img = cv2.imread(image_path)
    if img is None:
        return

    bgr = DRAW_COLORS.get(target_color, (255, 255, 255))
    for block in result["blocks"]:
        cx, cy = block["center_x"], block["center_y"]
        cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
        cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
        cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
        label = "{} ({},{})".format(target_color, cx, cy)
        cv2.putText(img, label, (cx + DOT_RADIUS + 5, cy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)

    fname = os.path.basename(image_path)
    save_path = os.path.join(TEST_PHOTOS_DIR, fname)
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


def _get_encounter_index(encountered_colors, target_color):
    if target_color in encountered_colors:
        return encountered_colors.index(target_color) + 1
    return -1


# ======================== Phase 1: Fetch ========================
def do_fetch(target_color):
    """搜索并拾取目标颜色方块，返回物块编号。"""
    print("=" * 55)
    print("  [Phase 1] Fetch — 目标颜色: {}".format(target_color))
    print("  中心容差: ±{} 像素".format(CENTER_TOLERANCE))
    print("  最大迭代: {} 次".format(MAX_ITERATIONS))
    print("=" * 55)

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion("reset")
    time.sleep(0.5)

    encountered_colors = []
    ever_found = False
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print("\n--- 第 {} 次迭代 ---".format(iteration))

        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，1 秒后重试...")
            time.sleep(1)
            continue

        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        # 检测全部颜色，更新首次出现记录
        for color in SUPPORTED_COLORS:
            if color not in encountered_colors:
                res_c = detect_color_blocks(photo_path, color)
                if res_c["found"]:
                    encountered_colors.append(color)
                    print("[INFO] 新发现 {} 色方块 (累计第 {} 个: {})".format(
                        color, len(encountered_colors),
                        ", ".join(encountered_colors)))

        if not result["found"]:
            print("[INFO] 未检测到 {} 色方块，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow",
                repeat=SEARCH_WALK_REPEAT,
            )
            time.sleep(0.3)
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色方块 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        if abs(offset) <= CENTER_TOLERANCE:
            block_index = _get_encounter_index(encountered_colors, target_color)
            print("[INFO] 方块已对准中心！")
            print("[INFO] 累计识别顺序: {}".format(" -> ".join(encountered_colors)))
            print("[RESULT] 物块编号: {}".format(block_index))
            print("[INFO] 开始执行 grasp 拾取...")
            YanAPI.sync_play_motion(name="grab2")
            print("[INFO] 拾取完成！")
            return block_index

        if offset < 0:
            print("[INFO] 方块偏左，向左调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1,
            )
        else:
            print("[INFO] 方块偏右，向右调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1,
            )

        time.sleep(0.3)

    # 超时
    block_index = _get_encounter_index(encountered_colors, target_color)
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色方块。".format(
            MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将方块对准中心。".format(
            MAX_ITERATIONS))
    print("[INFO] 累计识别顺序: {}".format(" -> ".join(encountered_colors)))
    print("[RESULT] 物块编号: {}".format(block_index))
    print("=" * 55)
    return block_index


# ======================== Phase 2: Put ========================
def do_put(block_index, target_color):
    """根据颜色和物块编号计算步数，向左走并放置方块。"""
    # 后退3步
    print("[INFO] 后退 3 步...")
    YanAPI.sync_play_motion(name="walk", direction="backward", speed="slow", repeat=3)
    base = PUT_BASE_STEPS[target_color]
    steps = base + (3 - block_index) * PUT_STEP_MULTIPLIER

    print("\n" + "=" * 55)
    print("  [Phase 2] Put — 颜色: {} 物块编号: {}".format(target_color, block_index))
    print("  向左走: {} + (4-{})*{} = {} 步".format(
        base, block_index, PUT_STEP_MULTIPLIER, steps))
    print("=" * 55)

    print("[INFO] 向左走 {} 步...".format(steps))
    for i in range(steps):
        YanAPI.sync_play_motion(name="walk", direction="left", speed="slow", repeat=1)
        print("[INFO] 向左第 {}/{} 步完成".format(i + 1, steps))
    print("[INFO] 向左走完成")

    if target_color == "red":
        print("[INFO] 红色方块，转180度...")
        YanAPI.sync_play_motion(name="turn around", direction="left", repeat=5)
        print("[INFO] 转180度完成")

    print("[INFO] 执行 place 放置方块...")
    YanAPI.sync_play_motion(name="place2")
    print("[INFO] 放置完成！")


# ======================== 主流程 ========================
def main():
    if len(sys.argv) < 2:
        print("用法: python \"fetch and put.py\" <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    # Phase 1: 拾取
    block_index = do_fetch(target_color)

    if block_index == -1:
        print("[ERROR] Fetch 失败，终止放置。")
        return

    # Phase 2: 放置
    do_put(block_index, target_color)


if __name__ == "__main__":
    main()
