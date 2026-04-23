"""
put2.py - 机器人寻找地面目标色块区域并靠近后放置

用法: python put2.py <color>
  color: red / yellow / green

流程:
  1. 拍照并检测目标颜色区域
  2. 先做左右对准，再向前靠近
  3. 靠近到阈值后执行 place2 放置动作
"""

import os
import sys
import time

import cv2

import YanAPI
import take_pic
from color_detect import (
    CONTOUR_THICKNESS,
    DOT_RADIUS,
    DRAW_COLORS,
    SUPPORTED_COLORS,
    detect_color_blocks,
    get_latest_photo,
)


# ======================== 路径配置 ========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
PHOTOS_DIR = os.path.join(PROJECT_DIR, "photos")
TEST_PHOTOS_DIR = os.path.join(PROJECT_DIR, "test_photos")


# ======================== 行为参数 ========================
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CENTER_X = IMAGE_WIDTH // 2

CENTER_TOLERANCE = 40  # 与 fetch.py 保持一致
APPROACH_MIN_Y = 360  # 目标中心 y 达到该值视为足够近
APPROACH_MIN_AREA = 12000  # 或面积达到阈值也可放置

INITIAL_BACKWARD_STEPS = 3  # 开始搜索前先后退
SEARCH_TURN_REPEAT = 1  # 搜索时每次转向步数
MAX_ITERATIONS = 40  # 与 fetch.py 保持一致


def do_take_photo():
    """调用 take_pic.main() 拍照，并返回最新图片路径。"""
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


def save_debug_image(image_path, result, target_color):
    """保存检测可视化，便于离线调参。"""
    os.makedirs(TEST_PHOTOS_DIR, exist_ok=True)

    img = cv2.imread(image_path)
    if img is None:
        return

    bgr = DRAW_COLORS.get(target_color, (255, 255, 255))
    for block in result["blocks"]:
        cx = block["center_x"]
        cy = block["center_y"]
        cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
        cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
        cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
        label = "{} ({},{})".format(target_color, cx, cy)
        cv2.putText(
            img,
            label,
            (cx + DOT_RADIUS + 5, cy + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )

    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)
    cv2.line(
        img, (0, APPROACH_MIN_Y), (IMAGE_WIDTH, APPROACH_MIN_Y), (180, 180, 180), 1
    )

    save_path = os.path.join(TEST_PHOTOS_DIR, os.path.basename(image_path))
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


def search_motion():
    """未找到目标时原地小步转向扫描地面颜色区域。"""
    print("[INFO] 未找到目标，原地左转小步搜索...")
    YanAPI.sync_play_motion(
        name="turn around", direction="left", repeat=SEARCH_TURN_REPEAT
    )


def main():
    if len(sys.argv) < 2:
        print("用法: python put2.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print(
            "[ERROR] 不支持的颜色 '{}', 支持: {}".format(
                target_color, ", ".join(SUPPORTED_COLORS)
            )
        )
        sys.exit(1)

    print("=" * 55)
    print("  目标颜色: {}".format(target_color))
    print("  中心容差: ±{} px".format(CENTER_TOLERANCE))
    print("  接近阈值: y >= {} 或 area >= {}".format(APPROACH_MIN_Y, APPROACH_MIN_AREA))
    print("  初始后退步数: {}".format(INITIAL_BACKWARD_STEPS))
    print("  最大迭代: {}".format(MAX_ITERATIONS))
    print("=" * 55)

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    YanAPI.yan_api_init(YanAPI.ip)

    print("[INFO] 先后退 {} 步，准备搜索地面目标区域...".format(INITIAL_BACKWARD_STEPS))
    YanAPI.sync_play_motion(
        name="walk",
        direction="backward",
        speed="slow",
        repeat=INITIAL_BACKWARD_STEPS,
    )
    time.sleep(0.3)

    ever_found = False

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("\n--- 第 {} 次迭代 ---".format(iteration))

        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，稍后重试...")
            time.sleep(0.8)
            continue

        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        if not result["found"]:
            search_motion()
            time.sleep(0.3)
            continue

        ever_found = True
        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        cy = block["center_y"]
        area = block["area"]
        offset = cx - CENTER_X

        print(
            "[INFO] 检测到 {} 区域: center=({}, {}) area={:.0f} offset={:+d}px".format(
                target_color, cx, cy, area, offset
            )
        )

        if abs(offset) > CENTER_TOLERANCE:
            if offset < 0:
                print("[INFO] 目标偏左，向左调整 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="left", speed="slow", repeat=1
                )
            else:
                print("[INFO] 目标偏右，向右调整 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="right", speed="slow", repeat=1
                )
            time.sleep(0.3)
            continue

        if cy >= APPROACH_MIN_Y or area >= APPROACH_MIN_AREA:
            print("[INFO] 已接近目标区域，执行 place2...")
            YanAPI.sync_play_motion(name="place2")
            print("[INFO] 放置完成。")
            return

        print("[INFO] 已对准中心，继续向前靠近...")
        YanAPI.sync_play_motion(
            name="walk", direction="forward", speed="slow", repeat=1
        )
        time.sleep(0.3)

    print("\n" + "=" * 55)
    if not ever_found:
        print("[ERROR] 达到最大迭代次数，始终未找到 {} 区域。".format(target_color))
    else:
        print("[ERROR] 达到最大迭代次数，未能靠近到可放置位置。")
    print("=" * 55)


if __name__ == "__main__":
    main()
