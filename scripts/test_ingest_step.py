# -*- coding: utf-8 -*-
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path('docs/screenshots')
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = r'D:\D Downloads\Class_10_English_2024_Edition-www.tntextbooks.in.pdf'

def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)

with sync_playwright() as p:
    log('Launching Microsoft Edge...')
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 960})
    page = context.new_page()

    page.on('console', lambda msg: log(f'BROWSER CONSOLE [{msg.type}]: {msg.text}'))
    page.on('pageerror', lambda err: log(f'BROWSER PAGE ERROR: {err}'))

    log('Navigating to http://localhost:5173...')
    page.goto('http://localhost:5173', wait_until='networkidle')
    page.wait_for_selector('nav.tabs-header', timeout=15000)
    log('App loaded!')

    # Switch to Ingestion
    page.click('button:has-text("File Ingestion")')
    page.wait_for_timeout(1000)

    # Fill path
    input_el = page.locator('input.file-path-input')
    input_el.fill(PDF_PATH)
    log(f'Filled path: {PDF_PATH}')
    page.wait_for_timeout(500)

    # Click detect
    log('Clicking Detect...')
    page.click('button:has-text("Inspect / Detect Format")')
    page.wait_for_selector('text="Multi-Signal File Detection"', timeout=15000)
    log('Detect OK!')

    # Check button state
    ingest_btn = page.locator('button:has-text("Run Ingest & Normalize Pipeline")')
    is_disabled = ingest_btn.is_disabled()
    btn_text = ingest_btn.inner_text()
    log(f'Ingest button disabled={is_disabled}, text="{btn_text}"')

    # Click ingest
    log('Clicking Ingest button...')
    ingest_btn.click()
    page.wait_for_timeout(2000)

    # Check for error or processing
    btn_text2 = ingest_btn.inner_text()
    log(f'After click, button text="{btn_text2}"')

    for i in range(15):
        time.sleep(2)
        err_elements = page.locator('.error-banner').all_inner_texts()
        if err_elements:
            log(f'Found error banner: {err_elements}')
            break
        res_card = page.locator('.result-card').all_inner_texts()
        log(f'Tick {i+1}: Result cards count={len(res_card)}')
        for rc in res_card:
            if 'Ingestion' in rc or 'Source ID' in rc:
                log(f'Found result card: {rc[:100]}...')
                break

    page.screenshot(path=str(SCREENSHOT_DIR / 'debug_ingest.png'))
    log('Saved docs/screenshots/debug_ingest.png')
    browser.close()
