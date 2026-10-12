"""Launch-gate counterexamples; no inference or study allocation."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('seal_v2_test',HERE/'seal_hybrid_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SealControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.sentinel=self.root/'qualified-source.py';self.sentinel.write_text('intact\n')
        self.hashes={str(self.sentinel):m.v2.frozen.file_sha(self.sentinel)}
        self.protocol=json.loads((HERE/'hybrid-protocol.json').read_text())
        self.host={'passed':True,'efficacy_trials':0,'registered_source_files_changed':[],
                   'checks':[{'passed':True},{'passed':True}]}
        self.controls={'all_controls_passed':True,'code_stable_during_controls':True,
                       'model_calls':0,'code_sha256_at_end':self.hashes}
        self.review={'passed':True,'unresolved_findings':[],'reviewed_files':self.hashes}
        self.toy={'files':self.hashes}
        self.args=argparse.Namespace(protocol=self.root/'protocol.json',manifest=self.root/'manifest.json',
            study=self.root/'never-allocated',model_catalog=self.root/'catalog.json',
            host_qualification=self.root/'qualification-summary.json',
            grader_controls=self.root/'controls.json',adversarial_review=self.root/'review.json')
    def write(self):
        for path,value in ((self.args.protocol,self.protocol),(self.args.host_qualification,self.host),
            (self.args.grader_controls,self.controls),(self.args.adversarial_review,self.review),
            (self.root/'toy-registration.json',self.toy)):
            path.write_text(json.dumps(value))
    def rejected_before_allocation(self):
        self.write()
        with patch.object(m.v2.frozen,'prepare') as prepare:
            with self.assertRaises(ValueError):m.seal(self.args)
            prepare.assert_not_called()
        self.assertFalse(self.args.study.exists())
    def test_unqualified_host_cannot_allocate(self):
        self.host['passed']=None;self.rejected_before_allocation()
    def test_changed_qualified_source_cannot_allocate(self):
        self.sentinel.write_text('changed\n');self.rejected_before_allocation()
    def test_failed_baseline_controls_cannot_allocate(self):
        self.controls['all_controls_passed']=False;self.rejected_before_allocation()
    def test_unresolved_review_cannot_allocate(self):
        self.review['unresolved_findings']=['source evidence missing'];self.rejected_before_allocation()
    def test_budget_change_cannot_reuse_qualification(self):
        self.protocol['resources']['aggregate_deadline_seconds']=1200;self.rejected_before_allocation()
    def test_qualified_unchanged_contract_reaches_fresh_prepare_once(self):
        self.write()
        with patch.object(m.v2.frozen,'prepare',side_effect=RuntimeError('CONTROL STOP BEFORE ALLOCATION')) as prepare:
            with self.assertRaisesRegex(RuntimeError,'CONTROL STOP'):m.seal(self.args)
            prepare.assert_called_once()
        self.assertFalse(self.args.study.exists())

if __name__=='__main__':unittest.main()
