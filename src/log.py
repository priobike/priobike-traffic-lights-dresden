import time


def log(str):
    print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {str}', flush=True)