"""
put_vision.py — 假设已夹取物块，视觉引导放置

用法: python put_vision.py <color>
  color: red / yellow / green

流程:
  绿色/黄色: 向左搜索目标色区域 → 对准中心 → place2 放置
  红色: 先搜索黄色区域 → 对准黄色中心 → 左转3次 → place2 放置
"""

import sys
import os
import time

import cv2

import YanAPI
import take_pic
from color_detect import get_latest_photo
from color_detect_put import (
    detect_color_blocks_put,
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


# ======================== 视觉引导放置 ========================
def do_put_vision(target_color):
    """视觉引导放置：搜索目标区域 → 对准中心 → place2 放置。"""
    print("=" * 55)
    print("  [Put Vision] 目标颜色: {}".format(target_color))
    print("  中心容差: ±{} 像素".format(CENTER_TOLERANCE))
    print("  最大迭代: {} 次".format(MAX_ITERATIONS))
    print("=" * 55)

    YanAPI.yan_api_init(YanAPI.ip)

    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion("reset")
    time.sleep(0.2)

    ever_found = False
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        print("\n--- 第 {} 次迭代 ---".format(iteration))

        # 1) 拍照
        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，稍后重试...")
            time.sleep(0.3)
            continue

        # 2) 红色特殊处理：先找黄色并走到黄色中心
        if target_color == "red":
            result_yellow = detect_color_blocks_put(photo_path, "yellow")
            save_debug_image(photo_path, result_yellow, "yellow")

            if not result_yellow["found"]:
                print("[INFO] [红] 未检测到黄色区域，继续向左搜索...")
                YanAPI.sync_play_motion(
                    name="walk", direction="left", speed="slow",
                    repeat=SEARCH_WALK_REPEAT)
                time.sleep(0.3)
                continue

            block_y = max(result_yellow["blocks"], key=lambda b: b["area"])
            offset_y = block_y["center_x"] - CENTER_X
            print("[INFO] [红] 检测到黄色 中心=({},{}) 偏移={:+d}px".format(
                block_y["center_x"], block_y["center_y"], offset_y))

            if abs(offset_y) <= CENTER_TOLERANCE:
                print("[INFO] [红] 已对准黄色中心，连续左转 3 次...")
                YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                print("[INFO] [红] 左转完成，执行 place2 放置...")
                YanAPI.sync_play_motion(name="place2")
                print("[INFO] 放置完成！")
                return True

            if offset_y < 0:
                print("[INFO] [红] 黄色偏左，向左调整 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="left", speed="slow", repeat=1)
            else:
                print("[INFO] [红] 黄色偏右，向右调整 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="right", speed="slow", repeat=1)
            time.sleep(0.3)
            continue

        # 3) 绿色/黄色：搜索目标色区域 → 对准中心 → place2
        result = detect_color_blocks_put(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        if not result["found"]:
            print("[INFO] 未检测到 {} 色区域，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="very fast",
                repeat=SEARCH_WALK_REPEAT)
            time.sleep(0.3)
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print("[INFO] 检测到 {} 色区域 中心=({}, {}) 面积={:.0f} 偏移={:+d}px".format(
            target_color, cx, cy, area, offset))

        if abs(offset) <= CENTER_TOLERANCE:
            print("[INFO] 已对准 {} 色区域中心，执行 place2 放置...".format(target_color))
            YanAPI.sync_play_motion(name="place2")
            print("[INFO] 放置完成！")
            return True

        if offset < 0:
            print("[INFO] 目标偏左，向左调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1)
        else:
            print("[INFO] 目标偏右，向右调整 1 步...")
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1)

        time.sleep(0.3)

    # 超时
    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 已达最大迭代次数 ({})，始终未找到 {} 色区域。".format(
            MAX_ITERATIONS, target_color))
    else:
        print("[ERROR] 已达最大迭代次数 ({})，无法将 {} 色区域对准中心。".format(
            MAX_ITERATIONS, target_color))
    print("=" * 55)
    return False


# ======================== 主流程 ========================
def main():
    if len(sys.argv) < 2:
        print("用法: python put_vision.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持的颜色 '{}', 支持: {}".format(
            target_color, ", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    do_put_vision(target_color)


if __name__ == "__main__":
    main()
