import YanAPI
import shutil
import os

def main():
    YanAPI.yan_api_init(YanAPI.ip)
    response=YanAPI.take_vision_photo("640x480")
    print(response)
    if(response.get('msg')=='Success'):
        photo_name=response['data']['name']
        source_path=os.path.join('/tmp/photo',photo_name)
        new_name = photo_name.replace("img", "").replace("_", "")
        target_dir='/home/pi/yanapi_ws/photos'
        target_path=os.path.join(target_dir,new_name)
        try:
            shutil.copy(source_path,target_path)
            print("successfully copied in ",target_path)
        except Exception as e:
            print("fail to copy ",e)
    else:
        print("fail to take photo", response.get('msg'))

if __name__=="__main__":
    main()
