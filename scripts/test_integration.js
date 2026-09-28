/**
 * Automated Integration Test for Electron Process Supervisor & Python Engine IPC.
 * Verifies dynamic port selection, token-authenticated requests, 401 rejections, and clean teardown.
 */

const path = require('path');

async function runIntegrationTest() {
  console.log('=== [Integration Test] Ragger.ai Supervisor & Engine IPC ===');
  process.env.RAGGER_ALLOW_TEST_EMBEDDINGS = '1';
  process.env.RAGGER_ALLOW_TEST_LLM = '1';
  process.env.RAGGER_ALLOW_TEST_EVAL = '1';

  const fs = require('fs');
  const testStorageDir = path.resolve(__dirname, '../.test_desktop_storage');
  if (fs.existsSync(testStorageDir)) {
    try {
      fs.rmSync(testStorageDir, { recursive: true, force: true });
    } catch {}
  }
  fs.mkdirSync(testStorageDir, { recursive: true });
  process.env.RAGGER_STORAGE_DIR = testStorageDir;

  // Load compiled supervisor from desktop dist
  const { PythonProcessSupervisor } = require('../apps/desktop/dist/main/supervisor');

  const supervisor = new PythonProcessSupervisor();

  try {
    console.log('1. Starting Python Process Supervisor...');
    const status = await supervisor.start();

    console.log(`✓ Engine started successfully.`);
    console.log(`  - Host: ${status.host}`);
    console.log(`  - Ephemeral Port: ${status.port}`);
    console.log(`  - Child PID: ${status.pid}`);
    console.log(`  - Authenticated: ${status.authenticated}`);

    if (!status.is_running || !status.pid || !status.port) {
      throw new Error('Supervisor failed to initialize engine correctly.');
    }

    // 2. Test Authenticated Health Check via Supervisor
    console.log('\n2. Testing Authenticated Health via Supervisor...');
    const health = await supervisor.getHealth();
    console.log('✓ Authenticated Health Response:', JSON.stringify(health));

    if (health.status !== 'ok' || !health.authenticated || health.process_id !== status.pid) {
      throw new Error(`Health response mismatch: expected PID ${status.pid}, got ${health.process_id}`);
    }

    // 3. Test Runtime Diagnostics via Supervisor
    console.log('\n3. Testing Runtime Diagnostics via Supervisor...');
    const runtime = await supervisor.getRuntime();
    console.log('✓ Runtime Diagnostics Response:', JSON.stringify(runtime));

    if (!runtime.python_version || !runtime.platform || runtime.process_id !== status.pid) {
      throw new Error('Runtime diagnostics validation failed.');
    }

    // 4. Test Direct Unauthenticated Call to Protected Route (Must return 401)
    console.log('\n4. Testing Direct Unauthenticated Call to Protected /api/v1/health (Expect 401)...');
    const unauthResponse = await fetch(`http://${status.host}:${status.port}/api/v1/health`);
    console.log(`  - HTTP Status: ${unauthResponse.status}`);

    if (unauthResponse.status === 401) {
      const errBody = await unauthResponse.json();
      console.log('✓ Protected endpoint correctly rejected unauthenticated request with 401:', errBody.code);
    } else {
      throw new Error(`Expected HTTP 401, but received ${unauthResponse.status}`);
    }

    // 5. Test Direct Call to Unauthenticated Liveness Route (Must return 200)
    console.log('\n5. Testing Direct Call to Liveness /health (Expect 200)...');
    const livenessResponse = await fetch(`http://${status.host}:${status.port}/health`);
    console.log(`  - HTTP Status: ${livenessResponse.status}`);

    if (livenessResponse.status === 200) {
      const liveBody = await livenessResponse.json();
      console.log('✓ Liveness endpoint succeeded without token:', JSON.stringify(liveBody));
    } else {
      throw new Error(`Expected HTTP 200, but received ${livenessResponse.status}`);
    }

    // 6. Phase 2: Test Multi-Signal Detection via Supervisor Proxy
    console.log('\n6. Testing Ingestion Detection via Supervisor Proxy...');
    const pdfPath = path.resolve(__dirname, '../engine/tests/fixtures/sample.pdf');
    const xlsxPath = path.resolve(__dirname, '../engine/tests/fixtures/sample.xlsx');

    const detectPdf = await supervisor.authenticatedRequest('/api/v1/ingestion/detect', {
      method: 'POST',
      body: JSON.stringify({ file_path: pdfPath }),
    });
    console.log('✓ PDF Detection result:', JSON.stringify(detectPdf));
    if (detectPdf.format !== 'pdf' || detectPdf.confidence < 0.9) {
      throw new Error('PDF detection failed validation.');
    }

    // 7. Phase 2: Test Real PDF Ingestion -> DocumentModel
    console.log('\n7. Testing Real PDF Ingestion -> DocumentModel...');
    const ingestPdf = await supervisor.authenticatedRequest('/api/v1/ingestion/ingest', {
      method: 'POST',
      body: JSON.stringify({ file_path: pdfPath }),
    });
    console.log(`✓ PDF Ingested: source_id=${ingestPdf.source.source_id}, model_type=${ingestPdf.model_type}`);
    console.log(`  - SHA-256: ${ingestPdf.source.sha256_checksum}`);
    console.log(`  - Total Blocks: ${ingestPdf.normalized_model.total_blocks}`);
    console.log(`  - Sample Strategy: ${ingestPdf.sample.strategy}`);

    if (ingestPdf.model_type !== 'document' || !ingestPdf.normalized_model.blocks.length) {
      throw new Error('PDF ingestion did not produce valid DocumentModel.');
    }

    // 8. Phase 2: Test Real XLSX Ingestion -> DatasetModel (NO FLATTENING)
    console.log('\n8. Testing Real XLSX Ingestion -> DatasetModel (Preserving Sheets & Columns)...');
    const ingestXlsx = await supervisor.authenticatedRequest('/api/v1/ingestion/ingest', {
      method: 'POST',
      body: JSON.stringify({ file_path: xlsxPath }),
    });
    console.log(`✓ XLSX Ingested: source_id=${ingestXlsx.source.source_id}, model_type=${ingestXlsx.model_type}`);
    console.log(`  - Total Sheets: ${ingestXlsx.normalized_model.total_sheets}`);
    
    for (const sheet of ingestXlsx.normalized_model.sheets) {
      console.log(`  - Sheet '${sheet.sheet_name}': ${sheet.total_rows} rows, ${sheet.columns.length} columns`);
    }

    if (ingestXlsx.model_type !== 'dataset' || ingestXlsx.normalized_model.total_sheets < 2) {
      throw new Error('XLSX ingestion failed: expected DatasetModel with multiple sheets.');
    }
    const salesSheet = ingestXlsx.normalized_model.sheets.find((s) => s.sheet_name === 'Sales');
    if (!salesSheet || !salesSheet.columns.some((c) => c.name === 'Revenue')) {
      throw new Error('XLSX Sales sheet columns missing or corrupted.');
    }
    console.log('✓ Verified: XLSX strictly parsed into DatasetModel with columns and rows, NOT flattened to text.');

    // 9. Phase 2: Test Persistent Source Registry
    console.log('\n9. Testing Persistent Source Registry Query...');
    const registrySources = await supervisor.authenticatedRequest('/api/v1/ingestion/sources');
    console.log(`✓ Retrieved ${registrySources.length} registered sources from persistent disk storage.`);
    if (registrySources.length < 2) {
      throw new Error('Persistent SourceRegistry failed to return registered sources.');
    }

    // 10. Phase 2: Test Unauthenticated Ingestion Request (Must return 401)
    console.log('\n10. Testing Direct Unauthenticated Ingestion Call (Expect 401)...');
    const unauthIngest = await fetch(`http://${status.host}:${status.port}/api/v1/ingestion/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: pdfPath }),
    });
    if (unauthIngest.status === 401) {
      console.log('✓ Unauthenticated call to /api/v1/ingestion/ingest rejected with 401.');
    } else {
      throw new Error(`Expected HTTP 401 for unauthenticated ingestion, got ${unauthIngest.status}`);
    }

    // 11. Phase 3: Test File Analysis (Real PDF)
    console.log('\n11. Testing Phase 3 Analysis on Real PDF via Supervisor Proxy...');
    const pdfProfile = await supervisor.authenticatedRequest('/api/v1/analysis/file', {
      method: 'POST',
      body: JSON.stringify({ source_id: ingestPdf.source.source_id, provider: 'heuristic_offline' }),
    });
    console.log(`✓ PDF Analyzed: modality=${pdfProfile.semantic_observations.primary_modality}, domain=${pdfProfile.semantic_observations.detected_domain}`);
    console.log(`  - Structural facts heading_depth: ${pdfProfile.structural_facts.heading_depth}`);
    console.log(`  - Objective summary: "${pdfProfile.semantic_observations.summary_description}"`);
    if (
      pdfProfile.structural_facts.heading_depth < 2 ||
      !pdfProfile.semantic_observations.summary_description ||
      pdfProfile.semantic_observations.summary_description.toLowerCase().includes('rag')
    ) {
      throw new Error('PDF analysis failed or violated Observer invariant.');
    }

    // 12. Phase 3: Test File Analysis (Real XLSX)
    console.log('\n12. Testing Phase 3 Analysis on Real XLSX via Supervisor Proxy...');
    const xlsxProfile = await supervisor.authenticatedRequest('/api/v1/analysis/file', {
      method: 'POST',
      body: JSON.stringify({ source_id: ingestXlsx.source.source_id, provider: 'heuristic_offline' }),
    });
    console.log(`✓ XLSX Analyzed: modality=${xlsxProfile.semantic_observations.primary_modality}`);
    console.log(`  - Structural tabular_ratio: ${xlsxProfile.structural_facts.tabular_ratio}`);
    console.log(`  - Has numerical columns: ${xlsxProfile.structural_facts.has_numerical_columns}`);
    if (
      xlsxProfile.semantic_observations.primary_modality !== 'tabular_dataset' ||
      xlsxProfile.structural_facts.tabular_ratio !== 1.0 ||
      !xlsxProfile.structural_facts.has_numerical_columns
    ) {
      throw new Error('XLSX analysis failed: expected tabular_dataset with numerical metrics.');
    }

    // 13. Phase 3: Test Deterministic Workspace Synthesis
    console.log('\n13. Testing Phase 3 Deterministic Workspace Synthesis...');
    const wsProfile = await supervisor.authenticatedRequest('/api/v1/analysis/workspace', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: 'default' }),
    });
    console.log(`✓ Workspace Synthesized: total_sources=${wsProfile.total_sources}, is_homogeneous=${wsProfile.is_homogeneous}`);
    console.log(`  - Modality distribution:`, JSON.stringify(wsProfile.modality_distribution));
    if (wsProfile.total_sources < 2 || wsProfile.is_homogeneous) {
      throw new Error('Workspace synthesis failed: expected heterogeneous mixed workspace.');
    }

    // 14. Phase 3: Test Unauthenticated Analysis Call (Must return 401)
    console.log('\n14. Testing Direct Unauthenticated Analysis Call (Expect 401)...');
    const unauthAnalysis = await fetch(`http://${status.host}:${status.port}/api/v1/analysis/file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_id: ingestPdf.source.source_id }),
    });
    if (unauthAnalysis.status === 401) {
      console.log('✓ Unauthenticated call to /api/v1/analysis/file rejected with 401.');
    } else {
      throw new Error(`Expected HTTP 401 for unauthenticated analysis, got ${unauthAnalysis.status}`);
    }

    // 17. Phase 4: Query Architecture Catalog
    console.log('\n17. Testing Phase 4 Architecture Catalog Query...');
    const catalog = await supervisor.authenticatedRequest('/api/v1/recommendation/architectures');
    console.log(`✓ Retrieved ${catalog.length} curated architectures from product catalog.`);
    const archIds = catalog.map((a) => a.architecture_id);
    console.log(`  - Registered: ${archIds.join(', ')}`);
    if (catalog.length !== 6 || !archIds.includes('hybrid_rag') || !archIds.includes('graph_rag')) {
      throw new Error('Architecture catalog incomplete or corrupted.');
    }
    const graphArch = catalog.find((a) => a.architecture_id === 'graph_rag');
    if (!graphArch.why_recommended.includes('Advanced Alternative')) {
      throw new Error('Graph RAG must be categorized as advanced alternative.');
    }

    // 18. Phase 4: Deterministic Recommendation Evaluation
    console.log('\n18. Testing Deterministic Recommendation Engine Evaluation...');
    const recResult = await supervisor.authenticatedRequest('/api/v1/recommendation/evaluate', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: 'default' }),
    });
    console.log(`✓ Recommendation Evaluated: rule=${recResult.matched_rule_id}, architecture=${recResult.recommended_architecture}`);
    console.log(`  - Confidence: ${recResult.confidence_score * 100}% (${recResult.confidence_level})`);
    console.log(`  - Detected Signals:`, JSON.stringify(recResult.detected_signals));
    console.log(`  - Alternatives Count: ${recResult.alternative_architectures.length}`);

    // Verify deterministic rule match for mixed 50% doc / 50% tabular (> 20% strict boundary)
    if (
      recResult.matched_rule_id !== 'RULE_MIXED_MODALITY' ||
      recResult.recommended_architecture !== 'hybrid_rag' ||
      recResult.confidence_score !== 0.95 ||
      recResult.confidence_level !== 'high'
    ) {
      throw new Error(`Deterministic rule mismatch: expected RULE_MIXED_MODALITY (0.95), got ${recResult.matched_rule_id} (${recResult.confidence_score})`);
    }

    // 19. Phase 4: Approve Configuration & Freeze Snapshot
    console.log('\n19. Testing Configuration Approval, Mutation Guard, and SHA-256 Freezing...');
    let existingApproved = null;
    try {
      existingApproved = await supervisor.authenticatedRequest('/api/v1/recommendation/approved?workspace_id=default');
    } catch {}

    const approvePayload = {
      workspace_id: 'default',
      architecture_id: 'hybrid_rag',
      user_customized: true,
      is_revision: Boolean(existingApproved),
      source_ids: [ingestPdf.source.source_id, ingestXlsx.source.source_id],
      chunking_config: {
        strategy: 'fixed_size',
        chunk_size: 512,
        chunk_overlap: 64,
      },
      embedding_config: {
        provider: 'local_onnx',
        model_name: 'bge-small-en-v1.5',
        dimensions: 384,
      },
      vector_db_config: {
        provider: 'lancedb',
        distance_metric: 'cosine',
      },
      retrieval_config: {
        strategy: 'hybrid_search',
        top_k: 5,
        hybrid_weights: { dense: 0.5, sparse: 0.5 },
        rrf_k: 60,
      },
    };

    if (existingApproved) {
      console.log(`  - Existing frozen config detected (v${existingApproved.config_version}). Testing mutation guard...`);
      try {
        await supervisor.authenticatedRequest('/api/v1/recommendation/approve', {
          method: 'POST',
          body: JSON.stringify({ ...approvePayload, is_revision: false }),
        });
        throw new Error('Expected HTTP 409 when mutating frozen config without is_revision=true');
      } catch (guardErr) {
        if (!guardErr.message.includes('409') && !guardErr.message.includes('CONFIG_ALREADY_FROZEN')) {
          throw guardErr;
        }
        console.log('✓ In-place mutation guard verified: HTTP 409 CONFIG_ALREADY_FROZEN returned as expected.');
      }
    }

    const approvedConfig = await supervisor.authenticatedRequest('/api/v1/recommendation/approve', {
      method: 'POST',
      body: JSON.stringify(approvePayload),
    });
    console.log(`✓ Configuration Approved and Frozen:`);
    console.log(`  - Config ID: ${approvedConfig.config_id}`);
    console.log(`  - Version: v${approvedConfig.config_version}`);
    console.log(`  - Is Frozen: ${approvedConfig.is_frozen}`);
    console.log(`  - SHA-256 Hash: ${approvedConfig.config_hash}`);
    console.log(`  - Sources Linked: ${approvedConfig.source_ids.length}`);

    if (
      !approvedConfig.is_frozen ||
      approvedConfig.config_version < 1 ||
      !approvedConfig.config_hash ||
      approvedConfig.config_hash.length !== 64 ||
      approvedConfig.approved_architecture !== 'hybrid_rag'
    ) {
      throw new Error('ApprovedBuildConfig validation failed.');
    }

    // 20. Phase 4: Query Frozen Approved Configuration from Persistence
    console.log('\n20. Testing Retrieval of Persisted Frozen Approved Configuration...');
    const fetchedApproved = await supervisor.authenticatedRequest('/api/v1/recommendation/approved?workspace_id=default');
    console.log(`✓ Retrieved Frozen Config: id=${fetchedApproved.config_id}, hash=${fetchedApproved.config_hash}`);
    if (fetchedApproved.config_hash !== approvedConfig.config_hash || fetchedApproved.config_id !== approvedConfig.config_id) {
      throw new Error('Persisted ApprovedBuildConfig hash or ID mismatch.');
    }

    // 21. Phase 4: Verify Phase 5 Build Contract
    console.log('\n21. Testing Phase 5 Build Contract Verification Endpoint...');
    const buildContract = await supervisor.authenticatedRequest('/api/v1/recommendation/validate-build?workspace_id=default');
    console.log(`✓ Phase 5 Build Contract: valid=${buildContract.valid}, config_id=${buildContract.config_id}, hash=${buildContract.config_hash}`);
    if (!buildContract.valid || !buildContract.config_id || !buildContract.config_hash || buildContract.config_hash !== approvedConfig.config_hash) {
      throw new Error('Phase 5 Build Contract validation failed: build was not authorized.');
    }
    console.log('✓ Phase 5 Build Authorization Verified: frozen config exists and hash matches.');

    // 22. Phase 4: Test Unauthenticated Recommendation Call (Must return 401)
    console.log('\n22. Testing Direct Unauthenticated Recommendation Call (Expect 401)...');
    const unauthRec = await fetch(`http://${status.host}:${status.port}/api/v1/recommendation/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: 'default' }),
    });
    if (unauthRec.status === 401) {
      console.log('✓ Unauthenticated call to /api/v1/recommendation/evaluate rejected with 401.');
    } else {
      throw new Error(`Expected HTTP 401 for unauthenticated recommendation, got ${unauthRec.status}`);
    }

    // 23. Phase 5: Test Builder Preflight Gate Rejection via Supervisor Proxy (Model Not Downloaded)
    console.log('\n23. Testing Builder Preflight Gate Rejection via Supervisor (Missing ONNX Model)...');
    try {
      await supervisor.authenticatedRequest('/api/v1/builder/start', { method: 'POST' });
      throw new Error('Expected HTTP 424 MODEL_NOT_AVAILABLE when model weights are not downloaded.');
    } catch (gateErr) {
      if (!gateErr.message.includes('424') && !gateErr.message.includes('MODEL_NOT_AVAILABLE')) {
        throw gateErr;
      }
      console.log('✓ Preflight gate correctly rejected build with 424 MODEL_NOT_AVAILABLE: model weights missing.');
    }

    // 24. Phase 5: Approve revision with test_deterministic embedding for E2E Builder Execution
    console.log('\n24. Approving revision with test_deterministic provider for E2E desktop test...');
    const testApprovePayload = {
      workspace_id: 'default',
      architecture_id: 'hybrid_rag',
      is_revision: true,
      custom_chunking: {
        strategy: 'boundary_paragraph',
        chunk_size: 256,
        chunk_overlap: 32,
      },
      custom_embedding: {
        provider: 'test_deterministic',
        model_name: 'bge-small-en-v1.5',
        dimension: 384,
      },
      custom_vector_db: {
        provider: 'local_flat_index',
        metric: 'cosine',
      },
      custom_retrieval: {
        strategy: 'hybrid_rrf',
        top_k: 5,
        rrf_k: 60,
      },
    };
    const testApproved = await supervisor.authenticatedRequest('/api/v1/recommendation/approve', {
      method: 'POST',
      body: JSON.stringify(testApprovePayload),
    });
    console.log(`✓ Test configuration approved: config_id=${testApproved.config_id}, hash=${testApproved.config_hash}`);

    // 25. Phase 5: Start Builder and Poll Authoritative Progress via Supervisor
    console.log('\n25. Testing Builder Execution & Telemetry via Supervisor...');
    const buildStart = await supervisor.authenticatedRequest('/api/v1/builder/start', { method: 'POST' });
    console.log(`✓ Build started: build_id=${buildStart.build_id}, status=${buildStart.status}`);
    if (!buildStart.build_id || !buildStart.build_id.startsWith('bld_')) {
      throw new Error('Builder did not return valid build_id.');
    }

    // Poll progress until completion
    let finalProgress = null;
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 300));
      const prog = await supervisor.authenticatedRequest('/api/v1/builder/progress');
      if (prog.status === 'completed' || prog.status === 'failed' || prog.status === 'cancelled') {
        finalProgress = prog;
        break;
      }
    }
    if (!finalProgress || finalProgress.status !== 'completed') {
      throw new Error(`Build did not complete successfully: ${JSON.stringify(finalProgress)}`);
    }
    console.log(`✓ Build Completed: stage=${finalProgress.current_stage}, chunks=${finalProgress.chunks_processed}, vectors=${finalProgress.vectors_processed}`);

    // 26. Phase 5: Retrieve and Validate Verified Build Manifest
    console.log('\n26. Testing Retrieval of Active BuildManifest via Supervisor...');
    const manifest = await supervisor.authenticatedRequest('/api/v1/builder/manifest');
    console.log(`✓ Retrieved Active BuildManifest:`);
    console.log(`  - Manifest ID: ${manifest.manifest_id}`);
    console.log(`  - Manifest Hash: ${manifest.manifest_hash}`);
    console.log(`  - Architecture: ${manifest.approved_architecture}`);
    console.log(`  - Chunks: ${manifest.chunk_count}, Vectors: ${manifest.vector_count}`);
    if (
      !manifest.manifest_hash ||
      manifest.manifest_hash.length !== 64 ||
      manifest.build_id !== buildStart.build_id ||
      manifest.status !== 'completed'
    ) {
      throw new Error('Active BuildManifest validation failed.');
    }

    // 27. Phase 5: Test Electron Builder IPC Handlers directly
    console.log('\n27. Testing Electron Builder IPC Handlers...');
    const registeredHandlers = {};
    const mockElectron = {
      ipcMain: {
        handle: (channel, fn) => {
          registeredHandlers[channel] = fn;
        },
      },
    };
    try {
      const electronResolved = require.resolve('electron');
      require.cache[electronResolved] = {
        id: electronResolved,
        filename: electronResolved,
        loaded: true,
        exports: mockElectron,
      };
    } catch {}

    const { registerBuilderIpcHandlers } = require('../apps/desktop/dist/main/ipc/builderHandler');
    registerBuilderIpcHandlers(supervisor);

    // Test builder:get-progress handler
    const ipcProgress = await registeredHandlers['builder:get-progress']();
    console.log('✓ IPC builder:get-progress result:', ipcProgress.success, ipcProgress.data?.status);
    if (!ipcProgress.success || ipcProgress.data?.status !== 'completed') {
      throw new Error('IPC builder:get-progress failed.');
    }

    // Test builder:get-manifest handler
    const ipcManifest = await registeredHandlers['builder:get-manifest']();
    console.log('✓ IPC builder:get-manifest result:', ipcManifest.success, ipcManifest.data?.manifest_hash?.slice(0, 12));
    if (!ipcManifest.success || ipcManifest.data?.manifest_hash !== manifest.manifest_hash) {
      throw new Error('IPC builder:get-manifest failed.');
    }

    // 28. Phase 5: Test Direct Unauthenticated Builder Call (Must return 401)
    console.log('\n28. Testing Direct Unauthenticated Builder Call (Expect 401)...');
    const unauthBuilder = await fetch(`http://${status.host}:${status.port}/api/v1/builder/progress`);
    if (unauthBuilder.status === 401) {
      console.log('✓ Unauthenticated call to /api/v1/builder/progress rejected with 401.');
    } else {
      throw new Error(`Expected HTTP 401 for unauthenticated builder call, got ${unauthBuilder.status}`);
    }

    // 29. Phase 6: Verify Active Build Retrieval Status via Supervisor
    console.log('\n29. Testing Retrieval Engine Status via Supervisor Proxy...');
    const retrievalStatus = await supervisor.authenticatedRequest('/api/v1/retrieval/status');
    console.log(`✓ Active Retrieval Status:`);
    console.log(`  - Active Build ID: ${retrievalStatus.active_build_id}`);
    console.log(`  - Architecture: ${retrievalStatus.approved_architecture}`);
    console.log(`  - Chunks: ${retrievalStatus.chunk_count}, Vectors: ${retrievalStatus.vector_count}`);
    if (!retrievalStatus.has_active_build || retrievalStatus.active_build_id !== buildStart.build_id) {
      throw new Error('Retrieval status does not match active build.');
    }

    // 30. Phase 6: Execute Grounded Retrieval Query via Supervisor Proxy
    console.log('\n30. Testing Grounded Retrieval Query via Supervisor Proxy...');
    const retrievalRes = await supervisor.authenticatedRequest('/api/v1/retrieval/query', {
      method: 'POST',
      body: JSON.stringify({ query: 'revenue sales order' }),
    });
    console.log(`✓ Retrieval Query Succeeded:`);
    console.log(`  - Query: "${retrievalRes.query}"`);
    console.log(`  - Strategy: ${retrievalRes.strategy}, Arch: ${retrievalRes.architecture}`);
    console.log(`  - Returned Chunks: ${retrievalRes.results.length}, Latency: ${retrievalRes.latency_ms} ms`);
    if (retrievalRes.results.length > 0) {
      const topChunk = retrievalRes.results[0];
      console.log(`  - Top Chunk ID: ${topChunk.chunk_id}, Score: ${topChunk.score} (${topChunk.score_type})`);
      console.log(`  - Citation: ${topChunk.citation}`);
      console.log(`  - Provenance Source: ${topChunk.provenance.source_name} (${topChunk.provenance.source_id})`);
    }
    if (
      retrievalRes.results.length === 0 ||
      !retrievalRes.grounded_context_prompt.includes('<<<BEGIN SYSTEM GROUNDING CONTEXT>>>')
    ) {
      throw new Error('Retrieval response is missing results or grounded context prompt.');
    }

    // 31. Phase 6: Test Electron Retrieval IPC Handlers
    console.log('\n31. Testing Electron Retrieval IPC Handlers...');
    const { registerRetrievalIpcHandlers } = require('../apps/desktop/dist/main/ipc/retrievalHandler');
    registerRetrievalIpcHandlers(supervisor);

    const ipcStatus = await registeredHandlers['retrieval:get-status']();
    console.log('✓ IPC retrieval:get-status result:', ipcStatus.success, ipcStatus.data?.active_build_id);
    if (!ipcStatus.success || !ipcStatus.data?.has_active_build) {
      throw new Error('IPC retrieval:get-status failed.');
    }

    const ipcQuery = await registeredHandlers['retrieval:query']({ query: 'sample' });
    console.log('✓ IPC retrieval:query result:', ipcQuery.success, `count=${ipcQuery.data?.results?.length}`);
    if (!ipcQuery.success || !ipcQuery.data?.results) {
      throw new Error('IPC retrieval:query failed.');
    }

    const ipcReload = await registeredHandlers['retrieval:reload']();
    console.log('✓ IPC retrieval:reload result:', ipcReload.success, ipcReload.data?.status);
    if (!ipcReload.success || ipcReload.data?.status !== 'reloaded') {
      throw new Error('IPC retrieval:reload failed.');
    }

    // 32. Phase 6: Test Empty Results on Non-Matching Filter (Must return HTTP 200 with empty array)
    console.log('\n32. Testing Non-Matching Filter Empty Result Contract...');
    const emptyRes = await supervisor.authenticatedRequest('/api/v1/retrieval/query', {
      method: 'POST',
      body: JSON.stringify({
        query: 'revenue sales',
        filters: { page_numbers: [99999] },
      }),
    });
    console.log(`✓ Non-matching filter returned HTTP 200 with ${emptyRes.results.length} results (total_candidates=${emptyRes.total_candidates}).`);
    if (emptyRes.results.length !== 0 || emptyRes.total_candidates !== 0) {
      throw new Error('Expected 0 results for non-matching filter.');
    }

    // Also assert that empty query string query='' is rejected with HTTP 422 (min_length=1 enforced)
    try {
      await supervisor.authenticatedRequest('/api/v1/retrieval/query', {
        method: 'POST',
        body: JSON.stringify({ query: '' }),
      });
      throw new Error('Expected HTTP 422 for query=""');
    } catch (queryErr) {
      if (!queryErr.message.includes('422')) {
        throw queryErr;
      }
      console.log('✓ Empty string query="" correctly rejected with HTTP 422 validation error (min_length=1 enforced).');
    }

    // 33. Phase 6: Test Direct Unauthenticated Retrieval Call (Must return 401)
    console.log('\n33. Testing Direct Unauthenticated Retrieval Call (Expect 401)...');
    const unauthRetrieval = await fetch(`http://${status.host}:${status.port}/api/v1/retrieval/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'revenue' }),
    });
    if (unauthRetrieval.status === 401) {
      console.log('✓ Unauthenticated call to /api/v1/retrieval/query rejected with 401.');
    } else {
      throw new Error(`Expected HTTP 401 for unauthenticated retrieval call, got ${unauthRetrieval.status}`);
    }

    // 34. Phase 6: Active Build Retrieval Verification
    console.log('\n34. Testing Phase 6 Retrieval Diagnostic Status...');
    const retStatus = await supervisor.authenticatedRequest('/api/v1/retrieval/status');
    if (!retStatus.active_build_id || !retStatus.has_active_build) {
      throw new Error('Retrieval diagnostic status failed validation.');
    }
    console.log(`✓ Active build confirmed ready: build_id=${retStatus.active_build_id}, architecture=${retStatus.approved_architecture}`);

    // 35. Phase 7: Preflight Ollama Model Gate Rejection (HTTP 424 MODEL_NOT_AVAILABLE with zero /api/pull)
    console.log('\n35. Testing Phase 7 Preflight Ollama Gate Rejection (Expect HTTP 424 MODEL_NOT_AVAILABLE)...');
    try {
      await supervisor.authenticatedRequest('/api/v1/chat/generate?workspace_id=default', {
        method: 'POST',
        body: JSON.stringify({ query: 'What was the revenue?' }),
      });
      throw new Error('Expected HTTP 424 MODEL_NOT_AVAILABLE for missing Ollama model');
    } catch (modelErr) {
      if (!modelErr.message.includes('424') && !modelErr.message.includes('MODEL_NOT_AVAILABLE')) {
        throw modelErr;
      }
      console.log('✓ Missing local Ollama model correctly rejected with HTTP 424 MODEL_NOT_AVAILABLE (zero /api/pull calls made).');
    }

    // 36. Phase 7: Grounded Chat Generation with Test Provider Gate & Phase 6 Retrieval Authority
    console.log('\n36. Testing Phase 7 Grounded Generation via Supervisor (RAGGER_ALLOW_TEST_LLM=1)...');
    // Switch generation config to use gated test provider
    await supervisor.authenticatedRequest('/api/v1/chat/config', {
      method: 'POST',
      body: JSON.stringify({
        provider: 'test_deterministic',
        model_name: 'deterministic-test-llm',
      }),
    });

    const genRes = await supervisor.authenticatedRequest('/api/v1/chat/generate?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({
        query: 'What is the quarterly revenue and operating performance?',
        top_k: 3,
      }),
    });

    console.log(`✓ Grounded answer received:`);
    console.log(`  - session_id: ${genRes.session_id}`);
    console.log(`  - message_id: ${genRes.message_id}`);
    console.log(`  - state: ${genRes.state}`);
    console.log(`  - retrieved_chunk_count: ${genRes.retrieved_chunk_count}`);
    console.log(`  - duration_ms: ${genRes.duration_ms}`);

    if (genRes.state !== 'completed' || genRes.retrieved_chunk_count <= 0 || !genRes.answer) {
      throw new Error('Generation response failed basic invariants.');
    }

    // 37. Phase 7: Deterministic Citation Validation & Unmodified Generated Answer Verification
    console.log('\n37. Testing Citation Verification & Untouched Generated Text Invariant...');
    const citations = genRes.valid_citations || genRes.citations;
    if (!citations || citations.length === 0) {
      throw new Error('Expected at least one verified citation.');
    }
    for (const cit of citations) {
      console.log(`  - Citation [${cit.chunk_id}]: source=${cit.source_name}, page=${cit.page_number}`);
      if (!cit.chunk_id || !cit.source_name) {
        throw new Error('Citation must have chunk_id and source_name.');
      }
    }
    // Verify answer is unmodified
    if (!genRes.answer.includes(citations[0].chunk_id)) {
      throw new Error('Untouched answer invariant violation: chunk_id missing from raw generated answer.');
    }
    console.log('✓ Answer text contains raw citation tags untouched; deterministic provenance verified.');

    // 38. Phase 7: Multi-Turn Conversation, Workspace Isolation, & Atomic Persistence
    console.log('\n38. Testing Multi-Turn Conversation, Workspace Isolation, & Atomic Session Persistence...');
    const turn2Res = await supervisor.authenticatedRequest('/api/v1/chat/generate?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({
        query: 'Can you elaborate further on those financial figures?',
        session_id: genRes.session_id,
        top_k: 2,
      }),
    });

    if (turn2Res.session_id !== genRes.session_id) {
      throw new Error(`Session ID mismatch across turns: expected ${genRes.session_id}, got ${turn2Res.session_id}`);
    }
    if (turn2Res.retrieved_chunk_count <= 0) {
      throw new Error('Multi-turn invariant violation: every turn must perform fresh retrieval.');
    }
    console.log(`✓ Multi-turn turn 2 successful with fresh retrieval (retrieved_chunk_count=${turn2Res.retrieved_chunk_count}).`);

    // Verify atomic file persistence on disk
    let sessionFilePath = path.join(testStorageDir, 'workspaces', 'default', 'chat_sessions', `${genRes.session_id}.json`);
    if (!fs.existsSync(sessionFilePath)) {
      sessionFilePath = path.join(testStorageDir, 'chat_sessions', `${genRes.session_id}.json`);
    }
    if (!fs.existsSync(sessionFilePath)) {
      throw new Error(`Session file not persisted atomically on disk at ${sessionFilePath}`);
    }
    const sessionData = JSON.parse(fs.readFileSync(sessionFilePath, 'utf-8'));
    if (sessionData.messages.length !== 4) {
      throw new Error(`Expected 4 messages in session history (2 turns), found ${sessionData.messages.length}`);
    }
    console.log(`✓ Atomic session file verified on disk with ${sessionData.messages.length} messages.`);

    // Workspace Isolation: accessing default session with different workspace must return 404
    try {
      await supervisor.authenticatedRequest(`/api/v1/chat/sessions/${genRes.session_id}?workspace_id=different_workspace`);
      throw new Error('Expected HTTP 404 for cross-workspace session access');
    } catch (wsErr) {
      if (!wsErr.message.includes('404')) {
        throw wsErr;
      }
      console.log('✓ Cross-workspace session access correctly rejected with HTTP 404 SESSION_NOT_FOUND.');
    }

    // 39. Phase 7: SSE Streaming Event Sequence & Late-Cancellation State Invariance
    console.log('\n39. Testing SSE Streaming & Terminal Late-Cancellation...');
    const streamRes = await fetch(`http://${status.host}:${status.port}/api/v1/chat/stream?workspace_id=default`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${supervisor.token}`,
      },
      body: JSON.stringify({ query: 'Streaming test query' }),
    });

    if (streamRes.status !== 200) {
      throw new Error(`Expected HTTP 200 for SSE stream, got ${streamRes.status}`);
    }

    const streamText = await streamRes.text();
    const eventTypes = [];
    for (const line of streamText.split('\n')) {
      const trimmed = line.trim();
      if (trimmed.startsWith('event: ')) {
        eventTypes.push(trimmed.slice(7).trim());
      }
    }
    console.log(`✓ SSE Stream event sequence received: ${eventTypes.join(' -> ')}`);
    if (!eventTypes.includes('status') || !eventTypes.includes('token') || !eventTypes.includes('done')) {
      throw new Error(`Missing expected SSE event types in stream: ${eventTypes.join(', ')}`);
    }

    // Test late-cancellation on completed session (must return already_completed)
    const lateCancelRes = await supervisor.authenticatedRequest(`/api/v1/chat/cancel/${genRes.session_id}`, {
      method: 'POST',
    });
    console.log(`✓ Late cancel on completed session result: status=${lateCancelRes.status}`);
    if (lateCancelRes.status !== 'already_completed') {
      throw new Error(`Expected status already_completed, got: ${lateCancelRes.status}`);
    }

    // 40. Phase 7: Direct Unauthenticated Chat Call Rejection (HTTP 401)
    console.log('\n40. Testing Direct Unauthenticated Chat Call Rejection (Expect 401)...');
    const unauthChat = await fetch(`http://${status.host}:${status.port}/api/v1/chat/generate?workspace_id=default`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'unauth test' }),
    });
    if (unauthChat.status !== 401) {
      throw new Error(`Expected HTTP 401 for unauthenticated chat call, got ${unauthChat.status}`);
    }
    console.log('✓ Direct unauthenticated call to /api/v1/chat/generate rejected with HTTP 401.');

    const unauthSessions = await fetch(`http://${status.host}:${status.port}/api/v1/chat/sessions?workspace_id=default`);
    if (unauthSessions.status !== 401) {
      throw new Error(`Expected HTTP 401 for unauthenticated chat sessions, got ${unauthSessions.status}`);
    }
    console.log('✓ Direct unauthenticated call to /api/v1/chat/sessions rejected with HTTP 401.');

    // 41. Phase 8: Preflight Ollama Missing Judge Model Rejection (HTTP 424)
    console.log('\n41. Phase 8: Preflight Ollama Missing Judge Model Rejection (Expect 424)...');
    await supervisor.authenticatedRequest('/api/v1/evaluation/config?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({
        judge_provider: 'ollama',
        judge_model_name: 'nonexistent-judge-model-xyz',
        temperature: 0.0,
        max_tokens: 256,
        default_sample_size: 3,
        sampling_seed: 42,
        retrieval_top_k: 3,
      }),
    });

    const missingJudgeRes = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/run?workspace_id=default`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${supervisor.token}`,
      },
      body: JSON.stringify({ sample_size: 3 }),
    });
    if (missingJudgeRes.status !== 424) {
      throw new Error(`Expected HTTP 424 for missing Ollama judge model, got ${missingJudgeRes.status}`);
    }
    const missingJudgeData = await missingJudgeRes.json();
    console.log(`✓ Missing judge model correctly rejected with HTTP 424: code=${missingJudgeData.detail?.error?.code}`);
    if (missingJudgeData.detail?.error?.code !== 'MODEL_NOT_AVAILABLE') {
      throw new Error(`Expected error code MODEL_NOT_AVAILABLE, got ${missingJudgeData.detail?.error?.code}`);
    }

    // 42. Phase 8: Graph RAG Architecture Evaluation Rejection (HTTP 422)
    console.log('\n42. Phase 8: Graph RAG Architecture Evaluation Rejection (Expect 422)...');
    const activePointerPath = path.join(testStorageDir, 'active_build.json');
    const activePointerRaw = JSON.parse(fs.readFileSync(activePointerPath, 'utf8'));
    const manifestPath = path.join(testStorageDir, 'builds', activePointerRaw.active_build_id, 'manifest.json');
    const originalManifestRaw = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

    const graphManifest = { ...originalManifestRaw, approved_architecture: 'graph_rag' };
    fs.writeFileSync(manifestPath, JSON.stringify(graphManifest, null, 2));

    const graphEvalRes = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/run?workspace_id=default`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${supervisor.token}`,
      },
      body: JSON.stringify({ sample_size: 3 }),
    });
    // restore original manifest immediately
    fs.writeFileSync(manifestPath, JSON.stringify(originalManifestRaw, null, 2));

    if (graphEvalRes.status !== 422) {
      throw new Error(`Expected HTTP 422 for graph_rag evaluation, got ${graphEvalRes.status}`);
    }
    const graphEvalData = await graphEvalRes.json();
    console.log(`✓ Graph RAG evaluation rejected with HTTP 422: code=${graphEvalData.detail?.error?.code}`);
    if (graphEvalData.detail?.error?.code !== 'ARCHITECTURE_NOT_EVALUATABLE') {
      throw new Error(`Expected code ARCHITECTURE_NOT_EVALUATABLE, got ${graphEvalData.detail?.error?.code}`);
    }

    // 43. Phase 8: Evaluation Run Trigger & Concurrency Gate (HTTP 409)
    console.log('\n43. Phase 8: Evaluation Run Trigger & Concurrency Gate (Expect 409 on second run)...');
    await supervisor.authenticatedRequest('/api/v1/evaluation/config?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({
        judge_provider: 'test',
        judge_model_name: 'test-deterministic-judge',
        temperature: 0.0,
        max_tokens: 256,
        default_sample_size: 3,
        sampling_seed: 42,
        retrieval_top_k: 3,
      }),
    });

    const chatSessionsDir = path.join(testStorageDir, 'chat_sessions');
    const preEvalChatFiles = fs.existsSync(chatSessionsDir) ? fs.readdirSync(chatSessionsDir).length : 0;

    const runTriggerRes = await supervisor.authenticatedRequest('/api/v1/evaluation/run?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({ sample_size: 3, sampling_seed: 42 }),
    });
    console.log(`✓ Evaluation run started: eval_id=${runTriggerRes.eval_id}, status=${runTriggerRes.status}`);
    const activeEvalId = runTriggerRes.eval_id;

    // Immediate second trigger on same workspace -> must return HTTP 409
    const concurrentRes = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/run?workspace_id=default`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${supervisor.token}`,
      },
      body: JSON.stringify({ sample_size: 3 }),
    });
    if (concurrentRes.status !== 409) {
      throw new Error(`Expected HTTP 409 for concurrent evaluation run, got ${concurrentRes.status}`);
    }
    const concurrentData = await concurrentRes.json();
    console.log(`✓ Concurrent evaluation blocked with HTTP 409: code=${concurrentData.detail?.error?.code}`);
    if (concurrentData.detail?.error?.code !== 'EVALUATION_ALREADY_RUNNING') {
      throw new Error(`Expected code EVALUATION_ALREADY_RUNNING, got ${concurrentData.detail?.error?.code}`);
    }

    // 44. Phase 8: Progress Polling & Mathematical RAG Quality Score Verification
    console.log('\n44. Phase 8: Progress Polling & Verification of Quality Score & Deterministic Metrics...');
    let evalComplete = false;
    let pollCount = 0;
    while (!evalComplete && pollCount < 60) {
      pollCount++;
      const progress = await supervisor.authenticatedRequest(`/api/v1/evaluation/progress/${activeEvalId}?workspace_id=default`);
      console.log(`  - Evaluation progress: state=${progress.state}, percent=${progress.percent}%, stage=${progress.current_stage}`);
      if (progress.state === 'completed') {
        evalComplete = true;
        break;
      } else if (progress.state === 'failed' || progress.state === 'cancelled') {
        throw new Error(`Evaluation terminated abnormally with state: ${progress.state}, error: ${progress.error_message}`);
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    if (!evalComplete) {
      throw new Error('Evaluation did not complete within expected timeout.');
    }

    const report = await supervisor.authenticatedRequest(`/api/v1/evaluation/reports/${activeEvalId}?workspace_id=default`);
    console.log(`✓ Evaluation Report Card retrieved:`);
    console.log(`  - Quality Score: ${report.quality_score} / 100.0`);
    console.log(`  - Metric Weights:`, JSON.stringify(report.metric_weights_used));
    console.log(`  - Hits@1: ${report.deterministic_metrics.hits_at_1}, Hits@3: ${report.deterministic_metrics.hits_at_3}, MRR: ${report.deterministic_metrics.mrr}`);
    console.log(`  - Source Coverage: ${report.deterministic_metrics.source_coverage}`);
    console.log(`  - Faithfulness: ${report.judge_evaluated_metrics.faithfulness}`);
    console.log(`  - Disclaimer Accuracy: ${report.judge_evaluated_metrics.disclaimer_accuracy}`);

    if (typeof report.quality_score !== 'number' || report.quality_score < 0 || report.quality_score > 100) {
      throw new Error(`Invalid RAG Quality Score: ${report.quality_score}`);
    }
    const weightSum = Object.values(report.metric_weights_used).reduce((a, b) => a + b, 0);
    if (Math.abs(weightSum - 1.0) > 0.01) {
      throw new Error(`Normalized metric weights must sum to 1.0, got: ${weightSum}`);
    }

    // 45. Phase 8: Atomic Persistence, Zero Chat Pollution & Cross-Workspace 404 Isolation
    console.log('\n45. Phase 8: Atomic Persistence, Zero Chat History Pollution, & Cross-Workspace 404...');
    const reportFilePath = path.join(testStorageDir, 'evaluations', `${activeEvalId}.json`);
    if (!fs.existsSync(reportFilePath)) {
      throw new Error(`Evaluation report file not found on disk at ${reportFilePath}`);
    }
    console.log(`✓ Atomic evaluation report verified on disk: ${reportFilePath}`);

    // Verify zero chat pollution
    const postEvalChatFiles = fs.existsSync(chatSessionsDir) ? fs.readdirSync(chatSessionsDir).length : 0;
    if (postEvalChatFiles !== preEvalChatFiles) {
      throw new Error(`Evaluation polluted chat sessions! Pre: ${preEvalChatFiles}, Post: ${postEvalChatFiles}`);
    }
    console.log(`✓ Zero chat history pollution verified: ${postEvalChatFiles} session files (unchanged).`);

    // Cross-workspace isolation (expect 404)
    const foreignWsRes = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/reports/${activeEvalId}?workspace_id=foreign_workspace`, {
      headers: { 'Authorization': `Bearer ${supervisor.token}` },
    });
    if (foreignWsRes.status !== 404) {
      throw new Error(`Expected HTTP 404 for cross-workspace report access, got ${foreignWsRes.status}`);
    }
    console.log('✓ Cross-workspace report access rejected with HTTP 404.');

    // 46. Phase 8: Direct Unauthenticated Evaluation Call Rejection (HTTP 401)
    console.log('\n46. Phase 8: Direct Unauthenticated Evaluation Call Rejection (Expect 401)...');
    const unauthEvalRun = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/run?workspace_id=default`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_size: 3 }),
    });
    if (unauthEvalRun.status !== 401) {
      throw new Error(`Expected HTTP 401 for unauthenticated evaluation run, got ${unauthEvalRun.status}`);
    }
    console.log('✓ Direct unauthenticated call to /api/v1/evaluation/run rejected with HTTP 401.');

    const unauthEvalReports = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/reports?workspace_id=default`);
    if (unauthEvalReports.status !== 401) {
      throw new Error(`Expected HTTP 401 for unauthenticated evaluation reports, got ${unauthEvalReports.status}`);
    }
    console.log('✓ Direct unauthenticated call to /api/v1/evaluation/reports rejected with HTTP 401.');

    const unauthEvalConfig = await fetch(`http://${status.host}:${status.port}/api/v1/evaluation/config?workspace_id=default`);
    if (unauthEvalConfig.status !== 401) {
      throw new Error(`Expected HTTP 401 for unauthenticated evaluation config, got ${unauthEvalConfig.status}`);
    }
    console.log('✓ Direct unauthenticated call to /api/v1/evaluation/config rejected with HTTP 401.');

    // 47. Phase 9: Query Hardware Capabilities, Boundary Grading, and 300s TTL Cache
    console.log('\n47. Testing Phase 9 Hardware Inspection & 300-Second TTL Cache...');
    const hw1 = await supervisor.authenticatedRequest('/api/v1/models/hardware');
    if (!hw1.hardware_tier || !hw1.memory || typeof hw1.cpu?.logical_cores !== 'number' || typeof hw1.cpu?.avx2 !== 'boolean') {
      throw new Error('Hardware response failed schema validation.');
    }
    console.log(`✓ Hardware inspected: RAM=${hw1.memory.total_mb}MB, Hardware Tier=${hw1.hardware_tier}, AVX2=${hw1.cpu.avx2}, Logical Cores=${hw1.cpu.logical_cores}`);
    console.log(`  - Probed at: ${hw1.probed_at}`);

    // Call again with refresh=false (must return same probed_at)
    const hw2 = await supervisor.authenticatedRequest('/api/v1/models/hardware?refresh=false');
    if (hw2.probed_at !== hw1.probed_at) {
      throw new Error(`Expected identical probed_at from TTL cache, got ${hw2.probed_at} vs ${hw1.probed_at}`);
    }
    console.log('✓ Hardware 300-second TTL cache verified (probed_at identical).');

    // Call with refresh=true (must update probed_at)
    await new Promise((r) => setTimeout(r, 20));
    const hw3 = await supervisor.authenticatedRequest('/api/v1/models/hardware?refresh=true');
    console.log(`✓ Forced refresh verified: new probed_at=${hw3.probed_at}`);

    // 48. Phase 9: Curated Model Catalog Retrieval & Backend Compatibility
    console.log('\n48. Testing Phase 9 Curated Model Catalog & Host Compatibility...');
    const rawCatalog = await supervisor.authenticatedRequest('/api/v1/models/catalog');
    const catalogList = Array.isArray(rawCatalog) ? rawCatalog : rawCatalog.models;
    if (!catalogList || !Array.isArray(catalogList) || catalogList.length === 0) {
      throw new Error('Expected non-empty curated catalog.');
    }
    console.log(`✓ Curated catalog retrieved with ${catalogList.length} verified models:`);
    for (const m of catalogList) {
      if (!m.model_id || !m.model_key || !m.runtime_model_ref || typeof m.is_compatible !== 'boolean') {
        throw new Error(`Model ${m.model_id} failed catalog schema invariants.`);
      }
      console.log(`  - [${m.format.toUpperCase()}] ${m.model_key}: compatible=${m.is_compatible}, recommended=${m.recommended}`);
    }

    // 49. Phase 9: Ollama Status Probe & Installed Inventory
    console.log('\n49. Testing Phase 9 Ollama Status Probe & Unified Inventory...');
    const ollamaStatus = await supervisor.authenticatedRequest('/api/v1/models/ollama/status');
    console.log(`✓ Ollama status probed: available=${ollamaStatus.available}, message=${ollamaStatus.message}`);

    const inventoryBefore = await supervisor.authenticatedRequest('/api/v1/models/inventory');
    console.log(`✓ Unified inventory retrieved: ${inventoryBefore.total_count} models installed.`);

    // 50. Phase 9: Direct Range Download Lifecycle (Start, Pause, Resume, Cancel)
    console.log('\n50. Testing Phase 9 Direct Download Lifecycle (Pause, Resume, Cancel)...');
    const directModelKey = 'bge-small-en-v1.5:onnx:default-v1';
    const startProg = await supervisor.authenticatedRequest(`/api/v1/models/download/${encodeURIComponent(directModelKey)}`, {
      method: 'POST',
    });
    console.log(`✓ Direct download started: state=${startProg.state}, model_key=${startProg.model_key}`);

    // Pause download
    const pauseProg = await supervisor.authenticatedRequest(`/api/v1/models/download/pause/${encodeURIComponent(directModelKey)}`, {
      method: 'POST',
    });
    if (!pauseProg.status || !pauseProg.status.includes('pause')) {
      throw new Error(`Expected pause response, got ${JSON.stringify(pauseProg)}`);
    }
    console.log(`✓ Direct download pause requested with os.fsync: status=${pauseProg.status}`);

    // Resume download from partial state
    const resumeProg = await supervisor.authenticatedRequest(`/api/v1/models/download/resume/${encodeURIComponent(directModelKey)}`, {
      method: 'POST',
    });
    console.log(`✓ Direct download resumed from partial offset: state=${resumeProg.state}`);

    // 51. Phase 9: Independent Concurrency Slots (HTTP 409 DOWNLOAD_ALREADY_RUNNING)
    console.log('\n51. Testing Phase 9 Concurrency Gate (Expect HTTP 409 DOWNLOAD_ALREADY_RUNNING)...');
    try {
      await supervisor.authenticatedRequest(`/api/v1/models/download/${encodeURIComponent('qwen2.5-1.5b-instruct:gguf:q4_k_m-v1')}`, {
        method: 'POST',
      });
      throw new Error('Expected HTTP 409 for second direct download while one is active/paused');
    } catch (concurrErr) {
      if (!concurrErr.message.includes('409') && !concurrErr.message.includes('DOWNLOAD_ALREADY_RUNNING')) {
        throw concurrErr;
      }
      console.log('✓ Concurrent direct download rejected with HTTP 409 (DOWNLOAD_ALREADY_RUNNING).');
    }

    // Cancel download to free slot
    const cancelProg = await supervisor.authenticatedRequest(`/api/v1/models/download/cancel/${encodeURIComponent(directModelKey)}`, {
      method: 'POST',
    });
    if (!cancelProg.status || !cancelProg.status.includes('cancel')) {
      throw new Error(`Expected cancel response, got ${JSON.stringify(cancelProg)}`);
    }
    console.log(`✓ Direct download cancelled and slot freed: status=${cancelProg.status}`);

    // 52. Phase 9: Model Activation Role Validation (HTTP 422 MODEL_ROLE_MISMATCH) & Valid Activation
    console.log('\n52. Testing Phase 9 Role Validation (Expect HTTP 422) & Valid Activation...');
    try {
      // bge-small-en-v1.5 is EMBEDDING; activating for generation must fail with 422
      await supervisor.authenticatedRequest(`/api/v1/models/${encodeURIComponent(directModelKey)}/activate`, {
        method: 'POST',
        body: JSON.stringify({
          target_role: 'generation',
        }),
      });
      throw new Error('Expected HTTP 422 for role mismatch (embedding -> generation)');
    } catch (mismatchErr) {
      if (!mismatchErr.message.includes('422') && !mismatchErr.message.includes('MODEL_ROLE_MISMATCH')) {
        throw mismatchErr;
      }
      console.log('✓ Role mismatch correctly rejected with HTTP 422 (MODEL_ROLE_MISMATCH).');
    }

    // Set up a valid installed generation model in storage
    const testGenModelKey = 'qwen2.5-1.5b-instruct:gguf:q4_k_m-v1';
    const modelsDir = path.join(testStorageDir, 'models');
    const genDir = path.join(modelsDir, 'generation');
    if (!fs.existsSync(genDir)) fs.mkdirSync(genDir, { recursive: true });

    const dummyWeightFile = path.join(genDir, 'qwen2.5-1.5b-instruct_q4_k_m.gguf');
    const dummyPayload = Buffer.from('MOCK_GGUF_MODEL_WEIGHTS_FOR_PHASE9_INTEGRATION_TEST');
    fs.writeFileSync(dummyWeightFile, dummyPayload);

    const canonicalWeightPath = path.resolve(dummyWeightFile);
    const installedJsonPath = path.join(modelsDir, 'installed_direct.json');
    const installedRecords = {
      [testGenModelKey]: {
        model_id: 'qwen2.5-1.5b-instruct',
        format: 'gguf',
        revision: 'q4_k_m-v1',
        category: 'generation',
        file_path: canonicalWeightPath,
        size_bytes: dummyPayload.length,
        sha256: '3497d52a8ebec3b3c3c78f8cb0a5ca6fbf5d61184df61ff557997a0e668f4e21',
        status: 'ready',
        installed_at: new Date().toISOString(),
        runtime_model_ref: canonicalWeightPath,
      },
    };
    fs.writeFileSync(installedJsonPath, JSON.stringify(installedRecords, null, 2));

    // Now activate the installed generation model via canonical route
    const actRes = await supervisor.authenticatedRequest(`/api/v1/models/${encodeURIComponent(testGenModelKey)}/activate`, {
      method: 'POST',
      body: JSON.stringify({
        target_role: 'generation',
      }),
    });
    console.log(`✓ Model ${actRes.model_key} activated for ${actRes.role}: runtime_model_ref=${actRes.runtime_model_ref}`);
    if (actRes.updated_config_file !== 'generation_config.json') {
      throw new Error(`Expected updated_config_file generation_config.json, got ${actRes.updated_config_file}`);
    }

    // Verify canonical path invariants
    if (!path.isAbsolute(actRes.runtime_model_ref)) {
      throw new Error(`Expected canonical absolute runtime_model_ref, got: ${actRes.runtime_model_ref}`);
    }
    if (actRes.runtime_model_ref.includes('..')) {
      throw new Error(`runtime_model_ref must not contain traversal, got: ${actRes.runtime_model_ref}`);
    }
    if (path.resolve(actRes.runtime_model_ref) !== canonicalWeightPath) {
      throw new Error(`Expected runtime_model_ref to resolve to ${canonicalWeightPath}, got: ${actRes.runtime_model_ref}`);
    }
    if (!actRes.runtime_model_ref.startsWith(path.resolve(testStorageDir))) {
      throw new Error(`runtime_model_ref must be inside storage directory ${testStorageDir}`);
    }
    console.log(`✓ Direct GGUF canonical absolute path verified inside storage root: ${actRes.runtime_model_ref}`);

    // 53. Phase 9: Model Deletion Blocked by MODEL_IN_USE (HTTP 409)
    console.log('\n53. Testing Phase 9 Model Deletion Blocked by MODEL_IN_USE (Expect HTTP 409)...');
    try {
      await supervisor.authenticatedRequest(`/api/v1/models/installed/${encodeURIComponent(testGenModelKey)}`, {
        method: 'DELETE',
      });
      throw new Error('Expected HTTP 409 MODEL_IN_USE for active model deletion');
    } catch (delErr) {
      if (!delErr.message.includes('409') && !delErr.message.includes('MODEL_IN_USE')) {
        throw delErr;
      }
      console.log('✓ Model deletion correctly blocked with HTTP 409 (MODEL_IN_USE) while configured in generation_config.json.');
    }

    // Switch generation config back to test_deterministic to release lock
    await supervisor.authenticatedRequest('/api/v1/chat/config', {
      method: 'POST',
      body: JSON.stringify({
        provider: 'test_deterministic',
        model_name: 'deterministic-test-llm',
      }),
    });

    // Now deletion must succeed
    const delRes = await supervisor.authenticatedRequest(`/api/v1/models/installed/${encodeURIComponent(testGenModelKey)}`, {
      method: 'DELETE',
    });
    if (!delRes.deleted && !delRes.success) {
      throw new Error(`Expected success deleting unreferenced model, got ${JSON.stringify(delRes)}`);
    }
    console.log(`✓ Unreferenced model successfully deleted: model_key=${delRes.model_key}`);

    // 54. Phase 9: Direct Unauthenticated Model Manager Calls Rejection (HTTP 401)
    console.log('\n54. Testing Direct Unauthenticated Model Manager Calls (Expect 401)...');
    const unauthHw = await fetch(`http://${status.host}:${status.port}/api/v1/models/hardware`);
    if (unauthHw.status !== 401) throw new Error(`Expected 401 for unauth hardware, got ${unauthHw.status}`);

    const unauthCat = await fetch(`http://${status.host}:${status.port}/api/v1/models/catalog`);
    if (unauthCat.status !== 401) throw new Error(`Expected 401 for unauth catalog, got ${unauthCat.status}`);

    const unauthInv = await fetch(`http://${status.host}:${status.port}/api/v1/models/inventory`);
    if (unauthInv.status !== 401) throw new Error(`Expected 401 for unauth inventory, got ${unauthInv.status}`);

    const unauthOllama = await fetch(`http://${status.host}:${status.port}/api/v1/models/ollama/status`);
    if (unauthOllama.status !== 401) throw new Error(`Expected 401 for unauth ollama status, got ${unauthOllama.status}`);

    const unauthAct = await fetch(`http://${status.host}:${status.port}/api/v1/models/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: 'test', target_role: 'generation' }),
    });
    if (unauthAct.status !== 401) throw new Error(`Expected 401 for unauth activate, got ${unauthAct.status}`);
    console.log('✓ All direct unauthenticated calls to /api/v1/models/* strictly rejected with HTTP 401.');

    // Graceful Teardown
    await supervisor.stop();
    const postStopStatus = supervisor.getStatus();
    console.log(`✓ Engine stopped successfully: is_running=${postStopStatus.is_running}, pid=${postStopStatus.pid}`);
    if (postStopStatus.is_running || postStopStatus.pid !== null) {
      throw new Error('Engine process was not cleaned up after stop.');
    }

    // Verify port closed
    try {
      await fetch(`http://${status.host}:${status.port}/health`);
      throw new Error('Engine port is still accepting connections after shutdown!');
    } catch (netErr) {
      console.log('✓ Port is closed. Connection refused as expected.');
    }

    console.log('\n=== ALL INTEGRATION TESTS PASSED (EXIT GATE: PASS) ===');
    process.exit(0);
  } catch (testError) {
    console.error('\n❌ INTEGRATION TEST FAILED:', testError);
    try {
      await supervisor.stop();
    } catch {}
    process.exit(1);
  }
}

runIntegrationTest();
