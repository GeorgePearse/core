"""Consumer demonstrating dynamic import limits."""


def main() -> str:
    module = __import__("used_pkg")
    return module.greet()


if __name__ == "__main__":
    print(main())
