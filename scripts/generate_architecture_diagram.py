#!/usr/bin/env python3
"""
Generate the AI Scribe Enterprise architecture diagram.
Output: docs/images/architecture_diagram.png

Portrait layout (full-page vertical):
  §1  LangGraph Pipeline        — horizontal row at top
  §2  MCP Engine Registry       — tree fanning out below
  §3  Supporting Components     — 2×2 grid
  §4  API + Web UI              — horizontal row at bottom

Run: source .venv/bin/activate && python3 scripts/generate_architecture_diagram.py
"""
from pathlib import Path
import graphviz

# ── palette ──────────────────────────────────────────────────────────────────
PIPE_FILL    = '#1E1B4B'
PIPE_DARK    = '#312E81'
MCP_FILL     = '#00B27A'
EHR_FILL     = '#D97706'
FUTURE_FILL  = '#E2E8F0'
FUTURE_FG    = '#64748B'
STATE_FILL   = '#EEF2FF'
WEB_FILL     = '#0369A1'
WEB_BG       = '#DBEAFE'
PIPE_BG      = '#EEF2FF'
MCP_BG       = '#F0FDF4'
SUPP_BG      = '#FFFBEB'
GRAY_BG      = '#F8FAFC'
WHITE        = 'white'
RED_PILL     = '#FEF2F2'
RED_FG       = '#991B1B'
GREEN_PILL   = '#F0FDF4'
GREEN_FG     = '#166534'


# ── helpers ──────────────────────────────────────────────────────────────────
def pipe_node(g, nid, title, sub='', w='2.0'):
    label = (f'<<b>{title}</b>'
             + (f'<br/><font point-size="8">{sub}</font>' if sub else '')
             + '>')
    g.node(nid, label,
           shape='box', style='filled,rounded',
           fillcolor=PIPE_FILL, fontcolor=WHITE,
           fontsize='10', fontname='Helvetica-Bold',
           width=w, height='0.52', margin='0.10,0.07')


def router(g, nid, lbl):
    g.node(nid, f'<<font point-size="8">{lbl}</font>>',
           shape='diamond', style='filled',
           fillcolor=PIPE_DARK, fontcolor=WHITE,
           width='0.85', height='0.52')


def mcp_node(g, nid, title, lines, future=False, ehr=False, w='2.6'):
    body = ''.join(f'<br/><font point-size="8">{l}</font>' for l in lines)
    label = f'<<b>{title}</b>{body}>'
    fill  = FUTURE_FILL if future else (EHR_FILL if ehr else MCP_FILL)
    fg    = FUTURE_FG   if future else WHITE
    style = 'filled,rounded,dashed' if future else 'filled,rounded'
    g.node(nid, label, shape='box', style=style,
           fillcolor=fill, fontcolor=fg, color=(FUTURE_FG if future else fill),
           fontsize='9', fontname='Helvetica', width=w, margin='0.12,0.07')


def supp_node(g, nid, title, lines, w='3.1'):
    body = ''.join(f'<br/><font point-size="8">{l}</font>' for l in lines)
    g.node(nid, f'<<b>{title}</b>{body}>',
           shape='box', style='filled,rounded',
           fillcolor=SUPP_BG, fontcolor='#1C1917',
           fontsize='9', fontname='Helvetica', width=w, margin='0.12,0.07')


# ── root graph ───────────────────────────────────────────────────────────────
d = graphviz.Digraph('ai_scribe', engine='dot')
d.attr(rankdir='TB', bgcolor=WHITE, compound='true',
       nodesep='0.40', ranksep='0.75',
       fontname='Helvetica', fontsize='12',
       size='14,20!', ratio='fill', dpi='150',   # portrait — fill full page
       pad='0.5')


