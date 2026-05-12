"""
milestone_apriltag.py - 里程碑流程：沿左侧墙探测并根据 AprilTag 决策转向

流程:
1) 机器人持续左移，每移一步读取一次左侧红外传感器。
2) 当红外值小于阈值时，认为遇到墙，停止左移。
3) 检测当前视野是否有 AprilTag：
   - 有 tag -> 向右转
   - 无 tag -> 向左转
4) 转向后做平行调整：
   - 刚才向右转 -> 后退若干步
   - 刚才向左转 -> 前进若干步
5) 调整后继续重复 1)~4)，用于复杂迷宫持续行进。

用法:
  python3 milestone_apriltag.py
"""

import time

import YanAPI


# ---------- 运行参数（按现场可调） ----------
INFRARED_WALL_THRESHOLD_MM = 120
INFRARED_MEAN_WINDOW = 5
INFRARED_CONSECUTIVE_HITS = 2
MAX_LEFT_SEARCH_STEPS = 60
LEFT_STEP_REPEAT = 1

APRILTAG_ID = 4
APRILTAG_SIZE_M = 0.125
APRILTAG_WARMUP_SEC = 0.6

TURN_REPEAT = 3
# TURN_REPEAT = 2
PARALLEL_ADJUST_STEPS = 3
MAZE_MAX_CYCLES = 10


def _read_infrared_mm():
    """读取红外距离（毫米）。失败返回 None。"""
    value = YanAPI.get_sensors_infrared_value()
    if isinstance(value, int):
        return value
    print("[WARN] 红外读取失败: {}".format(value))
    return None


def move_left_until_wall(threshold_mm):
    """左移探墙，命中阈值返回 True，否则 False。"""
    print(
        "[INFO] 开始左移探墙，阈值={}mm，均值窗口={}，连续命中={}".format(
            threshold_mm,
            INFRARED_MEAN_WINDOW,
            INFRARED_CONSECUTIVE_HITS,
        )
    )

    ir_window = []
    hit_count = 0

    for step in range(1, MAX_LEFT_SEARCH_STEPS + 1):
        YanAPI.sync_play_motion(
            name="walk", direction="left", speed="very fast", repeat=LEFT_STEP_REPEAT
        )

        ir_mm = _read_infrared_mm()
        if ir_mm is None:
            continue

        ir_window.append(ir_mm)
        if len(ir_window) > INFRARED_MEAN_WINDOW:
            ir_window.pop(0)

        ir_mean = sum(ir_window) / float(len(ir_window))

        print(
            "[INFO] 左移第 {} 步后，红外原始={}mm, 均值={:.2f}mm (n={})".format(
                step, ir_mm, ir_mean, len(ir_window)
            )
        )
        if len(ir_window) >= INFRARED_MEAN_WINDOW and ir_mean < threshold_mm:
            hit_count += 1
            print(
                "[INFO] 均值命中阈值，连续命中次数={}/{}".format(
                    hit_count, INFRARED_CONSECUTIVE_HITS
                )
            )
            if hit_count >= INFRARED_CONSECUTIVE_HITS:
                print("[INFO] 红外均值连续命中阈值，判定遇墙。")
                return True
        else:
            if hit_count > 0:
                print("[INFO] 均值未命中，连续计数清零。")
            hit_count = 0

    print("[WARN] 在最大左移步数内未触发遇墙阈值。")
    return False


def detect_apriltag_in_view(tag_id, tag_size_m):
    """检测视野中是否有 AprilTag。"""
    tags = [{"id": tag_id, "size": tag_size_m}]

    start_res = YanAPI.start_aprilTag_recognition(tags=tags, enableStream=False)
    if isinstance(start_res, dict):
        print(
            "[INFO] 启动 AprilTag 识别: code={} msg={}".format(
                start_res.get("code"), start_res.get("msg", "")
            )
        )
    else:
        print("[WARN] 启动 AprilTag 识别返回异常: {}".format(start_res))

    time.sleep(APRILTAG_WARMUP_SEC)

    found = False
    try:
        status = YanAPI.get_aprilTag_recognition_status()
        if isinstance(status, dict) and status.get("code") == 0:
            tag_list = status.get("data", {}).get("AprilTagStatus", [])
            found = len(tag_list) > 0
            print("[INFO] AprilTag 检测数量: {}".format(len(tag_list)))
        else:
            print("[WARN] 获取 AprilTag 状态失败: {}".format(status))
    finally:
        stop_res = YanAPI.stop_aprilTag_recognition()
        if isinstance(stop_res, dict):
            print(
                "[INFO] 关闭 AprilTag 识别: code={} msg={}".format(
                    stop_res.get("code"), stop_res.get("msg", "")
                )
            )

    return found


def turn_and_parallel_adjust(turn_direction):
    """转向后做平行补偿。"""
    print("[INFO] 执行转向: {}".format(turn_direction))
    YanAPI.sync_play_motion(
        name="turn around", direction=turn_direction, repeat=TURN_REPEAT
    )

    if turn_direction == "right":
        adjust_direction = "backward"
    else:
        adjust_direction = "forward"

    print("[INFO] 平行调整: {} {} 步".format(adjust_direction, PARALLEL_ADJUST_STEPS))
    YanAPI.sync_play_motion(
        name="walk",
        direction=adjust_direction,
        speed="very fast",
        repeat=PARALLEL_ADJUST_STEPS,
    )


def main():
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] 初始化完成，复位姿态...")
    YanAPI.sync_play_motion(name="reset")

    cycle = 0
    print(
        "[INFO] 进入迷宫持续模式。{}".format(
            "循环上限={} 次".format(MAZE_MAX_CYCLES)
            if MAZE_MAX_CYCLES > 0
            else "循环上限=无限(按 Ctrl+C 停止)"
        )
    )

    while True:
        cycle += 1
        print("\n[INFO] ===== 迷宫循环 #{} =====".format(cycle))

        hit_wall = move_left_until_wall(INFRARED_WALL_THRESHOLD_MM)
        if not hit_wall:
            print("[WARN] 本轮未遇墙，继续左移进入下一轮搜索。")
        else:
            tag_found = detect_apriltag_in_view(APRILTAG_ID, APRILTAG_SIZE_M)
            if tag_found:
                print("[INFO] 视野中有 AprilTag，按规则向右转。")
                turn_and_parallel_adjust("right")
            else:
                print("[INFO] 视野中无 AprilTag，按规则向左转。")
                turn_and_parallel_adjust("left")

        if MAZE_MAX_CYCLES > 0 and cycle >= MAZE_MAX_CYCLES:
            print("[INFO] 已达到循环上限，流程结束。")
            return


if __name__ == "__main__":
    main()
