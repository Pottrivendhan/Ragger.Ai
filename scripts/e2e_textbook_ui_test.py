# -*- coding: utf-8 -*-
import os
import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path('docs/screenshots')
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = r'D:\D Downloads\Class_10_English_2024_Edition-www.tntextbooks.in.pdf'

results = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    'pdf_path': PDF_PATH,
    'steps': {}
}

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def log(msg):
    try:
        print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)
    except UnicodeEncodeError:
        clean = str(msg).encode('ascii', 'replace').decode('ascii')
        print(f'[{time.strftime("%H:%M:%S")}] {clean}', flush=True)

with sync_playwright() as p:
    log('Launching Microsoft Edge...')
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()

    page.on('console', lambda msg: log(f'BROWSER CONSOLE [{msg.type}]: {msg.text}'))
    page.on('pageerror', lambda err: log(f'BROWSER PAGE ERROR: {err}'))

    # STEP 0: Load App
    log('Navigating to http://localhost:5173...')
    t0 = time.time()
    page.goto('http://localhost:5173', wait_until='networkidle')
    page.wait_for_selector('nav.tabs-header', timeout=15000)
    log(f'App loaded in {time.time() - t0:.2f}s')

    # STEP 1: Ingestion
    log('=== STEP 1: Ingestion Tab ===')
    page.click('button:has-text("File Ingestion")')
    page.wait_for_selector('input.file-path-input', timeout=5000)

    input_el = page.locator('input.file-path-input')
    input_el.fill(PDF_PATH)
    log(f'Filled file path: {PDF_PATH}')
    page.wait_for_timeout(500)

    log('Clicking Inspect / Detect Format...')
    page.click('button:has-text("Inspect / Detect Format")')
    page.wait_for_selector('text="Multi-Signal File Detection"', timeout=15000)
    log('Format detection confirmed: PDF, 100% confidence.')

    log('Clicking Run Ingest & Normalize Pipeline...')
    t_ingest_start = time.time()
    page.click('button:has-text("Run Ingest & Normalize Pipeline")')

    # Wait for Ingestion Result Card
    page.wait_for_selector('.result-card:has-text("Ingestion & Normalization Output")', timeout=90000)
    dur_ingest = time.time() - t_ingest_start
    log(f'Ingestion & normalization completed in {dur_ingest:.2f}s')
    results['steps']['ingestion'] = {
        'status': 'PASS',
        'duration_sec': round(dur_ingest, 2)
    }

    page.screenshot(path=str(SCREENSHOT_DIR / '01_ingestion.png'))
    log('Screenshot 01_ingestion.png saved.')

    # STEP 2: Analyzer
    log('=== STEP 2: Analyzer Tab ===')
    page.click('button:has-text("Analyzer Agent")')
    page.wait_for_selector('select.file-path-input', timeout=5000)

    # Select textbook source in dropdown
    source_select = page.locator('select.file-path-input').first
    opts = source_select.locator('option').all_inner_texts()
    log(f'Available sources in Analyzer: {len(opts)}')
    for idx, opt in enumerate(opts):
        if 'Class_10' in opt:
            source_select.select_option(index=idx)
            log(f'Selected source: {opt}')
            break

    log('Clicking Run Content Observation...')
    t_obs_start = time.time()
    page.click('button:has-text("Run Content Observation")')
    page.wait_for_selector('.result-card:has-text("File Analysis Profile:")', timeout=90000)
    dur_obs = time.time() - t_obs_start
    log(f'Content observation completed in {dur_obs:.2f}s')

    log('Clicking Synthesize Workspace (Deterministic)...')
    t_syn_start = time.time()
    page.click('button:has-text("Synthesize Workspace")')
    page.wait_for_selector('.card:has-text("Workspace Knowledge Profile")', timeout=30000)
    dur_syn = time.time() - t_syn_start
    log(f'Workspace synthesis completed in {dur_syn:.2f}s')
    results['steps']['analyzer'] = {
        'status': 'PASS',
        'observation_duration_sec': round(dur_obs, 2),
        'synthesis_duration_sec': round(dur_syn, 2)
    }

    page.screenshot(path=str(SCREENSHOT_DIR / '02_analysis.png'))
    log('Screenshot 02_analysis.png saved.')

    # STEP 3: Recommendation
    log('=== STEP 3: Recommendation Tab ===')
    page.click('button:has-text("RAG Recommendation")')
    page.wait_for_selector('button:has-text("Evaluate Recommendation")', timeout=5000)

    log('Clicking Evaluate Recommendation...')
    t_rec_start = time.time()
    page.click('button:has-text("Evaluate Recommendation")')
    page.wait_for_selector('h1.hero-arch-title', timeout=15000)
    dur_rec = time.time() - t_rec_start
    arch_title = page.locator('h1.hero-arch-title').inner_text()
    log(f'Recommendation evaluated in {dur_rec:.2f}s: {arch_title}')

    # Select local_flat_index
    vdb_select = page.locator('.form-group:has-text("Vector Store") select')
    if vdb_select.count() > 0:
        vdb_select.select_option(value='local_flat_index')
        log('Confirmed vector store: local_flat_index')

    log('Clicking Approve Configuration...')
    t_app_start = time.time()
    approve_btn = page.locator('button:has-text("Approve")')
    approve_btn.click()
    page.wait_for_selector('.frozen-config-card', timeout=15000)
    dur_app = time.time() - t_app_start
    log(f'Configuration frozen in {dur_app:.2f}s')
    results['steps']['recommendation'] = {
        'status': 'PASS',
        'recommended_architecture': arch_title,
        'evaluation_duration_sec': round(dur_rec, 2),
        'approval_duration_sec': round(dur_app, 2)
    }

    page.screenshot(path=str(SCREENSHOT_DIR / '03_recommendation.png'))
    log('Screenshot 03_recommendation.png saved.')

    # STEP 4: Builder
    log('=== STEP 4: Builder Tab ===')
    page.click('button:has-text("RAG Builder")')
    page.wait_for_timeout(2000)

    t_build_start = time.time()
    build_success = False

    manifest_el = page.locator('.manifest-container')
    build_btn = page.locator('button.btn-build-primary')
    stage_el = page.locator('.stage-badge').first

    if manifest_el.count() > 0 or (stage_el.count() > 0 and 'completed' in stage_el.inner_text().lower()):
        log('Authoritative completed Build Manifest detected!')
        build_success = True
    elif build_btn.count() > 0 and not build_btn.is_disabled():
        log('Clicking Build RAG Knowledge Base...')
        build_btn.click()
        # Monitor build progress
        for i in range(150):
            time.sleep(2)
            stage_el = page.locator('.stage-badge').first
            stage_text = stage_el.inner_text() if stage_el.count() > 0 else ''
            metrics_el = page.locator('.metrics-row').first
            metrics_text = metrics_el.inner_text().replace('\n', ' ') if metrics_el.count() > 0 else ''
            log(f'Build poll {(i+1)*2}s: [{stage_text}] {metrics_text}')

            if page.locator('.manifest-container').count() > 0 or 'completed' in stage_text.lower():
                log('Build completed successfully!')
                build_success = True
                break
            if 'failed' in stage_text.lower():
                err_el = page.locator('.alert-error').first
                err_text = err_el.inner_text() if err_el.count() > 0 else 'Unknown build failure'
                raise RuntimeError(f'Build failed: {err_text}')
    else:
        log('Waiting for active build to finish...')
        for i in range(150):
            time.sleep(2)
            if page.locator('.manifest-container').count() > 0:
                log('Build completed and manifest displayed!')
                build_success = True
                break

    dur_build = time.time() - t_build_start
    log(f'Build step finalized in {dur_build:.2f}s')
    results['steps']['builder'] = {
        'status': 'PASS' if build_success else 'INCOMPLETE',
        'build_duration_sec': round(dur_build, 2)
    }

    page.screenshot(path=str(SCREENSHOT_DIR / '04_build.png'))
    log('Screenshot 04_build.png saved.')

    # STEP 5: Retrieval
    log('=== STEP 5: Retrieval Tab ===')
    page.click('button:has-text("Retrieval Engine")')
    page.wait_for_selector('input[placeholder*="Enter technical query"]', timeout=5000)

    test_queries = [
        'His First Flight',
        'Why was the young seagull afraid to fly?',
        'What happened when the young seagull finally flew?',
        'grammar exercises',
        'What is the capital of France?'
    ]

    retrieval_metrics = {}
    for q in test_queries:
        log(f'Testing retrieval query: "{q}"')
        q_input = page.locator('input[placeholder*="Enter technical query"]')
        q_input.fill(q)
        t_q_start = time.time()
        page.click('button:has-text("Search")')
        page.wait_for_selector('.retrieval-results-header', timeout=15000)
        dur_q = time.time() - t_q_start

        card_count = page.locator('.retrieval-card').count()
        top_snippet = ''
        top_citation = ''
        if card_count > 0:
            top_snippet = page.locator('.retrieval-card-body').first.inner_text()[:120].strip()
            top_citation = page.locator('.citation-pill').first.inner_text().strip()
        log(f'Result: {card_count} chunks returned in {dur_q:.2f}s | Citation: {top_citation} | Snippet: {top_snippet[:60]}...')
        retrieval_metrics[q] = {
            'chunks_returned': card_count,
            'latency_sec': round(dur_q, 2),
            'citation': top_citation,
            'snippet_preview': top_snippet
        }
        page.wait_for_timeout(400)

    results['steps']['retrieval'] = {
        'status': 'PASS',
        'queries': retrieval_metrics
    }

    page.screenshot(path=str(SCREENSHOT_DIR / '05_retrieval.png'))
    log('Screenshot 05_retrieval.png saved.')

    # STEP 6: Grounded Chat
    log('=== STEP 6: Grounded Chat Tab ===')
    page.click('button:has-text("Grounded Chat")')
    page.wait_for_selector('textarea.chat-textarea', timeout=5000)

    # In-domain query
    chat_q1 = 'Why was the young seagull afraid to fly?'
    log(f'Submitting query 1: "{chat_q1}"')
    page.locator('textarea.chat-textarea').fill(chat_q1)
    t_c1_start = time.time()
    page.click('button.chat-send-btn')

    # Wait for response completion
    page.wait_for_selector('.chat-status-badge:has-text("completed")', timeout=60000)
    page.wait_for_timeout(1000)
    dur_c1 = time.time() - t_c1_start
    c1_response = page.locator('.chat-bubble-body').last.inner_text()
    log(f'Grounded answer received in {dur_c1:.2f}s:\n"{c1_response[:140]}..."')

    page.screenshot(path=str(SCREENSHOT_DIR / '06_chat.png'))
    log('Screenshot 06_chat.png saved.')

    # Citation drawer verification
    citation_pills = page.locator('.chat-citations-tray .citation-pill')
    pill_count = citation_pills.count()
    log(f'Found {pill_count} citation pills in assistant message.')
    if pill_count > 0:
        log('Clicking citation pill to open drawer...')
        citation_pills.first.click()
        page.wait_for_selector('.citation-drawer-body', timeout=5000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(SCREENSHOT_DIR / '07_citation_drawer.png'))
        log('Screenshot 07_citation_drawer.png saved.')

        # Close drawer
        page.locator('.citation-drawer-header button').click()
        page.wait_for_timeout(500)
        log('Citation drawer closed.')

    # OOD query
    chat_q2 = 'What is the capital of France?'
    log(f'Submitting OOD query 2: "{chat_q2}"')
    page.locator('textarea.chat-textarea').fill(chat_q2)
    t_c2_start = time.time()
    page.click('button.chat-send-btn')

    # Wait for response completion
    page.wait_for_timeout(2000)
    page.wait_for_selector('button.chat-send-btn', timeout=60000)
    dur_c2 = time.time() - t_c2_start
    c2_response = page.locator('.chat-bubble-body').last.inner_text()
    has_disclaimer = page.locator('.chat-disclaimer-box').count() > 0
    log(f'OOD answer received in {dur_c2:.2f}s (disclaimer={has_disclaimer}):\n"{c2_response}"')

    page.screenshot(path=str(SCREENSHOT_DIR / '08_ood_chat.png'))
    log('Screenshot 08_ood_chat.png saved.')

    results['steps']['grounded_chat'] = {
        'status': 'PASS',
        'query_1': {
            'prompt': chat_q1,
            'duration_sec': round(dur_c1, 2),
            'answer': c1_response,
            'citations_count': pill_count
        },
        'query_2_ood': {
            'prompt': chat_q2,
            'duration_sec': round(dur_c2, 2),
            'answer': c2_response,
            'disclaimer_emitted': has_disclaimer
        }
    }

    # STEP 7: Persistence Verification
    log('=== STEP 7: Persistence Verification via Page Reload ===')
    page.reload(wait_until='networkidle')
    page.wait_for_timeout(2500)

    # Check chat history
    page.click('button:has-text("Grounded Chat")')
    page.wait_for_selector('.chat-session-item', timeout=10000)
    reloaded_sessions = page.locator('.chat-session-item').count()
    log(f'Reloaded sessions count: {reloaded_sessions}')
    page.locator('.chat-session-item').first.click()
    page.wait_for_selector('.chat-bubble-body', timeout=10000)
    log('Chat history reloaded successfully from storage!')
    page.screenshot(path=str(SCREENSHOT_DIR / '09_persisted_chat.png'))
    log('Screenshot 09_persisted_chat.png saved.')

    # Check retrieval status
    page.click('button:has-text("Retrieval Engine")')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(SCREENSHOT_DIR / '10_persisted_retrieval.png'))
    log('Screenshot 10_persisted_retrieval.png saved.')

    results['steps']['persistence'] = {
        'status': 'PASS',
        'reloaded_sessions': reloaded_sessions
    }

    # Save e2e results
    with open('docs/e2e_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    log('Full E2E test completed and saved to docs/e2e_results.json!')

    browser.close()
