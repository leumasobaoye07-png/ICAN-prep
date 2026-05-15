"""
ICAN Topic Tagger
=================
Tags all MCQ and Theory questions with ICAN B&F topic categories.
Usage:
    pip install groq
    python tag_topics.py --api-key YOUR_GROQ_KEY

Output: topics.json — merge this into your HTML using inject_topics.py
Resumes from topics.json if interrupted.
"""

import json, re, sys, time, os, argparse

# ── ICAN B&F Topic Taxonomy ────────────────────────────────────────────────────
# These are the standard topics in the ICAN Foundation B&F syllabus
TOPICS = """
1. Business Environment & Strategy
2. Organisational Structure
3. Corporate Governance & Stakeholders
4. Business Ethics & Professionalism
5. Leadership & Management
6. Motivation & Human Behaviour
7. Teams & Workgroups
8. Communication
9. Financial Management & Objectives
10. Capital Investment Appraisal
11. Sources of Finance
12. Financial Markets & Instruments
13. Business Organisations & Types
14. Economics & Macroeconomics
15. Marketing & Strategy
16. Management Information & Reporting
"""

SYSTEM_PROMPT = f"""You are an ICAN exam classifier. Given a question from the ICAN Foundation Level Business & Finance paper, return ONLY the most appropriate topic from this list:

{TOPICS}

Rules:
- Return ONLY the topic name exactly as written above (e.g. "Business Ethics & Professionalism")
- No explanation, no punctuation, no extra text
- If a question covers multiple topics, pick the PRIMARY one
- For calculation questions, focus on the financial concept being tested
"""

def classify(client, text):
    if not text or len(text.strip()) < 10:
        return "Uncategorised"
    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=20,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {text[:300]}"}
        ]
    )
    raw = resp.choices[0].message.content.strip()
    # Validate against topic list
    valid = [t.split('. ', 1)[1].strip() for t in TOPICS.strip().split('\n') if t.strip()]
    for v in valid:
        if v.lower() in raw.lower():
            return v
    return raw  # Return as-is if no exact match

def extract_data(html):
    m = re.search(r'<script id="exam-data"[^>]*>([\s\S]*?)</script>', html)
    t = re.search(r'<script id="theory-data"[^>]*>([\s\S]*?)</script>', html)
    return json.loads(m.group(1)), json.loads(t.group(1))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--input",   default="ican_prep.html")
    parser.add_argument("--cache",   default="topics.json")
    parser.add_argument("--delay",   type=float, default=0.3)
    args = parser.parse_args()

    from groq import Groq
    client = Groq(api_key=args.api_key)

    if not os.path.exists(args.input):
        sys.exit(f"ERROR: {args.input} not found.")

    with open(args.input, 'r', encoding='utf-8') as f:
        html = f.read()

    mcq_data, theory_data = extract_data(html)

    # Build work list
    # Format: {id: "mcq_SESSION_QNUM" or "theory_SESSION_QNUM", text: "..."}
    work = []
    for s in mcq_data:
        for q in s['questions']:
            text = q.get('text', '').strip()
            if not text and q.get('options'):
                # Use first option as context
                text = list(q['options'].values())[0]
            work.append({
                'id': f"mcq_{s['session']}_{q['num']}",
                'text': text or ' '.join(list(q.get('options', {}).values())[:2])
            })
    for s in theory_data:
        for q in s['questions']:
            work.append({
                'id': f"theory_{s['session']}_{q['num']}",
                'text': q.get('question', '')[:300]
            })

    # Load cache
    cache = {}
    if os.path.exists(args.cache):
        with open(args.cache, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        print(f"Loaded {len(cache)} cached topics")

    todo = [w for w in work if w['id'] not in cache]
    print(f"Total: {len(work)} | Cached: {len(cache)} | To tag: {len(todo)}")
    print(f"ETA: ~{round(len(todo)*args.delay/60,1)} minutes\n")

    for i, item in enumerate(todo):
        print(f"[{len(cache)+1}/{len(work)}] {item['id'][:50]}...", end=' ', flush=True)
        try:
            topic = classify(client, item['text'])
            cache[item['id']] = topic
            print(f"→ {topic}")
            with open(args.cache, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            time.sleep(args.delay)
        except Exception as e:
            msg = str(e)
            if '429' in msg or 'rate' in msg.lower():
                print(f"Rate limit. Waiting 30s...")
                time.sleep(30)
            else:
                print(f"FAILED: {e}")
                time.sleep(2)

    print(f"\n{len(cache)} topics tagged. Run inject_topics.py next.")

if __name__ == "__main__":
    main()
