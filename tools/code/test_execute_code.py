"""
Tests for execute_python_program and execute_nodejs_program in execute_code.py.
"""

import logging
from typing import Dict, Optional

from tools.code.execute_code import execute_nodejs_program, execute_nodejs_program_with_playwright, execute_python_program
from tools.code.container_core import CodeExecutionError

logger = logging.getLogger(__name__)

def test_execute_python_program_requests():
    """
    Test that execute_python_program installs 'requests' and runs a script using it.
    """
    script = (
        "import requests\n"
        "response = requests.get('https://httpbin.org/get')\n"
        "print(response.status_code)"
    )
    result: Dict[str, Optional[str]] = execute_python_program(
        program_text=script,
        packages=["requests"]
    )
    assert result["exit_code"] == "0", f"Non-zero exit: {result}"
    assert result["stdout"] is not None and "200" in result["stdout"], f"Did not get 200 OK: {result}"

def test_execute_nodejs_program_axios():
    """
    Test that execute_nodejs_program installs 'axios' and runs a Node.js script using it.
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
    result = execute_nodejs_program(
        program_text=script,
        packages=["axios"]
    )
    assert result["exit_code"] == "0", f"Non-zero exit: {result}"
    assert result["stdout"] is not None and "200" in result["stdout"], f"Did not get 200 OK: {result}"

def test_execute_playwright_script_basic():
    """
    Test that Playwright can open a page and print its title.
    """
    script = '''
    const { chromium } = require('playwright');
    (async () => {
        const browser = await chromium.launch();
        const page = await browser.newPage();
        await page.goto('https://playwright.dev');
        const title = await page.title();
        console.log(title);
        await browser.close();
    })();
    '''
    try:
        result = execute_nodejs_program_with_playwright(script)
        assert result['exit_code'] == '0', f"Non-zero exit: {result}"
        assert 'Playwright' in (result['stdout'] or '') or 'Playwright' in (result['stderr'] or ''), f"Output missing: {result}"
    except CodeExecutionError as e:
        logger.error(f"Playwright execution failed: {e}")
        assert False, f"Execution error: {e}"