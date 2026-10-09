"""Check replay accounting against missing, late, blank and duplicate output."""
import copy
import unittest
from replay_analysis import summarize, stats, text_key


class Accounting(unittest.TestCase):
    def phase(self):
        return {'presentations':[{'id':1,'text':'Open the gate.','category':'test','at':0,'ended_at':1},
                                 {'id':2,'text':'Wait for me.','category':'test','at':1,'ended_at':2}],
                'ocr':[{'cue_id':1,'text':'Open the gate.','started_at':.1,'completed_at':.2,'ms':100}],
                'captures':[{'cue_id':1,'at':.1}], 'ui':[], 'results':[]}

    def display(self, p, at=.5, source='Open the gate.', target='打開大門。', visible=1, warning=''):
        p['ui'].append({'at':at,'source':source,'target':target,'visible_cue_id':visible,
                        'visible_source':'Open the gate.' if visible==1 else 'Wait for me.', 'warning':warning})

    def test_missing_in_denominator(self):
        p=self.phase();self.display(p);s=summarize(p)
        self.assertEqual((s['cues'],s['unobserved'],s['usable_within_700ms']),(2,1,1))

    def test_late_old_cue_never_success(self):
        p=self.phase();self.display(p,at=1.2,visible=2);s=summarize(p)
        self.assertEqual((s['usable_current_display'],s['late_source_display']),(0,1))

    def test_warning_not_success(self):
        p=self.phase();self.display(p,warning='rejected');self.assertEqual(summarize(p)['usable_within_700ms'],0)

    def test_blank_target_not_success(self):
        p=self.phase();self.display(p,target='');self.assertEqual(summarize(p)['usable_current_display'],0)

    def test_duplicate_does_not_inflate(self):
        p=self.phase();self.display(p);self.display(p,at=.6);self.assertEqual(summarize(p)['usable_within_700ms'],1)

    def test_700_boundary(self):
        p=self.phase();self.display(p,at=.7);self.assertEqual(summarize(p)['usable_within_700ms'],1)
        p=self.phase();self.display(p,at=.701);self.assertEqual(summarize(p)['usable_within_700ms'],0)

    def test_cue_end_exclusive(self):
        p=self.phase();self.display(p,at=1,visible=1);self.assertEqual(summarize(p)['usable_current_display'],0)

    def test_incomplete_source_not_success(self):
        p=self.phase();self.display(p,source='Open');self.assertEqual(summarize(p)['usable_current_display'],0)

    def test_period_only_tolerance(self):
        self.assertEqual(text_key('Open gate.'),text_key('Open gate'))
        for a,b in [('HP 1.','HP 1'),('Wait?','Wait'),('Wait!','Wait'),('Wait...','Wait'),('Do not go','Do go')]:
            self.assertNotEqual(text_key(a),text_key(b))

    def test_no_semantic_claim(self):
        p=self.phase();self.display(p);self.assertIsNone(summarize(p)['semantic_correct_coverage'])

    def test_percentiles_missing_not_zero(self):
        self.assertIsNone(stats([None]));self.assertEqual(stats([None,10,20])['n'],2)


if __name__=='__main__':unittest.main()
