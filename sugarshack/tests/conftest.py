"""Tests drive the real CLI in a subprocess, each against its own data folder.

The season of landing files is generated once and copied into each test's folder, so
every test starts from the same sources and an empty lake.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

CLI = [sys.executable, "-m", "sugarshack.cli"]


@pytest.fixture(scope="session")
def season(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("season")
    subprocess.run(CLI + ["sugarbush"], env={**os.environ, "SUGAR_DATA": str(root)},
                   check=True, capture_output=True)
    return root / "landing"


class Shack:
    def __init__(self, data: Path):
        self.data = data

    def run(self, *args, parsers=None, ok=True) -> subprocess.CompletedProcess:
        env = {**os.environ, "SUGAR_DATA": str(self.data)}
        env.pop("SUGAR_PARSERS", None)
        if parsers:
            env["SUGAR_PARSERS"] = parsers
        proc = subprocess.run(CLI + list(args), env=env, capture_output=True, text=True)
        if ok is not None:
            assert (proc.returncode == 0) == ok, proc.stdout + proc.stderr
        return proc

    def sql(self, query: str):
        with duckdb.connect(str(self.data / "lake" / "warehouse.duckdb"), read_only=True) as con:
            con.execute("set TimeZone = 'UTC'")
            return con.execute(query).fetchall()


@pytest.fixture
def make_shack(season, tmp_path_factory):
    def make() -> Shack:
        data = tmp_path_factory.mktemp("shack")
        shutil.copytree(season, data / "landing")
        return Shack(data)
    return make


@pytest.fixture
def shack(make_shack) -> Shack:
    return make_shack()
