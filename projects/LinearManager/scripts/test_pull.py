#!/usr/bin/env python3
"""
Test script for the pull functionality.
This will attempt to pull issues from Linear for testing purposes.
"""

import os
import sys

# Test if LINEAR_API_KEY is set
if not os.environ.get("LINEAR_API_KEY"):
    print("Error: LINEAR_API_KEY environment variable is not set.")
    print("Please set it before running the pull command.")
    sys.exit(1)

# Print instructions
print("To test the pull functionality, run:")
print()
print("# Pull issues from a specific team (replace ENG with your actual team key):")
print("manager pull --team-keys ENG --output ./pulled_issues --limit 5")
print()
print("# Or to pull to the default LinearManager/tasks directory:")
print("manager pull --team-keys ENG --limit 5")
print()
print("Note: Make sure you have a valid team key in Linear.")
