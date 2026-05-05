"""
fetch_put_aruco.py - 先抓取颜色方块，再基于 OpenCV ArUco 放置

用法: python3 fetch_put_aruco.py <color>
  color: red / yellow / green

流程:
  1) Fetch: 视觉搜索目标颜色并执行 grab2
  2) Put: 先左移若干步，然后搜索对应 ArUco tag
     - 未找到 tag: 左转一次继续找
     - 找到 tag: 先做中心对准，再用 tag 面积估计远近
     - 面积进入容差: 执行 place2
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
    "green": 9,
    "yellow": 9,
    "red": 9,
}

# OpenCV ArUco 字典: 5x5，id=9 在该字典内
ARUCO_DICT_NAME = "DICT_5X5_250"
# 实物边长（m），当前逻辑使用面积控制，保留该参数便于后续切换到数学距离解算
ARUCO_MARKER_SIZE_M = 0.05

PUT_INITIAL_LEFT_STEPS = 6
PUT_MAX_ITERATIONS = 50
TURN_LEFT_REPEAT = 1

# 放置阶段：先做中心对准，再按面积逼近
PUT_CENTER_TOLERANCE = 40
TARGET_TAG_AREA = 15000
TAG_AREA_TOLERANCE_RATIO = 0.20
TAG_AREA_TOLERANCE_MIN = 2500


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


def get_tag_area_bounds():
    area_tol = max(
        int(TARGET_TAG_AREA * TAG_AREA_TOLERANCE_RATIO), TAG_AREA_TOLERANCE_MIN
    )
    return area_tol, TARGET_TAG_AREA - area_tol, TARGET_TAG_AREA + area_tol


def _get_aruco_module():
    aruco = getattr(cv2, "aruco", None)
    if aruco is None:
        raise RuntimeError(
            "当前 OpenCV 不包含 aruco 模块。请安装 opencv-contrib 版本，"
            "例如: pip3 install opencv-contrib-python"
        )
    return aruco


def detect_aruco_marker(image_path, target_id):
    """用 OpenCV ArUco 检测指定 id，返回面积和中心。"""
    result = {
        "found": False,
        "marker": None,
        "image_path": image_path,
    }

    img = cv2.imread(image_path)
    if img is None:
        return result

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    aruco = _get_aruco_module()
    dictionary = aruco.getPredefinedDictionary(getattr(aruco, ARUCO_DICT_NAME))

    if hasattr(aruco, "ArucoDetector"):
        parameters = aruco.DetectorParameters()
        detector = aruco.ArucoDetector(dictionary, parameters)
        corners_list, ids, _ = detector.detectMarkers(gray)
    else:
        parameters = aruco.DetectorParameters_create()
        corners_list, ids, _ = aruco.detectMarkers(
            gray, dictionary, parameters=parameters
        )

    if ids is None or len(ids) == 0:
        return result

    ids_flat = ids.flatten().tolist()
    candidates = []
    for idx, marker_id in enumerate(ids_flat):
        if marker_id != target_id:
            continue
        pts = corners_list[idx].reshape(4, 2)
        area = float(cv2.contourArea(pts.astype("float32")))
        cx = int(pts[:, 0].mean())
        cy = int(pts[:, 1].mean())
        candidates.append(
            {
                "id": marker_id,
                "corners": pts,
                "area": area,
                "center_x": cx,
                "center_y": cy,
            }
        )

    if not candidates:
        return result

    best = max(candidates, key=lambda m: m["area"])
    result["found"] = True
    result["marker"] = best
    return result


def save_aruco_debug_image(image_path, aruco_result, target_id, lower_area, upper_area):
    os.makedirs(TEST_PHOTOS_DIR, exist_ok=True)
    img = cv2.imread(image_path)
    if img is None:
        return

    if aruco_result["found"]:
        marker = aruco_result["marker"]
        corners = marker["corners"].astype("int32").reshape((-1, 1, 2))
        cx = marker["center_x"]
        cy = marker["center_y"]
        area = int(marker["area"])
        cv2.polylines(img, [corners], True, (255, 220, 0), 2)
        cv2.circle(img, (cx, cy), 6, (0, 255, 255), -1)
        cv2.putText(
            img,
            "id={} area={}".format(target_id, area),
            (cx + 8, cy - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

    cv2.line(img, (CENTER_X, 0), (CENTER_X, IMAGE_HEIGHT), (255, 255, 255), 1)
    cv2.putText(
        img,
        "target_area={} range=[{},{}]".format(TARGET_TAG_AREA, lower_area, upper_area),
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
    )

    save_path = os.path.join(TEST_PHOTOS_DIR, os.path.basename(image_path))
    cv2.imwrite(save_path, img)
    print("[INFO] ArUco 调试图片已保存: {}".format(save_path))


def do_put_by_tag(target_color):
    """按颜色映射到 ArUco tag，并视觉引导靠近后 place2。"""
    target_id = COLOR_TO_ARUCO_ID[target_color]
    area_tol, lower_area, upper_area = get_tag_area_bounds()

    print("\n" + "=" * 60)
    print("[Phase 2] Put by OpenCV ArUco")
    print("  目标颜色: {} -> tag id {}".format(target_color, target_id))
    print(
        "  ArUco 字典: {} | marker_size={}m".format(
            ARUCO_DICT_NAME, ARUCO_MARKER_SIZE_M
        )
    )
    print("  初始左移步数: {}".format(PUT_INITIAL_LEFT_STEPS))
    print("  中心容差: ±{} px".format(PUT_CENTER_TOLERANCE))
    print(
        "  目标面积: {} (容差 ±{} => [{} ~ {}])".format(
            TARGET_TAG_AREA, area_tol, lower_area, upper_area
        )
    )
    print("=" * 60)

    print("[INFO] 抓取后先向左移动 {} 步...".format(PUT_INITIAL_LEFT_STEPS))
    YanAPI.sync_play_motion(
        name="walk", direction="left", speed="slow", repeat=PUT_INITIAL_LEFT_STEPS
    )

    try:
        _get_aruco_module()
    except RuntimeError as exc:
        print("[ERROR] {}".format(exc))
        return False

    for iteration in range(1, PUT_MAX_ITERATIONS + 1):
        print("\n--- [Put] 第 {} 次迭代 ---".format(iteration))

        photo_path = do_take_photo()
        if photo_path is None:
            print("[WARN] 拍照失败，稍后重试...")
            time.sleep(0.8)
            continue

        aruco_result = detect_aruco_marker(photo_path, target_id)
        save_aruco_debug_image(
            photo_path, aruco_result, target_id, lower_area, upper_area
        )

        if not aruco_result["found"]:
            print(
                "[INFO] 未找到目标 ArUco id={}，左转一次继续搜索...".format(target_id)
            )
            YanAPI.sync_play_motion(
                name="turn around", direction="left", repeat=TURN_LEFT_REPEAT
            )
            time.sleep(0.3)
            continue

        marker = aruco_result["marker"]
        cx = marker["center_x"]
        cy = marker["center_y"]
        area = int(marker["area"])
        offset = cx - CENTER_X
        print(
            "[INFO] 已找到 ArUco id={} center=({}, {}) area={} offset={:+d}px".format(
                target_id, cx, cy, area, offset
            )
        )

        if abs(offset) > PUT_CENTER_TOLERANCE:
            if offset < 0:
                print("[INFO] tag 偏左，向左微调 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="left", speed="slow", repeat=1
                )
            else:
                print("[INFO] tag 偏右，向右微调 1 步...")
                YanAPI.sync_play_motion(
                    name="walk", direction="right", speed="slow", repeat=1
                )
            time.sleep(0.3)
            continue

        if lower_area <= area <= upper_area:
            print("[INFO] 面积进入放置容差，执行 place2...")
            YanAPI.sync_play_motion(name="place2")
            print("[INFO] 放置完成。")
            return True

        if area < lower_area:
            print("[INFO] tag 面积偏小(area={})，向前靠近 1 步...".format(area))
            YanAPI.sync_play_motion(
                name="walk", direction="forward", speed="slow", repeat=1
            )
        else:
            print("[INFO] tag 面积偏大(area={})，向后退 1 步...".format(area))
            YanAPI.sync_play_motion(
                name="walk", direction="backward", speed="slow", repeat=1
            )

        time.sleep(0.3)

    print("[ERROR] Put 超时，未达到可放置范围。")
    return False


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
