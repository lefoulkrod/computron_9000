"""
Tests for the Playwright execution tool.
"""

import logging
from tools.code.execute_playwright import execute_playwright_script, CodeExecutionError

def test_execute_playwright_script_basic():
    """
    Test running a simple Playwright test script with no extra packages.
    """
    script = '''
    const { test, expect } = require('playwright');
    test('basic test', async ({ page }) => {
        await page.goto('https://playwright.dev');
        expect(await page.title()).toContain('Playwright');
    });
    '''
    try:
        result = execute_playwright_script(script, [])
        assert result['exit_code'] == '0', f"Non-zero exit: {result}"
        assert 'Playwright' in (result['stdout'] or '') or 'Playwright' in (result['stderr'] or ''), f"Output missing: {result}"
    except CodeExecutionError as e:
        logging.error(f"Playwright execution failed: {e}")
        assert False, f"Execution error: {e}"
