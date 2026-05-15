"""
ICAN Topic Injector
====================
Run this AFTER tag_topics.py finishes.
Injects topics into ican_prep.html → ican_prep_with_topics.html

Usage:
    python inject_topics.py
    (uses topics.json and ican_prep.html in same folder)
"""

import json, re, sys, os

def main():
    for f in ['topics.json', 'ican_prep.html']:
        if not os.path.exists(f):
            sys.exit(f"ERROR: {f} not found.")

    with open('topics.json', 'r', encoding='utf-8') as f:
        topics = json.load(f)

    with open('ican_prep.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract both datasets
    m = re.search(r'<script id="exam-data"[^>]*>([\s\S]*?)</script>', html)
    t = re.search(r'<script id="theory-data"[^>]*>([\s\S]*?)</script>', html)
    mcq_data    = json.loads(m.group(1))
    theory_data = json.loads(t.group(1))

    # Inject topics into MCQ questions
    mcq_tagged = theory_tagged = 0
    for s in mcq_data:
        for q in s['questions']:
            key = f"mcq_{s['session']}_{q['num']}"
            if key in topics:
                q['topic'] = topics[key]
                mcq_tagged += 1

    # Inject topics into theory questions
    for s in theory_data:
        for q in s['questions']:
            key = f"theory_{s['session']}_{q['num']}"
            if key in topics:
                q['topic'] = topics[key]
                theory_tagged += 1

    print(f"MCQ tagged: {mcq_tagged}, Theory tagged: {theory_tagged}")

    # Replace both data blocks in HTML
    new_mcq    = json.dumps(mcq_data,    ensure_ascii=False)
    new_theory = json.dumps(theory_data, ensure_ascii=False)

    html = re.sub(
        r'(<script id="exam-data"[^>]*>)([\s\S]*?)(</script>)',
        lambda m: m.group(1) + new_mcq + m.group(3),
        html
    )
    html = re.sub(
        r'(<script id="theory-data"[^>]*>)([\s\S]*?)(</script>)',
        lambda m: m.group(1) + new_theory + m.group(3),
        html
    )

    # Verify injection
    assert '"topic"' in html, "Topic injection failed"

    out = 'ican_prep_with_topics.html'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Saved: {out}")
    print("Next: open a new chat, upload ican_prep_with_topics.html to build the filter/tracker UI.")

if __name__ == "__main__":
    main()
