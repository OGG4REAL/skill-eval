from pathlib import Path

from agent_system.agent.core import Agent


class DummyRecorder:
    def __init__(self):
        self.paths = []

    def record_artifact_created(self, path: str) -> None:
        self.paths.append(path)


def test_records_files_created_by_tools_under_tracked_dirs(tmp_path):
    session_dir = tmp_path / "session"
    (session_dir / "temp").mkdir(parents=True)
    (session_dir / "output").mkdir()
    (session_dir / "uploads").mkdir()

    agent = object.__new__(Agent)
    agent.log_file = session_dir / "chat.log"

    before = agent._snapshot_tracked_artifacts()
    (session_dir / "temp" / "chart.json").write_text("{}", encoding="utf-8")
    (session_dir / "output" / "report.md").write_text("# report", encoding="utf-8")
    (session_dir / "uploads" / "source.csv").write_text("a,b\n1,2", encoding="utf-8")

    recorder = DummyRecorder()
    agent._record_new_tracked_artifacts(recorder, before)

    assert recorder.paths == ["output/report.md", "temp/chart.json"]
