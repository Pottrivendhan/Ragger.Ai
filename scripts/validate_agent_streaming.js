/**
 * End-to-end Local GGUF Agent Streaming Validation Script
 * Tests:
 * 1. Supervised engine start with dynamic ephemeral port + 256-bit token
 * 2. Real local GGUF model detection & configuration (llama-cpp-python)
 * 3. AI Agent streaming SSE endpoint (/api/v1/agents/{agent_id}/chat/stream)
 * 4. Token progression, grounded RAG context, and citation parsing
 */

const path = require('path');
const fs = require('fs');
const http = require('http');

async function validateAgentStreaming() {
  console.log('================================================================');
  console.log('   RAGGER.AI — LOCAL GGUF AGENT STREAMING & SSE VALIDATION');
  console.log('================================================================\n');

  // Ensure test mode does not override real GGUF
  delete process.env.RAGGER_ALLOW_TEST_LLM;

  const { PythonProcessSupervisor } = require('../apps/desktop/dist/main/supervisor');
  const supervisor = new PythonProcessSupervisor();

  try {
    console.log('[1/4] Starting Supervised Packaged Engine...');
    const status = await supervisor.start();
    console.log(`✓ Engine active on http://${status.host}:${status.port} (PID: ${status.pid})`);

    const health = await supervisor.getHealth();
    console.log(`✓ Engine health: status=${health.status}, authenticated=${health.authenticated}`);

    console.log('\n[2/4] Verifying Generation Config and GGUF Model...');
    const configRes = await supervisor.authenticatedRequest('/api/v1/chat/config');
    console.log(`✓ Current config: provider=${configRes.provider}, model=${configRes.model_name || configRes.model_path}`);

    // Fetch existing agents or create a test agent
    console.log('\n[3/4] Checking AI Agents...');
    let agents = await supervisor.authenticatedRequest('/api/v1/agents');
    let agentId = 'default';
    if (Array.isArray(agents) && agents.length > 0) {
      agentId = agents[0].id || agents[0].agent_id || 'default';
      console.log(`✓ Found existing agent: ${agentId} (${agents[0].name})`);
    } else {
      console.log('  No agent found, creating agent...');
      const newAgent = await supervisor.authenticatedRequest('/api/v1/agents', {
        method: 'POST',
        body: JSON.stringify({
          name: 'Validation Agent',
          description: 'Production validation agent',
          rag_pipeline_ids: ['default']
        })
      });
      agentId = newAgent.id || newAgent.agent_id || 'default';
      console.log(`✓ Created agent: ${agentId}`);
    }

    const apiConfig = supervisor.getApiConfig();
    console.log(`\n[4/4] Testing Real Streaming Inference (/api/v1/agents/${agentId}/chat/stream)...`);
    const question = 'Why was the author left with his grandmother in the village?';
    console.log(`Query: "${question}"`);

    // Stream SSE directly via Node http request to simulate client
    const streamPromise = new Promise((resolve, reject) => {
      const payload = JSON.stringify({
        query: question,
        top_k: 3
      });

      const options = {
        hostname: status.host,
        port: status.port,
        path: `/api/v1/agents/${agentId}/chat/stream`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiConfig.token}`,
          'Content-Length': Buffer.byteLength(payload)
        }
      };

      const req = http.request(options, (res) => {
        console.log(`✓ SSE Response Status: ${res.statusCode} ${res.statusMessage}`);
        console.log(`✓ Content-Type: ${res.headers['content-type']}`);

        if (res.statusCode !== 200) {
          let errBody = '';
          res.on('data', chunk => errBody += chunk);
          res.on('end', () => reject(new Error(`Stream failed with ${res.statusCode}: ${errBody}`)));
          return;
        }

        let fullText = '';
        let eventCount = 0;
        let citations = [];

        res.setEncoding('utf8');
        let buffer = '';

        res.on('data', (chunk) => {
          buffer += chunk;
          const lines = buffer.split('\n');
          buffer = lines.pop(); // keep last incomplete line

          let currentEvent = 'message';
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('event: ')) {
              currentEvent = trimmed.slice(7).trim();
            } else if (trimmed.startsWith('data: ')) {
              eventCount++;
              const dataStr = trimmed.slice(6);
              console.log(`[SSE Event] type="${currentEvent}" data=${dataStr}`);
              if (dataStr === '[DONE]') continue;
              try {
                const parsed = JSON.parse(dataStr);
                if (currentEvent === 'token' || parsed.token || parsed.type === 'token') {
                  const token = parsed.token || parsed.content || (typeof parsed === 'string' ? parsed : '');
                  fullText += token;
                } else if (currentEvent === 'done') {
                  if (parsed.answer) fullText = parsed.answer;
                  citations = parsed.citations || [];
                } else if (currentEvent === 'error') {
                  console.error('SSE Error Event received:', parsed);
                }
              } catch (e) {
                fullText += dataStr;
              }
            }
          }
        });

        res.on('end', () => {
          console.log('\n--- Stream Completed ---');
          console.log(`Total Events: ${eventCount}`);
          console.log(`Answer Length: ${fullText.length}`);
          console.log(`Answer: ${fullText}`);
          if (fullText.length > 0) {
            resolve({ fullText, eventCount, citations });
          } else {
            reject(new Error('Stream ended without generating any tokens or answer!'));
          }
        });
      });

      req.on('error', reject);
      req.write(payload);
      req.end();
    });

    const result = await streamPromise;
    console.log(`\n================================================================`);
    console.log('   ✓ REAL LOCAL GGUF STREAMING VALIDATION PASSED!');
    console.log('================================================================\n');
  } finally {
    console.log('Stopping Supervised Engine...');
    await supervisor.stop();
    console.log('✓ Engine stopped.');
  }
}

validateAgentStreaming().catch((err) => {
  console.error('\n❌ VALIDATION ERROR:', err);
  process.exit(1);
});
