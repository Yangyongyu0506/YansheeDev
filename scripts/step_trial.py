"""
step_trial.py - 手动按回车触发机器人左移一步

用法:
  python3 step_trial.py

控制:
  - 直接按回车: 左移一步
  - 输入 q 后回车: 退出脚本
"""

import YanAPI


def main():
    YanAPI.yan_api_init(YanAPI.ip)
    print("[INFO] step_trial 已启动。按回车左移一步，输入 q 退出。")
    total_steps = 0

    while True:
        cmd = input("[ENTER=左移一步 | q=退出] > ").strip().lower()
        if cmd == "q":
            print("[INFO] 已退出 step_trial。累计左移步数: {}".format(total_steps))
            return

        print("[INFO] 执行左移 1 步...")
        YanAPI.sync_play_motion(name="walk", direction="left", speed="slow", repeat=1)
        total_steps += 1
        print("[INFO] 当前累计左移步数: {}".format(total_steps))


if __name__ == "__main__":
    main()
