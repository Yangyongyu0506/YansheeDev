"""
step_trial.py - WASD 控制机器人朝四个方向各走一步

用法:
  python3 step_trial.py

控制:
  - 输入 w 回车: 前进一步
  - 输入 a 回车: 左移一步
  - 输入 s 回车: 后退一步
  - 输入 d 回车: 右移一步
  - 输入 q 回车: 退出脚本
"""

import YanAPI


def main():
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] step_trial 已启动。")
    print("[INFO] 输入 w(前) a(左) s(后) d(右) 后回车执行，q 退出")

    key_to_dir = {"w": "forward", "a": "left", "s": "backward", "d": "right"}
    dir_label = {"forward": "前", "left": "左", "backward": "后", "right": "右"}

    # 按顺序记录每次操作: [("前",2), ("左",1), ("前",2), ...]
    history = []
    # 合并连续同方向: {方向: 当前连续次数}
    pending_dir = None
    pending_count = 0

    while True:
        cmd = input("[w/a/s/d | q=退出] > ").strip().lower()
        if cmd == "q":
            print("[INFO] 已退出 step_trial。")
            if history:
                print("[INFO] 操作记录: {}".format("|".join(
                    "{}{}".format(d, n) for d, n in history)))
            return

        if cmd not in key_to_dir:
            print("[WARN] 无效输入，请使用 w/a/s/d 或 q。")
            continue

        direction = key_to_dir[cmd]
        label = dir_label[direction]

        print("[INFO] 执行{}移 1 步...".format(label))
        YanAPI.sync_play_motion(name="walk", direction=direction, speed="slow", repeat=1)

        # 合并连续同方向
        if direction == pending_dir:
            pending_count += 1
            history[-1] = (label, pending_count)
        else:
            pending_dir = direction
            pending_count = 1
            history.append((label, pending_count))

        print("[INFO] 操作记录: {}".format("|".join(
            "{}{}".format(d, n) for d, n in history)))


if __name__ == "__main__":
    main()
