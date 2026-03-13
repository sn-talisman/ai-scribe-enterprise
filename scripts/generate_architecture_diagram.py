#!/usr/bin/env python3
"""
Generate the AI Scribe Enterprise architecture diagram.
Output: docs/images/architecture_diagram.png

Layout strategy (graphviz dot):
  rankdir=TB  →  sections stack top-to-bottom.
  rank='same' nodes within a rank appear side-by-side (L→R).
  Invisible anchor edges (style='invis') control vertical ordering.
"""
from pathlib import Path
import graphviz

# ── palette ─────────────────────────────────────────────────────────────────
PIPE_FILL   = '#1E1B4B'   # deep indigo (pipeline nodes)
PIPE_DARK   = '#312E81'   # darker indigo (routers)
MCP_FILL    = '#00B27A'   # teal/green (active MCP servers)
EHR_FILL    = '#D97706'   # amber (EHR nodes)
FUTURE_FILL = '#E2E8F0'   # light slate (future/stub nodes)
FUTURE_FG   = '#64748B'
STATE_FILL  = '#EEF2FF'   # very light indigo (EncounterState band)
SUPPORT_FILL= '#FEF3C7'   # light amber (supporting components)
WEB_FILL    = '#0369A1'   # deep blue (API / Web)
WEB_BG      = '#E0F2FE'   # light blue background
PIPE_BG     = '#EEF2FF'   # pipeline section bg
MCP_BG      = '#F0FDF4'   # MCP section bg
SUPP_BG     = '#FFFBEB'   # supporting section bg
GRAY_BG     = '#F8FAFC'
WHITE       = 'white'


def pnode(g, nid, title, sub=''):
    """Pipeline node."""
    lbl = f'<<b>{title}</b>' + (f'<br/><font point-size="8">{sub}</font>' if sub else '') + '>'
    g.node(nid, lbl, shape='box', style='filled,rounded',
           fillcolor=PIPE_FILL, fontcolor=WHITE,
           fontsize='10', fontname='Helvetica-Bold',
           width='1.9', height='0.55', margin='0.12,0.08')


def rnode(g, nid, lbl):
    """Router diamond."""
    g.node(nid, f'<<font point-size="8">{lbl}</font>>',
           shape='diamond', style='filled',
           fillcolor=PIPE_DARK, fontcolor=WHITE,
           width='0.9', height='0.55')


def mnode(g, nid, title, lines, future=False, ehr=False):
    """MCP server node."""
    body = ''.join(f'<br/><font point-size="8">{l}</font>' for l in lines)
    lbl  = f'<<b>{title}</b>{body}>'
    fill = FUTURE_FILL if future else (EHR_FILL if ehr else MCP_FILL)
    fg   = FUTURE_FG   if future else WHITE
    brd  = FUTURE_FG   if future else fill
    g.node(nid, lbl, shape='box', style='filled,rounded' + (',dashed' if future else ''),
           fillcolor=fill, fontcolor=fg, color=brd,
           fontsize='9', fontname='Helvetica', width='2.4', margin='0.15,0.08')


def snode(g, nid, title, lines):
    """Supporting component node."""
    body = ''.join(f'<br/><font point-size="8">{l}</font>' for l in lines)
    lbl  = f'<<b>{title}</b>{body}>'
    g.node(nid, lbl, shape='box', style='filled,rounded',
           fillcolor=SUPPORT_FILL, fontcolor='#1C1917',
           fontsize='9', fontname='Helvetica', width='2.7', margin='0.15,0.08')


# ── root graph ──────────────────────────────────────────────────────────────
d = graphviz.Digraph('ai_scribe', engine='dot')
d.attr(rankdir='TB', bgcolor=WHITE, compound='true',
       nodesep='0.45', ranksep='0.9',
       fontname='Helvetica', fontsize='12',
       size='20,13!', dpi='150',
       pad='0.5')

