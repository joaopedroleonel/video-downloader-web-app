import os
import shutil
import time
from dotenv import load_dotenv 
load_dotenv()

class Clean:
    def __init__(self):
        pass
    def cleanOldFolders(self):
        while True:
            basePath = "/app/files"
            now = time.time()
            cutoff = now - (int(os.getenv('FILES_EXP_MINUTES')) * 60)
            interval = 60

            for entry in os.listdir(basePath):
                folder_path = os.path.join(basePath, entry)
                if os.path.isdir(folder_path):
                    folder_mtime = os.path.getmtime(folder_path)
                    if folder_mtime < cutoff:
                        try:
                            shutil.rmtree(folder_path)
                        except:
                            pass
            time.sleep(interval)