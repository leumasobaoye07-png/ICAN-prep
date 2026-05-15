"""
ICAN Prep — Pre-generate AI explanations using Groq (free tier)
===============================================================
Usage:
    pip install groq
    python generate_explanations.py --api-key YOUR_GROQ_KEY

Free tier: 14,400 requests/day — finishes all 400 in one run.
Resumes from explanations.json if interrupted.
Output: ican_prep_final.html
"""

import json, re, sys, time, os, argparse

def extract_exam_data(html):
    match = re.search(r'<script id="exam-data"[^>]*>([\s\S]*?)</script>', html)
    if not match:
        raise ValueError("Could not find exam-data block")
    return json.loads(match.group(1))

def build_prompt(session, q):
    opts = "\n".join(f"{k}. {v[:120]}" for k, v in q["options"].items())
    correct = q["options"].get(q["answer"], "")[:120]
    text = (q.get("text") or "Stem in options").strip()
    ans = q["answer"]
    return f"""You are an ICAN exam tutor. No preamble, no filler. Straight explanation.

ICAN Business & Finance (Foundation Level) - {session}
Question: {text}
Options:
{opts}
Correct answer: {ans} - {correct}

Reply in this exact format:
**Why {ans} is correct:** 2-3 sentences.
**Why the other options are wrong:** one sentence each, labelled by letter.
**Key concept:** one sentence naming the specific topic tested."""

def generate_one(client, session, q, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=350,
                messages=[{"role": "user", "content": build_prompt(session, q)}]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            msg = str(e)
            if '429' in msg or 'rate' in msg.lower():
                wait = 30 * (attempt + 1)
                print(f"\n  Rate limit. Waiting {wait}s...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise
    raise Exception("Max retries exceeded")

def patch_js(html):
    start_tag = "async function getAIExplanation(qIdx) {"
    start = html.find(start_tag)
    if start == -1:
        return html, False
    depth, i = 0, start
    while i < len(html):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        return html, False

    new_fn = (
        "function getAIExplanation(qIdx) {\n"
        "  var btn = document.getElementById('ai-explain-btn');\n"
        "  var responseEl = document.getElementById('ai-response-' + qIdx);\n"
        "  if (!btn || !responseEl) return;\n"
        "  var q = state.currentExam.questions[qIdx];\n"
        "  responseEl.className = 'ai-response';\n"
        "  if (!q.explanation) {\n"
        "    responseEl.innerHTML = '<em style=\"color:var(--muted)\">No explanation for this question.</em>';\n"
        "    return;\n"
        "  }\n"
        "  var fmt = q.explanation\n"
        "    .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')\n"
        "    .replace(/\\n\\n/g, '</p><p>')\n"
        "    .replace(/\\n/g, '<br>');\n"
        "  responseEl.innerHTML = '<p>' + fmt + '</p>';\n"
        "  if (btn) { btn.textContent = '\\u2713 Shown'; btn.disabled = true; }\n"
        "}"
    )
    return html[:start] + new_fn + html[end:], True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--input",   default="ican_prep.html")
    parser.add_argument("--output",  default="ican_prep_final.html")
    parser.add_argument("--cache",   default="explanations.json")
    parser.add_argument("--delay",   type=float, default=0.5)
    args = parser.parse_args()

    from groq import Groq
    client = Groq(api_key=args.api_key)

    if not os.path.exists(args.input):
        sys.exit(f"ERROR: {args.input} not found.")

    with open(args.input, "r", encoding="utf-8") as f:
        html = f.read()

    exam_data = extract_exam_data(html)

    cache = {}
    if os.path.exists(args.cache):
        with open(args.cache, "r", encoding="utf-8") as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} cached explanations")

    all_qs = [(s["session"], q) for s in exam_data for q in s["questions"] if q.get("answer")]
    todo   = [(sess, q) for sess, q in all_qs if f"{sess}_{q['num']}" not in cache]
    eta_mins = round(len(todo) * args.delay / 60, 1)
    print(f"Total: {len(all_qs)} | Cached: {len(cache)} | To generate: {len(todo)}")
    print(f"ETA: ~{eta_mins} minutes\n")

    for i, (session, q) in enumerate(todo):
        key   = f"{session}_{q['num']}"
        label = (q.get("text") or "(no text)")[:50]
        print(f"[{len(cache)+1}/{len(all_qs)}] {session} Q{q['num']}: {label}...", end=" ", flush=True)
        try:
            expl = generate_one(client, session, q)
            cache[key] = expl
            print("OK")
            with open(args.cache, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            if i < len(todo) - 1:
                time.sleep(args.delay)
        except Exception as e:
            print(f"FAILED: {e}")
            time.sleep(5)

    print(f"\n{len(cache)} explanations ready. Building HTML...")

    for s in exam_data:
        for q in s["questions"]:
            key = f"{s['session']}_{q['num']}"
            if key in cache:
                q["explanation"] = cache[key]

    new_data = json.dumps(exam_data, ensure_ascii=False)
    new_html = re.sub(
        r'(<script id="exam-data"[^>]*>)([\s\S]*?)(</script>)',
        lambda m: m.group(1) + new_data + m.group(3),
        html
    )

    new_html, patched = patch_js(new_html)
    print("JS patched OK" if patched else "WARNING: JS patch failed.")

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"\nDone. Open '{args.output}' in your browser.")

if __name__ == "__main__":
    main()