# ────────────────────────────────────────────────────────────────────────────
# §1  LangGraph Pipeline
# ────────────────────────────────────────────────────────────────────────────
with d.subgraph(name='cluster_pipe') as p:
    p.attr(label='§1  LANGGRAPH PIPELINE  (orchestrator/)',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=PIPE_BG,
           color=PIPE_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    # Force all pipeline nodes onto the SAME rank → they render L-to-R
    with p.subgraph() as rank_pipe:
        rank_pipe.attr(rank='same')
        pnode(rank_pipe, 'ctx',  'CONTEXT',   'StubEHRServer → patient_context.yaml')
        pnode(rank_pipe, 'cap',  'CAPTURE',   'Audio segments · future: VAD + noise suppression')
        pnode(rank_pipe, 'tx',   'TRANSCRIBE','WhisperXServer  ·  faster-whisper large-v3')
        rnode(rank_pipe, 'asr_r','asr_router')
        pnode(rank_pipe, 'note', 'NOTE',      'OllamaServer  ·  qwen2.5:14b')
        rnode(rank_pipe, 'llm_r','llm_router')
        pnode(rank_pipe, 'rev',  'REVIEW',    'HITL Review  ·  auto-approve stub')
        pnode(rank_pipe, 'del',  'DELIVERY',  'EHR push  ·  clipboard stub')

    # pipeline edges
    p.edge('ctx',   'cap',   label='context_packet', fontsize='8')
    p.edge('cap',   'tx',    label='audio_segments',  fontsize='8')
    p.edge('tx',    'asr_r')
    p.edge('asr_r', 'note',  label='conf≥0.40',       fontsize='8')
    p.edge('note',  'llm_r')
    p.edge('llm_r', 'rev',   label='conf≥0.50',       fontsize='8')
    p.edge('rev',   'del',   label='approved',         fontsize='8')

    # EncounterState band — same rank row below the pipeline nodes
    with p.subgraph() as rank_state:
        rank_state.attr(rank='same')
        p.node('estate',
               '<<b>EncounterState (Pydantic v2)</b>  ·  shared across all nodes<br/>'
               '<font point-size="8">'
               'encounter_id  ·  provider_id  ·  recording_mode (AMBIENT | DICTATION)  ·  '
               'context_packet  ·  audio_segments  ·  transcript  ·  generated_note  ·  '
               'final_note  ·  delivery_result  ·  errors[]  ·  EncounterMetrics'
               '</font>>',
               shape='rectangle', style='filled',
               fillcolor=STATE_FILL, fontcolor=PIPE_FILL,
               fontsize='9', fontname='Helvetica',
               width='16', height='0.6')

    # one invisible edge from first pipeline node → state band (keeps band below)
    p.edge('ctx', 'estate', style='invis')


# ────────────────────────────────────────────────────────────────────────────
# §2  MCP Registry & Servers   (left half of middle row)
# ────────────────────────────────────────────────────────────────────────────
with d.subgraph(name='cluster_mcp') as m:
    m.attr(label='§2  MCP ENGINE REGISTRY & SERVERS  (mcp_servers/)',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=MCP_BG,
           color=MCP_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    # Registry hub on its own rank
    m.node('reg',
           '<<b>EngineRegistry</b><br/>'
           '<font point-size="8">mcp_servers/registry.py<br/>'
           'get_asr()  ·  get_llm()  ·  get_ehr()<br/>'
           'get_asr_for_provider(provider_id, use_lora=False)<br/>'
           'get_with_failover()  ·  health_check_all()<br/>'
           'Config: config/engines.yaml</font>>',
           shape='box', style='filled,rounded',
           fillcolor=MCP_FILL, fontcolor=WHITE,
           fontsize='10', fontname='Helvetica-Bold', width='2.8')

    # Server families on the same rank (L-to-R under the registry)
    with m.subgraph() as rank_srv:
        rank_srv.attr(rank='same')

        # ASR cluster
        with m.subgraph(name='cluster_asr') as a:
            a.attr(label='ASR', style='filled', fillcolor='#DCFCE7',
                   color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mnode(a, 'asr_wx',
                  '[DEFAULT] WhisperXServer',
                  ['faster-whisper (CTranslate2)',
                   'pyannote 3.1 · wav2vec2 alignment',
                   'whisper-large-v3 · CUDA A10G',
                   'VRAM peak 10-12 GB'])
            mnode(a, 'asr_lora',
                  '[OPT-IN] WhisperXLoraServer',
                  ['peft LoRA adapter · ≥30 min audio',
                   'Ambient: -11-13% WER'],
                  future=True)

        # LLM cluster
        with m.subgraph(name='cluster_llm') as l:
            l.attr(label='LLM', style='filled', fillcolor='#DCFCE7',
                   color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mnode(l, 'llm_ol',
                  '[DEFAULT] OllamaServer',
                  ['OpenAI-compat · localhost:11434/v1',
                   'qwen2.5:14b (Apache 2.0)  ~8 GB VRAM',
                   'keep_alive=0 · per-task model overrides'])
            mnode(l, 'llm_fut',
                  '[FUTURE] vLLM / Claude API / OpenAI',
                  [], future=True)

        # EHR cluster
        with m.subgraph(name='cluster_ehr') as e:
            e.attr(label='EHR', style='filled', fillcolor='#FEF9C3',
                   color=EHR_FILL, fontname='Helvetica-Bold', fontsize='10')
            e.node('ehr_stub',
                   '<<b>[DEFAULT] StubEHRServer</b><br/>'
                   '<font point-size="8">Reads patient_context.yaml<br/>'
                   'get_patient() · get_problem_list()<br/>'
                   'get_medications() · get_allergies()<br/>'
                   'get_recent_labs() · push_note()</font>>',
                   shape='box', style='filled,rounded',
                   fillcolor=EHR_FILL, fontcolor=WHITE,
                   fontsize='9', fontname='Helvetica', width='2.4')
            mnode(e, 'ehr_fut',
                  '[FUTURE] FHIRServer / HL7v2 / Extension',
                  [], future=True)

        # Data servers cluster
        with m.subgraph(name='cluster_data') as ds:
            ds.attr(label='Data Servers', style='filled', fillcolor='#DCFCE7',
                    color=MCP_FILL, fontname='Helvetica-Bold', fontsize='10')
            mnode(ds, 'tpl_srv',
                  'TemplateServer',
                  ['NoteTemplate YAML loading',
                   'list_templates() · get_template()'])
            mnode(ds, 'dict_srv',
                  'MedicalDictServer',
                  ['get_hotwords(specialty, N)',
                   '98K OpenMedSpel base'])

    # registry → server edges
    m.edge('reg', 'asr_wx',   label='ASR',  fontsize='8', lhead='cluster_asr')
    m.edge('reg', 'asr_lora', fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'llm_ol',   label='LLM',  fontsize='8', lhead='cluster_llm')
    m.edge('reg', 'llm_fut',  fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'ehr_stub', label='EHR',  fontsize='8', lhead='cluster_ehr')
    m.edge('reg', 'ehr_fut',  fontsize='8', style='dashed', color=FUTURE_FG)
    m.edge('reg', 'tpl_srv',  fontsize='8')
    m.edge('reg', 'dict_srv', fontsize='8')


# ────────────────────────────────────────────────────────────────────────────
# §3  Supporting Components   (right half of middle row)
# ────────────────────────────────────────────────────────────────────────────
with d.subgraph(name='cluster_support') as s:
    s.attr(label='§3  SUPPORTING COMPONENTS',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=SUPP_BG,
           color=EHR_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    snode(s, 'postproc', 'Post-Processor  (postprocessor/)',
          ['medasr_postprocessor.py · 12-stage rule-based',
           'medical_wordlist.txt · 98K OpenMedSpel (GPL)',
           'CTC stutters -90%  ·  char stutters -99%',
           'Medical term correction -87%'])

    snode(s, 'prov_mgr', 'Provider Profile System  (config/providers/)',
          ['style_directives · custom_vocabulary · asr_overrides',
           'template_routing · quality_scores · quality_history',
           'ProviderManager.resolve_template(provider_id, visit_type)'])

    snode(s, 'tpl_sys', 'Template System  (config/templates/*.yaml)',
          ['ortho_follow_up · ortho_initial_eval · soap_default',
           'sections: label, required, prompt_hint, formatting',
           'Routing: provider_id + visit_type → template_id → YAML'])

    snode(s, 'qual_fw', 'Quality Evaluation  (quality/)',
          ['evaluator.py · LLM-as-judge (llama3.1)',
           'fact_extractor.py · meds / diagnoses / findings',
           'Dimensions: accuracy · completeness · no_hallucination',
           '            structure · language  (each 1–5)'])

    s.node('qual_trend',
           '<<b>Quality Trend  (v1 → v6)</b><br/>'
           '<font point-size="8">'
           'v1 basic        ~3.50<br/>'
           'v2 templates     4.30<br/>'
           'v3 EHR context   4.34<br/>'
           'v4 provider      4.38<br/>'
           'v5 ASR knobs     4.35<br/>'
           '<b>v6 qwen2.5:14b  4.44 ✓</b>'
           '</font>>',
           shape='box', style='filled,rounded',
           fillcolor=GRAY_BG, fontcolor='#1C1917',
           fontsize='9', fontname='Helvetica', width='2.2')

    s.edge('prov_mgr', 'tpl_sys',     label='resolves', fontsize='8')
    s.edge('qual_fw',  'qual_trend',  fontsize='8')


# ────────────────────────────────────────────────────────────────────────────
# §4  API + Web UI   (bottom row)
# ────────────────────────────────────────────────────────────────────────────
with d.subgraph(name='cluster_ui') as u:
    u.attr(label='§4  API + WEB UI',
           labelloc='t', labeljust='l',
           style='filled', fillcolor=WEB_BG,
           color=WEB_FILL, penwidth='2',
           fontname='Helvetica-Bold', fontsize='12')

    with u.subgraph() as rank_ui:
        rank_ui.attr(rank='same')

        u.node('api',
               '<<b>FastAPI Backend  (api/)</b><br/>'
               '<font point-size="8">'
               'POST /encounters  ·  POST /{id}/upload  ·  GET /{id}<br/>'
               'GET /{id}/transcript · /{id}/note · /{id}/audio<br/>'
               'GET /{id}/comparison · /{id}/quality<br/>'
               'GET /providers  ·  /providers/{id}/quality-trend<br/>'
               'GET /quality/aggregate · /samples · /dimensions<br/>'
               'WS /ws/encounters/{id} — real-time pipeline progress<br/>'
               'Data source: output/ directory tree</font>>',
               shape='box', style='filled,rounded',
               fillcolor=WEB_FILL, fontcolor=WHITE,
               fontsize='9', fontname='Helvetica-Bold', width='3.8')

        u.node('web',
               '<<b>Next.js Web App  (client/web/)</b><br/>'
               '<font point-size="8">'
               'Dashboard (/)  — KPI cards · quality trend chart (Recharts)<br/>'
               'Samples (/samples)  — filterable table<br/>'
               'Sample Detail (/samples/[id])  — 6 tabs:<br/>'
               '  Transcript — audio player + version picker (v1–v6)<br/>'
               '  Clinical Note — Markdown + version picker<br/>'
               '  Comparison — gold vs generated side-by-side<br/>'
               '  Quality Scores — dimension bar chart<br/>'
               '  Compare Versions — LCS line diff (green/red/gray)<br/>'
               'Providers (/providers)  ·  Upload (/upload)</font>>',
               shape='box', style='filled,rounded',
               fillcolor=WEB_FILL, fontcolor=WHITE,
               fontsize='9', fontname='Helvetica-Bold', width='3.8')

    u.edge('web', 'api', label='REST calls', fontsize='8')
    u.edge('api', 'web', label='JSON + WS',  fontsize='8', style='dashed')


# ────────────────────────────────────────────────────────────────────────────
# Legend
# ────────────────────────────────────────────────────────────────────────────
with d.subgraph(name='cluster_legend') as leg:
    leg.attr(label='Legend', labelloc='b', labeljust='r',
             style='filled', fillcolor=GRAY_BG,
             fontname='Helvetica', fontsize='10', color='#CBD5E1')
    leg.node('l1', '[DEFAULT]  active implementation',
             shape='plaintext', fontsize='9')
    leg.node('l2', '[OPT-IN / FUTURE]  planned or stubbed (dashed border)',
             shape='plaintext', fontsize='9')
    leg.node('l3', '──►  data flow      - - ►  optional / future path',
             shape='plaintext', fontsize='9')
    leg.edge('l1', 'l2', style='invis')
    leg.edge('l2', 'l3', style='invis')


# ────────────────────────────────────────────────────────────────────────────
# Vertical section ordering  (invisible anchor edges: pipe → mcp → ui)
# ────────────────────────────────────────────────────────────────────────────
# estate (bottom of §1) → reg (top of §2/§3)
d.edge('estate', 'reg',      style='invis')
# mcp → api  (§2/§3 above §4)
d.edge('reg',    'api',      style='invis')
d.edge('postproc','api',     style='invis')


# ────────────────────────────────────────────────────────────────────────────
# Cross-section call edges  (pipeline nodes → their MCP / support targets)
# ────────────────────────────────────────────────────────────────────────────
CE = dict(style='dashed', fontsize='8', constraint='false')

d.edge('ctx',  'ehr_stub',  label='get_patient()',          color=EHR_FILL,  **CE)
d.edge('tx',   'asr_wx',   label='transcribe_batch_sync()', color=MCP_FILL,  **CE)
d.edge('tx',   'postproc', label='_apply_postprocessor()',  color=EHR_FILL,  **CE)
d.edge('note', 'llm_ol',   label='generate_sync()',         color=MCP_FILL,  **CE)
d.edge('note', 'tpl_srv',  label='load_template()',         color=MCP_FILL,  **CE)
d.edge('note', 'dict_srv', label='get_hotwords()',          color=MCP_FILL,  **CE)
d.edge('del',  'ehr_stub',  label='push_note()',             color=EHR_FILL,  **CE)
d.edge('del',  'api',       label='writes output/',          color=WEB_FILL,  **CE)


# ────────────────────────────────────────────────────────────────────────────
# Render
# ────────────────────────────────────────────────────────────────────────────
out_dir = Path('docs/images')
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / 'architecture_diagram'

d.render(filename=str(out_path), format='png', cleanup=True)
print(f'✓  PNG : {out_path}.png')

dot_src = out_dir / 'architecture_diagram.dot'
dot_src.write_text(d.source)
print(f'✓  DOT : {dot_src}')
