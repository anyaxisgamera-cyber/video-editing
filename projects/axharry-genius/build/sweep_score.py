"""Score Seed-VC sweep outputs: Whisper intelligibility vs script line + ECAPA similarity vs reference."""
import difflib, json, re, subprocess, sys, unicodedata
from pathlib import Path
import numpy as np, torch
ROOT = Path(__file__).resolve().parent.parent
run = Path(sys.argv[1]); only = sys.argv[2:]
def load(p, sr=16000):
    return np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",str(p),"-ac","1","-ar",str(sr),"-f","f32le","-"],capture_output=True,check=True).stdout,dtype="<f4").copy()
norm = lambda t: re.sub(r"[^\wఀ-౿]", "", unicodedata.normalize("NFC", t))
from speechbrain.inference.speaker import EncoderClassifier
ecapa = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(ROOT/"work/voice/ecapa"), run_opts={"device":"cpu"})
def emb(x):
    with torch.no_grad(): e = ecapa.encode_batch(torch.from_numpy(x).unsqueeze(0)).squeeze()
    return e / e.norm()
ref = emb(load(ROOT/"brand/voice/(256k)_vocals_mixed.m4a"))
from faster_whisper import WhisperModel
wm = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
meta = json.load(open(run/"in/sweep_meta.json")); content = json.load(open(ROOT/"content/te.json"))
for name, m in meta.items():
    if only and name not in only: continue
    text = content["lines"][m["line"]]["text"]
    for tag in ("source", "A", "B", "C"):
        p = run/"in"/f"{name}.wav" if tag == "source" else run/"out"/f"sweep_{name}_{tag}.wav"
        if not p.exists(): continue
        x = load(p)
        heard = " ".join(s.text for s in wm.transcribe(x, language="te", beam_size=5)[0]).strip()
        print(f"{name} {tag:6s} intelligibility={difflib.SequenceMatcher(None,norm(text),norm(heard),autojunk=False).ratio():.2f} similarity={float(emb(x)@ref):.3f} | {heard}", flush=True)
