#!/usr/bin/env python3
"""Entry point for the Study Buddy RAG application.

Usage:
    python run.py [--host HOST] [--port PORT] [--debug]

The app will be accessible at http://localhost:5000 by default.
"""

import argparse
import multiprocessing
import sys
import webbrowser
import threading


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(
        description="Study Buddy - AI-Powered RAG Study Assistant",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable Flask debug mode",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Do not automatically open browser",
    )

    args = parser.parse_args()

    # Ensure stdout/stderr handles UTF-8 on Windows
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Import app after parsing args to avoid slow imports when showing help
    from app import app, socketio

    url = f"http://{args.host}:{args.port}"

    print("""
    +--------------------------------------------------+
    |                                                  |
    |          S T U D Y   B U D D Y                   |
    |          AI-Powered RAG Study Assistant          |
    |                                                  |
    +--------------------------------------------------+
    """)
    print(f"  * Server starting at: {url}")
    print(f"  * Data directory: ~/.studybuddy/")
    print(f"  * Debug mode: {'ON' if args.debug else 'OFF'}")
    print()
    print("  Press Ctrl+C to stop the server")
    print("  " + "-" * 50)
    print()

    # Auto-open browser after a short delay
    if not args.no_browser:
        def open_browser():
            webbrowser.open(url)
        timer = threading.Timer(1.5, open_browser)
        timer.daemon = True
        timer.start()

    try:
        socketio.run(
            app,
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=args.debug,
            log_output=True,
            allow_unsafe_werkzeug=True,
        )
    except KeyboardInterrupt:
        print("\n\n  👋 Study Buddy shutting down. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
