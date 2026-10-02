import random
import time


def fire_cannon():
    print("대포 발사 준비...")
    time.sleep(0.5)
    for s in ("3", "2", "1"):
        print(s)
        time.sleep(0.5)
    print("🔥 쾅! 💥")
    time.sleep(0.3)
    number = random.randint(1, 60)
    print(f"포탄이 떨어진 곳: {number}")
    return number


if __name__ == "__main__":
    fire_cannon()