# ════════════════════════════════════════════════════════════════════════════
# §1  LangGraph Pipeline
# ════════════════════════════════════════════════════════════════════════════
with d.subgraph(name='cluster_pipe') as p:
    p.attr(label='§1  LANGGRAPH PIPELINE  (orchestrator/)',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=PIPE_BG,
           color=PIPE_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    # All 8 pipeline nodes on a single rank → render left-to-right
    with p.subgraph() as row:
        row.attr(rank='same')
        pipe_node(row, 'ctx',   'CONTEXT',    'StubEHRServer<br/>patient_context.yaml')
        pipe_node(row, 'cap',   'CAPTURE',    'audio_segments<br/>future: VAD + denoise')
        pipe_node(row, 'tx',    'TRANSCRIBE', 'WhisperX large-v3<br/>faster-whisper + pyannote')
        router(row, 'asr_r', 'asr_router')
        pipe_node(row, 'note',  'NOTE',       'OllamaServer<br/>qwen2.5:14b', w='2.2')
        router(row, 'llm_r', 'llm_router')
        pipe_node(row, 'rev',   'REVIEW',     'HITL Review<br/>auto-approve stub')
        pipe_node(row, 'del',   'DELIVERY',   'EHR push<br/>clipboard stub')

    p.edge('ctx',   'cap',    label='context_packet', fontsize='8')
    p.edge('cap',   'tx',     label='audio_segments',  fontsize='8')
    p.edge('tx',    'asr_r')
    p.edge('asr_r', 'note',   label='conf≥0.40',        fontsize='8')
    p.edge('note',  'llm_r')
    p.edge('llm_r', 'rev',    label='conf≥0.50',         fontsize='8')
    p.edge('rev',   'del',    label='approved',            fontsize='8')

    # EncounterState band — row immediately below pipeline
    with p.subgraph() as row2:
        row2.attr(rank='same')
        p.node('estate',
               '<<b>EncounterState (Pydantic v2)</b> — shared across all nodes<br/>'
               '<font point-size="8">'
               'encounter_id  ·  provider_id  ·  recording_mode (AMBIENT | DICTATION)  ·  '
               'context_packet  ·  audio_segments  ·  transcript  ·  '
               'generated_note  ·  final_note  ·  delivery_result  ·  '
               'errors[]  ·  EncounterMetrics (timing, ASR conf, note conf)</font>>',
               shape='rectangle', style='filled',
               fillcolor=STATE_FILL, fontcolor=PIPE_FILL,
               fontsize='9', fontname='Helvetica',
               width='15.5', height='0.55')

    p.edge('ctx', 'estate', style='invis')   # keeps state band below pipeline row


# ════════════════════════════════════════════════════════════════════════════
# §2  MCP Engine Registry & Servers
# ════════════════════════════════════════════════════════════════════════════
with d.subgraph(name='cluster_mcp') as m:
    m.attr(label='§2  MCP ENGINE REGISTRY & SERVERS  (mcp_servers/)',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=MCP_BG,
           color=MCP_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    # Registry hub — centred
    m.node('reg',
           '<<b>EngineRegistry</b><br/>'
           '<font point-size="8">mcp_servers/registry.py<br/>'
           'get_asr() · get_llm() · get_ehr()<br/>'
           'get_asr_for_provider(provider_id, use_lora=False)<br/>'
           'get_with_failover() · health_check_all()<br/>'
           'Config: config/engines.yaml</font>>',
           shape='box', style='filled,rounded',
           fillcolor=MCP_FILL, fontcolor=WHITE,
           fontsize='10', fontname='Helvetica-Bold', width='3.4')

    # All four server families on the same rank
    with m.subgraph() as row_srv:
        row_srv.attr(rank='same')

        with m.subgraph(name='cluster_asr') as a:
            a.attr(label='ASR Servers', style='filled', fillcolor='#DCFCE7',
                   color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mcp_node(a, 'asr_wx',
                     '[DEFAULT] WhisperXServer',
                     ['faster-whisper (CTranslate2)',
                      'pyannote 3.1 · wav2vec2 alignment',
                      'Model: whisper-large-v3 · CUDA',
                      'VRAM peak 10-12 GB (A10G 23 GB)'])
            mcp_node(a, 'asr_lora',
                     '[OPT-IN] WhisperXLoraServer',
                     ['peft LoRA adapter',
                      'Requires ≥30 min verbatim audio',
                      'Ambient: -11-13% WER improvement'],
                     future=True)

        with m.subgraph(name='cluster_llm') as l:
            l.attr(label='LLM Servers', style='filled', fillcolor='#DCFCE7',
                   color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mcp_node(l, 'llm_ol',
                     '[DEFAULT] OllamaServer',
                     ['OpenAI-compat · localhost:11434/v1',
                      'qwen2.5:14b (Apache 2.0) · ~8 GB VRAM',
                      'keep_alive=0 (VRAM sharing)',
                      'note_generation / coding / summary'])
            mcp_node(l, 'llm_fut',
                     '[FUTURE] vLLM / Claude / OpenAI',
                     ['Same LLMEngine interface',
                      'Zero pipeline code changes'],
                     future=True)

        with m.subgraph(name='cluster_ehr') as e:
            e.attr(label='EHR Adapters', style='filled', fillcolor='#FEF9C3',
                   color=EHR_FILL, fontname='Helvetica-Bold', fontsize='10')
            mcp_node(e, 'ehr_stub',
                     '[DEFAULT] StubEHRServer',
                     ['Reads patient_context.yaml',
                      'get_patient() · get_problem_list()',
                      'get_medications() · get_allergies()',
                      'get_recent_labs() · push_note()'],
                     ehr=True)
            mcp_node(e, 'ehr_fut',
                     '[FUTURE] FHIRServer (R4) / HL7v2',
                     ['Same EHRAdapter interface',
                      'Browser extension bridge'],
                     future=True)

        with m.subgraph(name='cluster_data') as ds:
            ds.attr(label='Data Servers', style='filled', fillcolor='#DCFCE7',
                    color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mcp_node(ds, 'tpl_srv',
                     'TemplateServer',
                     ['config/templates/*.yaml',
                      'get_template(specialty, visit_type)',
                      'ortho_follow_up · soap_default · …'])
            mcp_node(ds, 'dict_srv',
                     'MedicalDictServer',
                     ['get_hotwords(specialty, max_terms)',
                      '98K OpenMedSpel base dictionary',
                      'Specialty: ortho · cardiology · …'])

    m.edge('reg', 'asr_wx',   label='ASR',  fontsize='8', lhead='cluster_asr')
    m.edge('reg', 'asr_lora', fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'llm_ol',   label='LLM',  fontsize='8', lhead='cluster_llm')
    m.edge('reg', 'llm_fut',  fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'ehr_stub', label='EHR',  fontsize='8', lhead='cluster_ehr')
    m.edge('reg', 'ehr_fut',  fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'tpl_srv',  fontsize='8')
    m.edge('reg', 'dict_srv', fontsize='8')


# ════════════════════════════════════════════════════════════════════════════
# §3  Supporting Components
# ════════════════════════════════════════════════════════════════════════════
with d.subgraph(name='cluster_support') as s:
    s.attr(label='§3  SUPPORTING COMPONENTS',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=SUPP_BG,
           color=EHR_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    # Row 1: post-processor + provider profiles
    with s.subgraph() as row_s1:
        row_s1.attr(rank='same')
        supp_node(s, 'postproc', 'Post-Processor  (postprocessor/)',
                  ['medasr_postprocessor.py · 12-stage rule-based pipeline',
                   'medical_wordlist.txt · 98K OpenMedSpel (GPL)',
                   'Called by: transcribe_node._apply_postprocessor()',
                   'CTC stutter pairs -90% · char stutters -99%',
                   'Medical term correction -87% · artifact removal'])

        supp_node(s, 'prov_mgr', 'Provider Profile System  (config/providers/)',
                  ['config/providers/{provider_id}.yaml per provider',
                   'style_directives · custom_vocabulary (22 terms)',
                   'asr_overrides · template_routing · quality_history',
                   'ProviderManager.resolve_template(provider_id, visit_type)',
                   'Dr. Faraz Rahman: 10 directives, 22 vocab, 4 routing entries'])

    # Row 2: template system + quality framework
    with s.subgraph() as row_s2:
        row_s2.attr(rank='same')
        supp_node(s, 'tpl_sys', 'Template System  (config/templates/*.yaml)',
                  ['ortho_follow_up (6 sections) · dictation short follow-ups',
                   'ortho_initial_eval (12 sections) · ambient initial encounters',
                   'soap_default · specialty-specific templates',
                   'Each: sections (label, required, prompt_hint), formatting',
                   'Routing: provider_id + visit_type → template_id → YAML'])

        supp_node(s, 'qual_fw', 'Quality Evaluation  (quality/)',
                  ['evaluator.py · LLM-as-judge: always use llama3.1:latest as judge',
                   'fact_extractor.py · meds / diagnoses / exam findings',
                   'Dimensions: accuracy · completeness · no_hallucination',
                   '            structure · language  (each 1–5, weighted)',
                   'report.py → quality_report_v{N}.md per version'])

    s.node('qual_trend',
           '<<b>Quality Progress  (v1 → v6)</b><br/>'
           '<font point-size="8">'
           'v1  Session 4  basic pipeline         ~3.50 / 5.0<br/>'
           'v2  Session 5  templates + dicts        4.30 / 5.0<br/>'
           'v3  Session 7  EHR context              4.34 / 5.0<br/>'
           'v4  Session 8  provider profiles        4.38 / 5.0<br/>'
           'v5  Session 10 ASR knobs wired          4.35 / 5.0<br/>'
           '<b>v6  Model upgrade  qwen2.5:14b      4.44 / 5.0  ✓ current</b><br/>'
           '<font point-size="7">Judge: llama3.1:latest · 22 gold-standard samples</font>'
           '</font>>',
           shape='box', style='filled,rounded',
           fillcolor=GRAY_BG, fontcolor='#1C1917',
           fontsize='9', fontname='Helvetica', width='5.8')

    s.edge('prov_mgr', 'tpl_sys',    label='resolves', fontsize='8')
    s.edge('qual_fw',  'qual_trend', fontsize='8')


# ════════════════════════════════════════════════════════════════════════════
# §4  API + Web UI
# ════════════════════════════════════════════════════════════════════════════
with d.subgraph(name='cluster_ui') as u:
    u.attr(label='§4  API + WEB UI',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=WEB_BG,
           color=WEB_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    with u.subgraph() as row_ui:
        row_ui.attr(rank='same')

        u.node('api',
               '<<b>FastAPI Backend  (api/)</b><br/>'
               '<font point-size="8">'
               '<b>Encounters:</b>  POST /encounters  ·  POST /{id}/upload<br/>'
               'GET /{id}  ·  GET /{id}/transcript  ·  GET /{id}/note<br/>'
               'GET /{id}/audio  ·  GET /{id}/comparison  ·  GET /{id}/quality<br/>'
               '<b>Providers:</b>  GET /providers  ·  GET /{id}/quality-trend<br/>'
               '<b>Quality:</b>  GET /quality/aggregate · /samples · /dimensions<br/>'
               '<b>WebSocket:</b>  WS /ws/encounters/{id} — real-time progress<br/>'
               '<b>Data source:</b>  output/ directory tree (no DB yet)</font>>',
               shape='box', style='filled,rounded',
               fillcolor=WEB_FILL, fontcolor=WHITE,
               fontsize='9', fontname='Helvetica-Bold', width='5.0')

        u.node('web',
               '<<b>Next.js Web App  (client/web/)</b><br/>'
               '<font point-size="8">'
               '<b>Dashboard (/):</b>  KPI cards · quality trend (Recharts) · encounters table<br/>'
               '<b>Samples (/samples):</b>  filterable table (version, mode, score range)<br/>'
               '<b>Sample Detail (/samples/[id])  —  6 tabs:</b><br/>'
               '  Transcript: HTML5 audio player + version picker (v1–v6)<br/>'
               '  Clinical Note: rendered Markdown + version picker<br/>'
               '  Comparison: gold vs generated side-by-side<br/>'
               '  Gold Standard: original gold-standard note<br/>'
               '  Quality Scores: dimension bar chart + fact-check table<br/>'
               '  Compare Versions: dual pickers + LCS line diff (green/red/gray)<br/>'
               '<b>Providers (/providers):</b>  cards with quality badge<br/>'
               '<b>Upload (/upload):</b>  drag-and-drop MP3/WAV + provider selector</font>>',
               shape='box', style='filled,rounded',
               fillcolor=WEB_FILL, fontcolor=WHITE,
               fontsize='9', fontname='Helvetica-Bold', width='5.0')

    u.edge('web', 'api', label='REST calls',    fontsize='8')
    u.edge('api', 'web', label='JSON + WebSocket', fontsize='8', style='dashed')


# ════════════════════════════════════════════════════════════════════════════
# Legend
# ════════════════════════════════════════════════════════════════════════════
with d.subgraph(name='cluster_legend') as leg:
    leg.attr(label='Legend', labelloc='b', labeljust='r',
             style='filled', fillcolor=GRAY_BG,
             color='#CBD5E1', fontname='Helvetica', fontsize='10')
    leg.node('l1', '[DEFAULT]  active implementation — solid border',
             shape='plaintext', fontsize='9')
    leg.node('l2', '[OPT-IN / FUTURE]  planned or stubbed — dashed border',
             shape='plaintext', fontsize='9')
    leg.node('l3', '──►  data flow          - - ►  optional / future path',
             shape='plaintext', fontsize='9')
    leg.edge('l1', 'l2', style='invis')
    leg.edge('l2', 'l3', style='invis')


# ════════════════════════════════════════════════════════════════════════════
# Vertical section ordering  (invisible anchor edges)
# ════════════════════════════════════════════════════════════════════════════
d.edge('estate', 'reg',      style='invis')   # §1 above §2
d.edge('reg',    'postproc', style='invis')   # §2 above §3
d.edge('postproc','api',     style='invis')   # §3 above §4
d.edge('qual_fw', 'api',     style='invis')   # §3 above §4 (second anchor)


# ════════════════════════════════════════════════════════════════════════════
# Cross-section call edges  (pipeline nodes → MCP / support)
# ════════════════════════════════════════════════════════════════════════════
CE = dict(style='dashed', fontsize='8', constraint='false')

d.edge('ctx',  'ehr_stub',  label='get_patient()',          color=EHR_FILL,  **CE)
d.edge('tx',   'asr_wx',    label='transcribe_batch_sync()',color=MCP_FILL,  **CE)
d.edge('tx',   'postproc',  label='_apply_postprocessor()', color=EHR_FILL,  **CE)
d.edge('note', 'llm_ol',    label='generate_sync()',        color=MCP_FILL,  **CE)
d.edge('note', 'tpl_srv',   label='load_template()',        color=MCP_FILL,  **CE)
d.edge('note', 'dict_srv',  label='get_hotwords()',         color=MCP_FILL,  **CE)
d.edge('del',  'ehr_stub',   label='push_note()',            color=EHR_FILL,  **CE)
d.edge('del',  'api',        label='writes output/',         color=WEB_FILL,  **CE)


# ════════════════════════════════════════════════════════════════════════════
# Render
# ════════════════════════════════════════════════════════════════════════════
out_dir = Path('docs/images')
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / 'architecture_diagram'

d.render(filename=str(out_path), format='png', cleanup=True)
print(f'✓  PNG : {out_path}.png')

dot_src = out_dir / 'architecture_diagram.dot'
dot_src.write_text(d.source)
print(f'✓  DOT : {dot_src}')
