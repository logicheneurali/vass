import sys
import os

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import main

if __name__ == "__main__":
    main.main()
