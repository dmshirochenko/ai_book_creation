#!/usr/bin/env python3
"""
Children's Book Generator - API Server

Run the FastAPI application.

Usage:
    python main.py
    python main.py --port 8080
    python main.py --reload  # Development mode
"""

import argparse
import uvicorn


def main():
    """Start the FastAPI server."""
    parser = argparse.ArgumentParser(
        description="Start the Children's Book Generator API server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    args = parser.parse_args()
    
    print(f"🚀 Starting Children's Book Generator API")
    print(f"   Docs: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "src.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
