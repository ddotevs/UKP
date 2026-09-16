"""
TF-IDF based kickball rules lookup engine.
Preprocesses the full ruleset at startup for instant queries.
"""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_sections = []       # list of (section_id, section_text)
_vectorizer = None
_tfidf_matrix = None
_ready = False
_SECTION_HEADERS = {}


def _parse_headers(rules_text):
    """Extract top-level section headers like '8. KICKING'."""
    headers = {}
    for line in rules_text.split('\n'):
        match = re.match(r'^(\d+)\.\s+(.+)', line.strip())
        if match and not re.match(r'^\d+\.\d+', line.strip()):
            headers[match.group(1)] = match.group(2).strip()
    return headers


def _parse_sections(rules_text):
    """Split rules text into numbered sections like ('8.01', 'full text...')."""
    sections = []
    current_id = None
    current_lines = []

    for line in rules_text.split('\n'):
        match = re.match(r'^(\d+\.\d+(?:\.\d+)?)\s+(.*)', line.strip())
        if match:
            if current_id and current_lines:
                sections.append((current_id, ' '.join(current_lines)))
            current_id = match.group(1)
            current_lines = [match.group(2)]
        elif current_id and line.strip():
            current_lines.append(line.strip())

    if current_id and current_lines:
        sections.append((current_id, ' '.join(current_lines)))

    return sections


def build_index(rules_text):
    """Parse rules and build TF-IDF index. Call once at startup."""
    global _sections, _vectorizer, _tfidf_matrix, _ready, _SECTION_HEADERS

    if not rules_text or not rules_text.strip():
        _ready = False
        return False

    _SECTION_HEADERS = _parse_headers(rules_text)
    _sections = _parse_sections(rules_text)
    if not _sections:
        _ready = False
        return False

    enriched = []
    for sec_id, text in _sections:
        parent = sec_id.split('.')[0]
        header = _SECTION_HEADERS.get(parent, '')
        enriched.append(f"{header} {text}" if header else text)

    _vectorizer = TfidfVectorizer(
        stop_words='english',
        ngram_range=(1, 2),
        max_df=0.9,
    )
    _tfidf_matrix = _vectorizer.fit_transform(enriched)
    _ready = True
    return True


def _normalize(word):
    """Minimal normalization: lowercase, strip trailing 's' for plurals."""
    w = word.lower()
    if len(w) > 3 and w.endswith('s') and not w.endswith('ss'):
        w = w[:-1]
    return w


def _header_relevance(question):
    """Score each parent section header against the query using word overlap."""
    q_words = set(re.findall(r'[a-z]+', question.lower()))
    stop = {'the', 'a', 'an', 'is', 'it', 'in', 'of', 'or', 'and', 'to', 'do', 'can', 'you', 'are', 'at'}
    q_words -= stop
    q_norms = {_normalize(w) for w in q_words} | q_words
    relevance = {}
    for num, header in _SECTION_HEADERS.items():
        h_words = set(re.findall(r'[a-z]+', header.lower()))
        h_norms = {_normalize(w) for w in h_words} | h_words
        overlap = len(q_norms & h_norms)
        relevance[num] = overlap
    return relevance


def query(question, top_n=4, threshold=0.05):
    """Find the most relevant rule sections for a question.
    Returns list of (section_id, section_text, score) tuples.
    After picking the top hit, boosts sibling rules from the same parent section,
    then fills remaining slots preferring sections whose headers match the query.
    """
    if not _ready:
        return []

    q_vec = _vectorizer.transform([question])
    scores = cosine_similarity(q_vec, _tfidf_matrix).flatten()

    ranked = sorted(enumerate(scores), key=lambda x: -x[1])

    # Find the top hit's parent section
    top_idx, top_score = ranked[0]
    if top_score < threshold:
        return []
    top_parent = _sections[top_idx][0].split('.')[0]

    # Score section headers against the query for fill ranking
    header_rel = _header_relevance(question)

    # Collect results: top hit first, then siblings from same parent, then others
    results = []
    seen = set()

    # 1. Top hit
    sec_id, sec_text = _sections[top_idx]
    results.append((sec_id, sec_text, float(top_score)))
    seen.add(top_idx)

    # 2. Best sibling from the same parent section
    siblings = [(idx, s) for idx, s in ranked if idx != top_idx
                and _sections[idx][0].split('.')[0] == top_parent and s >= threshold]
    for idx, score in siblings[:1]:
        sec_id, sec_text = _sections[idx]
        results.append((sec_id, sec_text, float(score)))
        seen.add(idx)

    # 3. Fill remaining slots from other sections, weighted by header relevance
    #    Only 1 result per parent section among fill candidates
    candidates = []
    for idx, score in ranked:
        if idx in seen or score < threshold:
            continue
        parent = _sections[idx][0].split('.')[0]
        if parent == top_parent:
            continue
        boosted = score + header_rel.get(parent, 0) * 0.1
        candidates.append((idx, score, boosted, parent))

    candidates.sort(key=lambda x: -x[2])
    fill_parents = set()
    for idx, orig_score, _, parent in candidates:
        if len(results) >= top_n:
            break
        if parent in fill_parents:
            continue
        fill_parents.add(parent)
        sec_id, sec_text = _sections[idx]
        results.append((sec_id, sec_text, float(orig_score)))
        seen.add(idx)

    return results
