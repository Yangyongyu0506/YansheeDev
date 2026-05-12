import YanAPI

def main():
        YanAPI.yan_api_init(YanAPI.ip)
        response=YanAPI.get_robot_battery_info()
        print(response)
if __name__ == "__main__":
         main()
