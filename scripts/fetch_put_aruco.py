"""
fetch_put_aruco.py - 先抓取颜色方块，再基于 ArUco/AprilTag 放置

用法: python3 fetch_put_aruco.py <color>
  color: red / yellow / green

流程:
  1) Fetch: 视觉搜索目标颜色并执行 grab2
  2) Put: 先左移若干步，然后搜索对应 tag
     - 未找到 tag: 左转一次继续找
     - 找到 tag: 根据 tag 的距离(postion-z/position-z)前后调整
     - 距离进入容差: 执行 place2
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


# ======================== Fetch 参数 ========================
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
CENTER_X = IMAGE_WIDTH // 2
CENTER_TOLERANCE = 40
FETCH_SEARCH_LEFT_REPEAT = 2
FETCH_MAX_ITERATIONS = 40


# ======================== Put(Tag) 参数 ========================
# 颜色 -> tag id 对应关系（按现场实际修改）
COLOR_TO_ARUCO_ID = {
    "green": 10,
    "yellow": 11,
    "red": 12,
}

# start_aprilTag_recognition 需要 id + size（单位 m）
DEFAULT_TAG_SIZE_M = 0.05

PUT_INITIAL_LEFT_STEPS = 6
PUT_MAX_ITERATIONS = 50
TURN_LEFT_REPEAT = 1

# 目标距离（机器人到 tag 的 z 距离，单位 m）
TARGET_TAG_DISTANCE_M = 0.35
TAG_DISTANCE_TOLERANCE_M = 0.06


def do_take_photo():
    take_pic.main()
    return get_latest_photo(PHOTOS_DIR)


def save_debug_image(image_path, result, target_color):
    os.makedirs(TEST_PHOTOS_DIR, exist_ok=True)

    img = cv2.imread(image_path)
    if img is None:
        return

    bgr = DRAW_COLORS.get(target_color, (255, 255, 255))
    for block in result["blocks"]:
        cx, cy = block["center_x"], block["center_y"]
        cv2.drawContours(img, [block["contour"]], -1, bgr, CONTOUR_THICKNESS)
        cv2.circle(img, (cx, cy), DOT_RADIUS + 2, (255, 255, 255), 2)
        cv2.circle(img, (cx, cy), DOT_RADIUS, bgr, -1)
        label = "{} ({},{}) area={:.0f}".format(target_color, cx, cy, block["area"])
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

    save_path = os.path.join(TEST_PHOTOS_DIR, os.path.basename(image_path))
    cv2.imwrite(save_path, img)
    print("[INFO] 调试图片已保存: {}".format(save_path))


def do_fetch(target_color):
    """搜索目标颜色方块并抓取。"""
    print("\n" + "=" * 60)
    print("[Phase 1] Fetch")
    print("  目标颜色: {}".format(target_color))
    print("  中心容差: ±{} px".format(CENTER_TOLERANCE))
    print("=" * 60)

    os.makedirs(PHOTOS_DIR, exist_ok=True)

    for iteration in range(1, FETCH_MAX_ITERATIONS + 1):
        print("\n--- [Fetch] 第 {} 次迭代 ---".format(iteration))
        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，稍后重试...")
            time.sleep(1.0)
            continue

        result = detect_color_blocks(photo_path, target_color)
        save_debug_image(photo_path, result, target_color)

        if not result["found"]:
            print("[INFO] 未检测到 {}，继续向左搜索...".format(target_color))
            YanAPI.sync_play_motion(
                name="walk",
                direction="left",
                speed="slow",
                repeat=FETCH_SEARCH_LEFT_REPEAT,
            )
            time.sleep(0.3)
            continue

        block = max(result["blocks"], key=lambda b: b["area"])
        cx = block["center_x"]
        offset = cx - CENTER_X
        print(
            "[INFO] 检测到目标方块 center_x={} offset={:+d}px area={:.0f}".format(
                cx, offset, block["area"]
            )
        )

        if abs(offset) <= CENTER_TOLERANCE:
            print("[INFO] 方块已对准，执行 grab2...")
            YanAPI.sync_play_motion(name="grab2")
            print("[INFO] 抓取完成。")
            return True

        if offset < 0:
            YanAPI.sync_play_motion(
                name="walk", direction="left", speed="slow", repeat=1
            )
        else:
            YanAPI.sync_play_motion(
                name="walk", direction="right", speed="slow", repeat=1
            )
        time.sleep(0.3)

    print("[ERROR] Fetch 超时，未完成抓取。")
    return False


def _get_numeric(dct, keys):
    for key in keys:
        if key in dct:
            try:
                return float(dct[key])
            except Exception:
                return None
    return None


def _find_target_tag(status_res, target_id):
    if not isinstance(status_res, dict):
        return None
    data = status_res.get("data", {})
    tags = data.get("AprilTagStatus", [])
    for tag in tags:
        if tag.get("id") == target_id:
            return tag
    return None


def do_put_by_tag(target_color):
    """按颜色映射到 tag，并视觉引导靠近后 place2。"""
    target_id = COLOR_TO_ARUCO_ID[target_color]

    print("\n" + "=" * 60)
    print("[Phase 2] Put by ArUco/AprilTag")
    print("  目标颜色: {} -> tag id {}".format(target_color, target_id))
    print("  初始左移步数: {}".format(PUT_INITIAL_LEFT_STEPS))
    print(
        "  目标距离: {:.2f} m (容差 ±{:.2f})".format(
            TARGET_TAG_DISTANCE_M, TAG_DISTANCE_TOLERANCE_M
        )
    )
    print("=" * 60)

    print("[INFO] 抓取后先向左移动 {} 步...".format(PUT_INITIAL_LEFT_STEPS))
    YanAPI.sync_play_motion(
        name="walk", direction="left", speed="slow", repeat=PUT_INITIAL_LEFT_STEPS
    )

    start_res = YanAPI.start_aprilTag_recognition(
        tags=[{"id": target_id, "size": DEFAULT_TAG_SIZE_M}],
        enableStream=False,
    )
    if not isinstance(start_res, dict) or start_res.get("code") not in (0, 20003):
        print("[ERROR] AprilTag 识别启动失败: {}".format(start_res))
        return False

    try:
        for iteration in range(1, PUT_MAX_ITERATIONS + 1):
            print("\n--- [Put] 第 {} 次迭代 ---".format(iteration))
            status = YanAPI.get_aprilTag_recognition_status()
            tag = _find_target_tag(status, target_id)

            if tag is None:
                print("[INFO] 未找到目标 tag {}，左转一次继续搜索...".format(target_id))
                YanAPI.sync_play_motion(
                    name="turn around", direction="left", repeat=TURN_LEFT_REPEAT
                )
                time.sleep(0.3)
                continue

            distance_z = _get_numeric(tag, ["postion-z", "position-z", "z"])
            offset_x = _get_numeric(tag, ["postion-x", "position-x", "x"])

            print(
                "[INFO] 已找到目标 tag {}: x={} z={}".format(
                    target_id, offset_x, distance_z
                )
            )

            # 可用横向位移时，先微调朝向
            if offset_x is not None and abs(offset_x) > 0.08:
                if offset_x > 0:
                    print("[INFO] tag 在右侧，向右微调 1 步...")
                    YanAPI.sync_play_motion(
                        name="walk", direction="right", speed="slow", repeat=1
                    )
                else:
                    print("[INFO] tag 在左侧，向左微调 1 步...")
                    YanAPI.sync_play_motion(
                        name="walk", direction="left", speed="slow", repeat=1
                    )
                time.sleep(0.3)
                continue

            if distance_z is None:
                print("[WARN] 未拿到 z 距离，左转一次重试...")
                YanAPI.sync_play_motion(name="turn around", direction="left", repeat=1)
                time.sleep(0.3)
                continue

            delta = distance_z - TARGET_TAG_DISTANCE_M
            if abs(delta) <= TAG_DISTANCE_TOLERANCE_M:
                print("[INFO] 已到放置距离，执行 place2...")
                YanAPI.sync_play_motion(name="place2")
                print("[INFO] 放置完成。")
                return True

            if delta > 0:
                print("[INFO] 距离偏远(z={:.3f})，向前走 1 步...".format(distance_z))
                YanAPI.sync_play_motion(
                    name="walk", direction="forward", speed="slow", repeat=1
                )
            else:
                print("[INFO] 距离偏近(z={:.3f})，向后退 1 步...".format(distance_z))
                YanAPI.sync_play_motion(
                    name="walk", direction="backward", speed="slow", repeat=1
                )

            time.sleep(0.3)

        print("[ERROR] Put 超时，未到达可放置距离。")
        return False
    finally:
        stop_res = YanAPI.stop_aprilTag_recognition()
        print("[INFO] 已停止 AprilTag 识别: {}".format(stop_res))


def main():
    if len(sys.argv) < 2:
        print("用法: python3 fetch_put_aruco.py <color>")
        print("支持颜色: {}".format(", ".join(SUPPORTED_COLORS)))
        sys.exit(1)

    target_color = sys.argv[1].strip().lower()
    if target_color not in SUPPORTED_COLORS:
        print("[ERROR] 不支持颜色: {}".format(target_color))
        sys.exit(1)

    if target_color not in COLOR_TO_ARUCO_ID:
        print(
            "[ERROR] 颜色 {} 未配置对应 tag id，请先修改 COLOR_TO_ARUCO_ID".format(
                target_color
            )
        )
        sys.exit(1)

    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] 复位姿态...")
    YanAPI.sync_play_motion(name="reset")
    time.sleep(0.5)

    if not do_fetch(target_color):
        print("[ERROR] 抓取失败，终止。")
        return

    ok = do_put_by_tag(target_color)
    if not ok:
        print("[ERROR] 放置失败。")


if __name__ == "__main__":
    main()
