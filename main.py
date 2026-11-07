import sys

from ums import cli, seed

if __name__ == "__main__":
    if "--init" in sys.argv:
        seed.main()
    else:
        cli.main()
