// Editable review deck. Run with the Codex bundled Node runtime and environment paths.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const workspaceDir = process.cwd();
const { RUNTIME_NODE_MODULES, RUNTIME_PYTHON, SKILL_DIR } = process.env;
if (!RUNTIME_NODE_MODULES || !RUNTIME_PYTHON || !SKILL_DIR) throw new Error('Set bundled runtime and skill paths');
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(RUNTIME_NODE_MODULES, '@oai/artifact-tool/dist/artifact_tool.mjs')));
const { finalizePresentation, resolvePresentationFont } = await import(pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')));
const font = resolvePresentationFont({fontFamily:'Arial'});
const dir = path.join(workspaceDir, 'artifacts/deck');
const output = path.join(workspaceDir, 'output/submission');
await fs.mkdir(dir, {recursive:true}); await fs.mkdir(output, {recursive:true});
const presentation = Presentation.create({slideSize:{width:1280,height:720}});
let measured = 'Official FDB-v3 results unavailable';
const fdbReports = [];
const reportRoot = 'docs/results';
try {
  const pass = JSON.parse(await fs.readFile(path.join(reportRoot, 'interra_elevenlabs_pass_rate_report.json'), 'utf8'));
  const tool = JSON.parse(await fs.readFile(path.join(reportRoot, 'interra_elevenlabs_evaluation_report.json'), 'utf8'));
  measured = `Best completed hosted run: ${pass.passed}/${pass.total_scenarios} strict passes\n${tool.turn_taking.turn_taken}/${tool.total_scenarios} turn-taken; ${tool.turn_taking.no_response} no-response\nTool selection ${tool.by_metric.tool_selection_acc_all}; arguments ${tool.by_metric.argument_acc_all} across all cases`;
} catch {}
for (const reportName of [
  'interra_elevenlabs_asr_report.json',
  'interra_elevenlabs_evaluation_report.json',
  'interra_elevenlabs_pass_rate_report.json',
  'interra_elevenlabs_latency_report.json',
]) {
  try {
    await fs.access(path.join('artifacts/fdb_v3', reportName));
    fdbReports.push(reportName);
  } catch {}
}
let tests = 'See the accompanying test report for the final test count';
try {
  const log = await fs.readFile('artifacts/tests-current.txt','utf8');
  const match = log.match(/Ran (\d+) tests/);
  if (match && /\bOK\b/.test(log) && !/FAILED/.test(log)) tests = `${match[1]} automated tests passed on Python 3.11`;
} catch {}
const slides = [
 ['Interra', 'Theme 05 / Interruptible real-time agents', 'LiveKit voice agent for Full-Duplex-Bench v3'],
 ['What the benchmark measures', '100 recordings / 79 unique scenarios\n12 speakers and five disfluency types\n12 mock tools across four domains\nCorrections, interruptions and 1–3 dependent calls', 'Round 1: benchmark 60% / extension 20% / documentation, architecture and video 20%.'],
 ['Submission architecture', 'Silero VAD detects speech boundaries\nLiveKit Inference Deepgram Nova-3 transcribes speech\nGPT-4.1 mini selects and chains tools\nCartesia Sonic-3 speaks grounded results\nLiveKit coordinates turns and interruptions', 'The official MockAPIRegistry remains the source of tool behavior and telemetry.'],
 ['Correction and tool lifecycle', 'LiveKit handles speech interruption and tool scheduling.\nDependent calls receive the preceding tool result.\nThe prompt asks for completion claims grounded in tool results.\nFDB-v3 records speech and tool timestamps.\nSession cleanup drains briefly, closes the session and ends the job.', 'The retained custom stale-result gate and duplicate-write ledger are not integrated into this adapter.'],
 ['FDB-v3 evidence', `${tests}\n${measured}\nReproduce: python scripts/reproduce.py`, 'The reports measure archived hosted-model source. Later fixes are awaiting a new score.'],
 ['Camera extension', 'A separate LiveKit agent samples the current camera frame\nThe frame joins the next completed voice turn\nNew tracks discard older frames\nDevice advice stays tied to visible evidence', 'Frame lifecycle has deterministic tests. A live camera demonstration is still required.'],
 ['Reproduction and limits', 'Three LIVEKIT_* Secrets provide model and room access\nThe official FDB-v3 code and audio are fetched at a pinned revision\nBest completed run: 7 inference failures and 42 no-response cases\nUpdated-model rerun and live extension demo remain open', 'The organizer rerun needs the declared LiveKit credentials. The report filenames retain a legacy provider label.'],
 ['Demonstration', '1. Show an interrupted request and corrected tool call\n2. Show the resulting FDB trace and timestamps\n3. Run camera-assisted troubleshooting\n4. Display the official report and exact reproduction command', 'Target video length: 3–5 minutes. Maximum deck length: 8 slides.'],
];
function text(slide, value, top, height, size, color, bold=false) {
  const shape=slide.shapes.add({geometry:'textbox',position:{left:80,top,width:1120,height},fill:'none',line:{fill:'none',width:0}});
  shape.text=value; shape.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none'};
}
for (let i=0;i<slides.length;i++) {
  const slide=presentation.slides.add();slide.background.fill=i===0?'#0A2032':'#F7F9FC';
  const [title,body,note]=slides[i];
  text(slide,title,i===0?180:64,i===0?110:100,i===0?76:42,i===0?'#FFFFFF':'#102A43',true);
  text(slide,body,i===0?310:210,i===0?120:335,i===0?32:30,i===0?'#6CE4CE':'#243B53');
  text(slide,note,590,72,20,i===0?'#B9CFDD':'#52667A');
  slide.speakerNotes.textFrame.setText('Evidence: supplied Theme05_Participant_Guide_UPDATED_FBD.docx; docs/FDB_V3.md; docs/STATUS.md; docs/results/ official reports and measured-source archive; tests/unit/test_extension_livekit.py. Sources: https://github.com/DanielLin94144/Full-Duplex-Bench . This is an alternate review deck. The organizer-template deck is docs/Interra_Theme05_submission.pptx. Final rerun and live extension video remain open.');
}
const candidatePath=path.join(dir,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const finalPath=path.join(output,`Interra-Theme5-FDB-v3-${process.env.DECK_REVISION || 'review'}.pptx`);
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,
  integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
  explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
  fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(dir,`${process.env.DECK_REVISION || 'review'}.validation.json`)});
for(let i=0;i<presentation.slides.items.length;i++) {
  const png=await presentation.export({slide:presentation.slides.items[i],format:'png',scale:1});
  await fs.writeFile(path.join(dir,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log(finalPath);
