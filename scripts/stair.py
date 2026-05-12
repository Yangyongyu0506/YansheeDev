# milestone 1
import YanAPI
import sys

def main():
    YanAPI.yan_api_init(YanAPI.ip)
    YanAPI.sync_play_motion(name="stair")

if __name__ == "__main__":
    main()
