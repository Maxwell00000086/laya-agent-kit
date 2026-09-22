import os
from pathlib import Path
import sys


PROJECT_DIRECTORY = Path(__file__).resolve().parent
os.environ.setdefault("LAYA_HOME", str(PROJECT_DIRECTORY / ".cache"))
sys.path.insert(0, str(PROJECT_DIRECTORY / "agent-kit/src"))

from laya_agent_kit.server import JudgeRequest, MODEL_DIRECTORIES, Question, RankRequest, check_budget, main


if __name__ == "__main__":
    main()
