"""Pure replay analysis: failures stay in coverage denominators."""
import math
import re
import statistics


def text_key(text):
    # Same narrowly defined period tolerance as production dialogue dedup.
    return re.sub(r'(?<=[A-Za-z])\.$', '', ' '.join(text.split()))


def stats(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return {'n':len(values), 'mean_ms':round(statistics.mean(values), 2),
            'p50_ms':round(values[math.ceil(len(values)*.5)-1], 2),
            'p95_ms':round(values[math.ceil(len(values)*.95)-1], 2),
            'max_ms':round(values[-1], 2)}


def summarize(phase):
    outcomes = []
    for cue in phase['presentations']:
        end = cue['ended_at']
        observations = [r for r in phase['ocr'] if r['cue_id']==cue['id']]
        exact = [r for r in observations if text_key(r['text'])==text_key(cue['text'])]
        # A late old output is recorded, but cannot count as a current display.
        matching = [r for r in phase['ui'] if r['target'] and not r['warning']
                    and text_key(r['source'])==text_key(cue['text'])
                    and cue['at'] <= r['at'] < end and r['visible_cue_id']==cue['id']]
        matching.sort(key=lambda r:r['at'])
        latency = (matching[0]['at']-cue['at'])*1000 if matching else None
        first_exact = min((r['completed_at'] for r in exact), default=None)
        first_capture = min((r['at'] for r in phase['captures'] if r['cue_id']==cue['id']), default=None)
        first_admission = min((r['started_at'] for r in observations), default=None)
        outcomes.append({'cue_id':cue['id'], 'source':cue['text'], 'category':cue['category'],
                         'onset_at':cue['at'], 'visible_ms':(end-cue['at'])*1000,
                         'first_capture_ms':None if first_capture is None else (first_capture-cue['at'])*1000,
                         'first_ocr_start_ms':None if first_admission is None else (first_admission-cue['at'])*1000,
                         'first_exact_ocr_ms':None if first_exact is None else (first_exact-cue['at'])*1000,
                         'any_ocr':bool(observations), 'exact_ocr':bool(exact),
                         'ocr_incomplete':bool(observations) and not bool(exact),
                         'display_latency_ms':latency, 'usable_current_display':bool(matching),
                         'within_700ms':latency is not None and latency<=700,
                         'semantic_verified':False})
    evaluated = [r for r in outcomes if r['source']]
    translated = [t for r in phase['results'] for t in r['translations']]
    phase['outcomes'] = outcomes
    phase['summary'] = {
        'cues':len(evaluated), 'unobserved':sum(not r['any_ocr'] for r in evaluated),
        'exact_ocr_seen':sum(r['exact_ocr'] for r in evaluated),
        'usable_current_display':sum(r['usable_current_display'] for r in evaluated),
        'usable_within_700ms':sum(r['within_700ms'] for r in evaluated),
        'display_latency':stats([r['display_latency_ms'] for r in evaluated]),
        'first_exact_ocr_latency':stats([r['first_exact_ocr_ms'] for r in evaluated]),
        'ocr_call_latency':stats([r['ms'] for r in phase['ocr']]),
        'ocr_calls':len(phase['ocr']), 'captures':len(phase['captures']),
        'backend_requests':sum(t['backend_state'] in ('warm','cold') for t in translated),
        'cache_hits':sum(t['cache_hit'] for t in translated),
        'guard_rejections':sum(bool(t['warning']) for t in translated),
        'late_source_display':sum(bool(r['target']) and not r['warning'] and
            text_key(r['source'])!=text_key(r['visible_source']) for r in phase['ui']),
        'semantic_correct_coverage':None,
        'latency_sample_policy':'successful CURRENT displays only; coverage includes every nonblank cue'}
    return phase['summary']


def aggregate(phases):
    outcomes = [r for p in phases for r in p['outcomes'] if r['source']]
    ocr = [r for p in phases for r in p['ocr']]
    return {'cues':len(outcomes), 'exact_ocr_seen':sum(r['exact_ocr'] for r in outcomes),
            'unobserved':sum(not r['any_ocr'] for r in outcomes),
            'usable_current_display':sum(r['usable_current_display'] for r in outcomes),
            'usable_within_700ms':sum(r['within_700ms'] for r in outcomes),
            'display_latency':stats([r['display_latency_ms'] for r in outcomes]),
            'ocr_call_latency':stats([r['ms'] for r in ocr]), 'ocr_calls':len(ocr),
            'late_source_display':sum(p['summary']['late_source_display'] for p in phases),
            'guard_rejections':sum(p['summary']['guard_rejections'] for p in phases),
            'cache_hits':sum(p['summary']['cache_hits'] for p in phases),
            'semantic_correct_coverage':None}
