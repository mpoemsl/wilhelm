import os

from wilhelm import get_imgs, make_animation


def main():
    get_imgs()

    for n in range(5):
        os.remove("imgs/11.mp4")
        make_animation(n_interpolations=n)
        print(f"Succeeded with {n} interpolations")


if __name__ == "__main__":
    main()
