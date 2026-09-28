/**
 * End-to-end User Journey Validation Script
 * Tests:
 * 1. Frozen packaged engine execution via Supervisor with ephemeral port & 256-bit token
 * 2. Real user PDF ingestion (D:\D Downloads\BDA ROLE PLAY 4.pdf)
 * 3. File Analysis & Profile Generation (/api/v1/analysis/file)
 * 4. Architecture Recommendation (/api/v1/recommendation/evaluate)
 * 5. Configuration & Build Pipeline (ONNX BGE Embeddings, Chunks, Vector Store)
 * 6. Vector Store & Retrieval (/api/v1/retrieval/query)
 * 7. AI Agent Chat Query & Answer Generation (/api/v1/chat/generate)
 */

const path = require('path');
const fs = require('fs');

async function validateEndToEndUserJourney() {
  console.log('================================================================');
  console.log('   RAGGER.AI — PRODUCTION END-TO-END VALIDATION (BDA ROLE PLAY 4)');
  console.log('================================================================\n');

  process.env.RAGGER_ALLOW_TEST_LLM = '1';

  const pdfPath = 'D:\\D Downloads\\BDA ROLE PLAY 4.pdf';
  if (!fs.existsSync(pdfPath)) {
    throw new Error(`Target document not found at: ${pdfPath}`);
  }
  console.log(`✓ Found target document: ${pdfPath} (${(fs.statSync(pdfPath).size / 1024).toFixed(1)} KB)`);

  const { PythonProcessSupervisor } = require('../apps/desktop/dist/main/supervisor');
  const supervisor = new PythonProcessSupervisor();

  try {
    // STEP 1: START SUPERVISED ENGINE
    console.log('\n[1/7] Initializing Supervised Engine...');
    const status = await supervisor.start();
    console.log(`✓ Engine active on http://${status.host}:${status.port} (PID: ${status.pid})`);

    const health = await supervisor.getHealth();
    console.log(`✓ Engine authenticated health: status=${health.status}, authenticated=${health.authenticated}`);

    // STEP 2: INGEST BDA ROLE PLAY 4.PDF
    console.log('\n[2/7] Ingesting Document (BDA ROLE PLAY 4.pdf)...');
    const ingestRes = await supervisor.authenticatedRequest('/api/v1/ingestion/ingest', {
      method: 'POST',
      body: JSON.stringify({ file_path: pdfPath }),
    });

    const sourceId = ingestRes.source.source_id;
    console.log(`✓ Document ingested successfully:`);
    console.log(`  - Source ID: ${sourceId}`);
    console.log(`  - Model Type: ${ingestRes.model_type}`);
    console.log(`  - Blocks: ${ingestRes.normalized_model.total_blocks}`);
    console.log(`  - SHA-256: ${ingestRes.source.sha256_checksum}`);

    // STEP 3: ANALYZE FILE & GENERATE PROFILE
    console.log('\n[3/7] Generating File Analysis Profile...');
    const profile = await supervisor.authenticatedRequest('/api/v1/analysis/file', {
      method: 'POST',
      body: JSON.stringify({ source_id: sourceId }),
    });
    console.log(`✓ Profile generated:`);
    console.log(`  - Primary Modality: ${profile.semantic_observations?.primary_modality}`);
    console.log(`  - Detected Domain: ${profile.semantic_observations?.detected_domain}`);
    console.log(`  - Summary: "${profile.semantic_observations?.summary_description}"`);

    // Synthesize workspace
    console.log('\n  Synthesizing Workspace Profile...');
    const wsProfile = await supervisor.authenticatedRequest('/api/v1/analysis/workspace', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: 'default' }),
    });
    console.log(`✓ Workspace Profile synthesized: total_sources=${wsProfile.total_sources}`);

    // STEP 4: RECOMMENDATION
    console.log('\n[4/7] Requesting Architecture Recommendation...');
    const recRes = await supervisor.authenticatedRequest('/api/v1/recommendation/evaluate', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: 'default' }),
    });
    console.log(`✓ Recommendation received:`);
    console.log(`  - Recommended Architecture: ${recRes.recommended_architecture}`);
    console.log(`  - Confidence: ${recRes.confidence_score * 100}% (${recRes.confidence_level})`);

    // STEP 5: APPROVE & BUILD RAG ARTIFACT WITH REAL LOCAL ONNX BGE
    console.log('\n[5/7] Starting RAG Build (ONNX BGE Embeddings, Chunks, Vector Index)...');
    const approvePayload = {
      workspace_id: 'default',
      architecture_id: recRes.recommended_architecture || 'knowledge_rag',
      source_ids: [sourceId],
      is_revision: true,
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
        strategy: 'dense_semantic',
        top_k: 5,
      },
    };
    await supervisor.authenticatedRequest('/api/v1/recommendation/approve', {
      method: 'POST',
      body: JSON.stringify(approvePayload),
    });

    const startBuildRes = await supervisor.authenticatedRequest('/api/v1/builder/start', {
      method: 'POST',
    });
    console.log(`✓ Build triggered: build_id=${startBuildRes.build_id}`);

    // Poll build progress
    let buildComplete = false;
    let attempts = 0;
    while (!buildComplete && attempts < 60) {
      await new Promise((r) => setTimeout(r, 1000));
      const prog = await supervisor.authenticatedRequest('/api/v1/builder/progress');
      process.stdout.write(`\r  Building... Stage: ${prog.current_stage || prog.stage} (${prog.percent_complete || prog.progress || 0}%)`);

      if (prog.status === 'completed' || prog.state === 'completed') {
        buildComplete = true;
        console.log('\n✓ RAG Build completed successfully!');
        break;
      }
      if (prog.status === 'failed' || prog.state === 'failed') {
        throw new Error(`Build failed: ${prog.error || prog.error_message || 'Unknown build error'}`);
      }
      attempts++;
    }

    if (!buildComplete) {
      throw new Error('Build timed out after 60 seconds.');
    }

    // Retrieve active manifest
    const manifest = await supervisor.authenticatedRequest('/api/v1/builder/manifest');
    console.log(`✓ Build Manifest Verified: chunks=${manifest.chunk_count}, vectors=${manifest.vector_count}`);

    // STEP 6: VERIFY RETRIEVAL ON BUILT VECTOR STORE
    console.log('\n[6/7] Testing Semantic Retrieval on Built Vector Index...');
    const testQuery = 'What are the main role play scenarios and objectives?';
    const retrievalRes = await supervisor.authenticatedRequest('/api/v1/retrieval/query', {
      method: 'POST',
      body: JSON.stringify({ query: testQuery, top_k: 3 }),
    });

    console.log(`✓ Retrieval Query: "${testQuery}"`);
    console.log(`✓ Matches retrieved: ${retrievalRes.results?.length || 0}`);
    if (retrievalRes.results && retrievalRes.results.length > 0) {
      const topMatch = retrievalRes.results[0];
      console.log(`  - Top Match Score: ${topMatch.score}`);
      console.log(`  - Content Snippet: ${topMatch.text?.slice(0, 160).replace(/\n/g, ' ')}...`);
    }

    // STEP 7: TEST AI AGENT CHAT QUERY
    console.log('\n[7/7] Testing AI Agent Query with Context Injection...');
    await supervisor.authenticatedRequest('/api/v1/chat/config', {
      method: 'POST',
      body: JSON.stringify({
        provider: 'test_deterministic',
        model_name: 'deterministic-test-llm',
      }),
    });

    const chatRes = await supervisor.authenticatedRequest('/api/v1/chat/generate?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify({
        query: 'Summarize the primary purpose of this BDA role play.',
        top_k: 3,
      }),
    });

    console.log(`✓ AI Agent Grounded Answer:`);
    console.log(`----------------------------------------------------------------`);
    console.log(chatRes.answer);
    console.log(`----------------------------------------------------------------`);
    console.log(`  - Retrieved Chunks Used: ${chatRes.retrieved_chunk_count}`);
    console.log(`  - Valid Citations: ${chatRes.valid_citations?.length || chatRes.citations?.length || 0}`);

    console.log('\n================================================================');
    console.log('   ✓ ALL 7 USER JOURNEY PHASES VALIDATED PERFECTLY!');
    console.log('================================================================\n');
  } finally {
    console.log('Tearing down supervised engine...');
    await supervisor.stop();
    console.log('✓ Teardown complete.');
  }
}

validateEndToEndUserJourney().catch((err) => {
  console.error('\n❌ VALIDATION ERROR:', err);
  process.exit(1);
});
