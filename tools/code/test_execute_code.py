"""
Tests for execute_program_with_packages in execute_code.py.
"""

import logging
from typing import Dict, Optional

import pytest

from tools.code.execute_code import execute_program_with_packages, CodeExecutionError

logger = logging.getLogger(__name__)

def test_execute_program_with_packages_python_requests():
    """
    Test that execute_program_with_packages installs 'requests' and runs a script using it.
    """
    script = (
        "import requests\n"
        "response = requests.get('https://httpbin.org/get')\n"
        "print(response.status_code)"
    )
    result: Dict[str, Optional[str]] = execute_program_with_packages(
        program_text=script,
        language="python",
        packages=["requests"]
    )
    assert result["exit_code"] == "0", f"Non-zero exit: {result}"
    assert result["stdout"] is not None and "200" in result["stdout"], f"Did not get 200 OK: {result}"

def test_execute_program_with_packages_node_axios():
    """
    Test that execute_program_with_packages installs 'axios' and runs a Node.js script using it.
    """
    script = (
        "const axios = require('axios');\n"
        "axios.get('https://httpbin.org/get').then(response => {\n"
        "    console.log(response.status);\n"
        "}).catch(error => {\n"
        "    console.error('Error:', error);\n"
        "    process.exit(1);\n"
        "});"
    )
    result = execute_program_with_packages(
        program_text=script,
        language="node",
        packages=["axios"]
    )
    assert result["exit_code"] == "0", f"Non-zero exit: {result}"
    assert result["stdout"] is not None and "200" in result["stdout"], f"Did not get 200 OK: {result}"
