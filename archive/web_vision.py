import YanAPI

def main():
    YanAPI.yan_api_init(YanAPI.ip)
    response=YanAPI.open_vision_stream('640*480')
    print(response["code"])
    print(response["msg"])

if __name__=="__main__":
    main()
