"""Opt-in real Blender verification; uses synthetic geometry, never a client case."""
import os
from pathlib import Path
import subprocess

import pytest


def test_native_off_axis_apertures_cut_full_wall_depth(tmp_path):
    executable=os.environ.get('INTERIOR_BLENDER')
    if not executable:pytest.skip('Set INTERIOR_BLENDER for the real geometry check')
    repo=Path(__file__).parents[2]
    result=subprocess.run([executable,'--background','--factory-startup','--disable-autoexec',
        '--python-exit-code','1','--python',str(repo/'tests/fixtures/visualization/check_native_aperture.py'),
        '--',str(repo),str(tmp_path/'synthetic.glb')],capture_output=True,timeout=120)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf8',errors='replace')[-5000:]
    assert b'NATIVE APERTURES VERIFIED' in result.stdout
    assert (tmp_path/'synthetic.glb').is_file()
