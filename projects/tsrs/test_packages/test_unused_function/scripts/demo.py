#!/usr/bin/env python3
"""
Demo script that uses functions from package_one.
"""

from package_one import add_one_and_one, HelloWorld


def main() -> None:
    """Run the demo."""
    # Use the add_one_and_one function
    result = add_one_and_one()
    print(f"Result of add_one_and_one(): {result}")

    # Use the HelloWorld class
    greeter = HelloWorld()
    greeter.greet()


if __name__ == "__main__":
    main()
