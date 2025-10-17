#!/usr/bin/env python3
"""Top-level CLI entrypoint that delegates to the package implementation.

Usage: python server.py [args]
"""

from atlantico_server.server import main


if __name__ == '__main__':
    main()
