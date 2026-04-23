# milestone 1
import YanAPI
import sys

def main():
    YanAPI.yan_api_init(YanAPI.ip)
    if len(sys.argv) > 1:
        volume = int(sys.argv[1])
    else:
        volume = 50
    if YanAPI.set_robot_volume_value(volume)
        YanAPI.sync_play_motion(name="task01")

if __name__ == "__main__":
    main()
